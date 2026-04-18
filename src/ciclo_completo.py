# src/ciclo_completo.py
import sys
import os
import cv2
import time
from dotenv import load_dotenv

# Corrección de ruta para importar módulos desde la raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.flujo_camara import CameraSerial
from modules.arm_controller import ArmController
from modules.pastillas_detector import process_pastillas_frame
from modules.detectarColor import process_color_frame
from modules.mouth_detector import get_mouth_coordinates

# Cargar variables de entorno
load_dotenv()

# ===============================================================
# --- CONFIGURACIÓN PRINCIPAL ---
# ===============================================================
PUERTO_CAMARA = os.getenv('PUERTO_CAMARA', '/dev/cu.usbserial-210')
PUERTO_BRAZO = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
COLOR_OBJETIVO = "Verde" 

class Estado:
    HOME = "HOME"
    OBSERVACION = "OBSERVACION"
    SEGUIMIENTO_PASTILLA = "SEGUIMIENTO_PASTILLA"
    RECOLECCION = "RECOLECCION"
    OBSERVACION_MANIQUI = "OBSERVACION_MANIQUI"
    SEGUIMIENTO_BOCA = "SEGUIMIENTO_BOCA"
    ENTREGA = "ENTREGA"

def main():
    print("--- INICIANDO CICLO COMPLETO CON SEGUIMIENTO PROPORCIONAL ---")
    
    try:
        camara = CameraSerial(port=PUERTO_CAMARA, baud_rate=460800)
        brazo = ArmController(puerto=PUERTO_BRAZO, baudios=9600)
    except Exception as e:
        print(f"[ERROR] No se pudo inicializar el hardware: {e}")
        return

    estado_actual = Estado.HOME
    macro_movimiento_hecho = False
    
    # Variables para el protocolo de búsqueda
    frames_sin_pastilla = 0
    fase_busqueda_pastilla = 0
    direccion_base = 1
    
    print("Presiona 'n' para iniciar el ciclo, 'q' para salir.")

    try:
        while True:
            frame = camara.get_frame()
            if frame is None:
                continue

            frame_vis = frame.copy()
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break

            # =================================================
            # --- MÁQUINA DE ESTADOS ---
            # =================================================

            if estado_actual == Estado.HOME:
                if not macro_movimiento_hecho:
                    brazo.mover_a_estado("HOME")
                    macro_movimiento_hecho = True
                
                cv2.putText(frame_vis, "HOME - Esperando 'n'", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                if key == ord('n'):
                    estado_actual = Estado.OBSERVACION
                    macro_movimiento_hecho = False

            elif estado_actual == Estado.OBSERVACION:
                if not macro_movimiento_hecho:
                    brazo.mover_a_estado("OBSERVACION")
                    time.sleep(1)
                    macro_movimiento_hecho = True
                
                frame_vis, colores = process_color_frame(frame_vis)
                
                if COLOR_OBJETIVO in colores:
                    print(f"[INFO] Color {COLOR_OBJETIVO} localizado. Iniciando rastreo.")
                    estado_actual = Estado.SEGUIMIENTO_PASTILLA
                    macro_movimiento_hecho = False
                else:
                    cv2.putText(frame_vis, f"Buscando color: {COLOR_OBJETIVO}", (10, 60), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            elif estado_actual == Estado.SEGUIMIENTO_PASTILLA:
                # Usamos process_pastillas_frame para obtener el error visual
                frame_vis, error = process_pastillas_frame(frame_vis, COLOR_OBJETIVO.lower())
                
                if error:
                    frames_sin_pastilla = 0
                    fase_busqueda_pastilla = 0
                    # Método proporcional inteligente para el centrado
                    centrado = brazo.centrar_proporcional(error[0], error[1])
                    if centrado:
                        print("[INFO] Pastilla centrada. Iniciando recolección.")
                        estado_actual = Estado.RECOLECCION
                        macro_movimiento_hecho = False
                else:
                    frames_sin_pastilla += 1
                    cv2.putText(frame_vis, f"Buscando pastilla... ({frames_sin_pastilla})", (10, 60), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                    
                    if frames_sin_pastilla >= 5:
                        frames_sin_pastilla = 0 # Reiniciamos para dar tiempo al siguiente movimiento
                        
                        if fase_busqueda_pastilla == 0:
                            print("[BUSQUEDA] Fase 1: Moviendo Servo 3 hacia ARRIBA (Paso fino)")
                            brazo.mover_tiempo([(3, brazo.estado_actual[3] - 5)])
                            fase_busqueda_pastilla = 1
                        elif fase_busqueda_pastilla == 1:
                            print("[BUSQUEDA] Fase 2: Moviendo Servo 0 hacia los LADOS (Paso fino)")
                            nuevo_angulo_0 = brazo.estado_actual[0] + (5 * direccion_base)
                            if nuevo_angulo_0 > 45 or nuevo_angulo_0 < -45:
                                direccion_base *= -1
                            brazo.mover_tiempo([(0, nuevo_angulo_0)])
                            fase_busqueda_pastilla = 2
                        elif fase_busqueda_pastilla == 2:
                            print("[BUSQUEDA] Fase 3: Moviendo Servo 3 hacia ABAJO (Paso fino)")
                            brazo.mover_tiempo([(3, brazo.estado_actual[3] + 5)])
                            fase_busqueda_pastilla = 0 # Reiniciar ciclo de búsqueda

            elif estado_actual == Estado.RECOLECCION:
                print("[INFO] Ejecutando maniobra de recolección.")
                # Bajar brazo (Servo 3 primero, luego 1 para evitar choque)
                brazo.mover_tiempo([(3, 80), (1, 100)])
                time.sleep(0.5)
                # Cerrar pinza (Servo 6)
                brazo.mover_tiempo([(6, 110)])
                time.sleep(0.5)
                # Subir para evitar colisiones
                brazo.mover_a_estado("PRE_RECOLECCION")
                
                estado_actual = Estado.OBSERVACION_MANIQUI
                macro_movimiento_hecho = False

            elif estado_actual == Estado.OBSERVACION_MANIQUI:
                if not macro_movimiento_hecho:
                    brazo.mover_a_estado("ENTREGA")
                    time.sleep(1)
                    macro_movimiento_hecho = True
                
                frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                if coords_boca:
                    print("[INFO] Maniquí detectado. Centrando boca.")
                    estado_actual = Estado.SEGUIMIENTO_BOCA
                    macro_movimiento_hecho = False
                else:
                    cv2.putText(frame_vis, "Buscando boca del maniquí...", (10, 60), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

            elif estado_actual == Estado.SEGUIMIENTO_BOCA:
                frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                
                if coords_boca:
                    # Calcular error respecto al centro de la cámara
                    error_x = coords_boca[0] - (frame_vis.shape[1] // 2)
                    error_y = coords_boca[1] - (frame_vis.shape[0] // 2)
                    
                    centrado = brazo.centrar_proporcional(error_x, error_y)
                    if centrado:
                        print("[INFO] Boca centrada. Soltando pastilla.")
                        estado_actual = Estado.ENTREGA
                        macro_movimiento_hecho = False
                else:
                    # Si perdemos el maniquí, regresamos a buscarlo
                    estado_actual = Estado.OBSERVACION_MANIQUI
                    macro_movimiento_hecho = False

            elif estado_actual == Estado.ENTREGA:
                print("[INFO] Liberando carga.")
                # Abrir pinza
                brazo.mover_tiempo([(6, 10)])
                time.sleep(1)
                
                print("[INFO] Ciclo finalizado satisfactoriamente.")
                estado_actual = Estado.HOME
                macro_movimiento_hecho = False

            # --- UI de Visualización ---
            cv2.putText(frame_vis, f"ESTADO: {estado_actual}", (10, frame_vis.shape[0] - 20), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow('Ciclo Autonomo Inteligente', frame_vis)

    except KeyboardInterrupt:
        print("\n[INFO] Ejecución cancelada por el usuario.")
    finally:
        print("[INFO] Limpiando recursos y regresando a HOME.")
        brazo.mover_a_estado("HOME")
        brazo.cerrar()
        camara.liberar()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
