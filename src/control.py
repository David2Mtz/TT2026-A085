# main_autonomo_dinamico.py
import sys
import os
import cv2
import time
from dotenv import load_dotenv

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
PUERTO_CAMARA = os.getenv('PUERTO_CAMARA', '/dev/ttyUSB1')
PUERTO_BRAZO = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')

# Color objetivo a buscar (Asegúrate de que inicie en mayúscula para coincidir con get_color_name)
COLOR_OBJETIVO = "Azul" 

class Estado:
    INICIO_HOME = "INICIO_HOME"
    OBSERVAR_COLORES = "OBSERVAR_COLORES"
    BUSQUEDA = "BUSQUEDA"
    RECOLECCION = "RECOLECCION"
    OBSERVACION_MANIQUI = "OBSERVACION_MANIQUI"
    SOLTAR = "SOLTAR"

def main():
    print("--- INICIANDO CICLO AUTÓNOMO IBVS ---")
    camara = CameraSerial(port=PUERTO_CAMARA, baud_rate=460800)
    brazo = ArmController(puerto=PUERTO_BRAZO, baudios=115200)
    
    estado_actual = Estado.INICIO_HOME
    macro_movimiento_hecho = False 
    
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
            # 1. INICIO (HOME)
            # =================================================
            if estado_actual == Estado.INICIO_HOME:
                if not macro_movimiento_hecho:
                    brazo.mover_a_estado("HOME")
                    macro_movimiento_hecho = True
                
                #TODO: REEMPLAZAR POR 3BLINKS
                cv2.putText(frame_vis, "Presiona 'n' para iniciar", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                if key == ord('n'):
                    estado_actual = Estado.OBSERVAR_COLORES
                    macro_movimiento_hecho = False

            # =================================================
            # 2. OBSERVACIÓN Y VALIDACIÓN DE COLORES
            # =================================================
            elif estado_actual == Estado.OBSERVAR_COLORES:
                if not macro_movimiento_hecho:
                    # Se utiliza la posición general para ver toda la mesa
                    brazo.mover_a_estado("OBSERVACION") 
                    time.sleep(1) 
                    macro_movimiento_hecho = True

                # Obtenemos el arreglo de los 3 cuadrantes
                frame_vis, colores = process_color_frame(frame_vis)
                
                # Asignamos el resultado al arreglo de validación
                definir_bloque_candidatos = colores

                if COLOR_OBJETIVO in definir_bloque_candidatos:
                    indice_target = definir_bloque_candidatos.index(COLOR_OBJETIVO)
                    print(f"[INFO] Objetivo '{COLOR_OBJETIVO}' localizado en el índice {indice_target} del bloque de candidatos.")
                    print("[INFO] Transfiriendo control al Servocontrol Visual (IBVS)...")
                    
                    # No hay movimiento hardcodeado, pasamos directo a que la cámara guíe al brazo
                    estado_actual = Estado.BUSQUEDA
                    macro_movimiento_hecho = False
                else:
                    cv2.putText(frame_vis, f"Buscando color: {COLOR_OBJETIVO}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # =================================================
            # 3. BÚSQUEDA Y CENTRADO DE PASTILLA (IBVS)
            # =================================================
            elif estado_actual == Estado.BUSQUEDA:
                # Se envía en minúsculas porque get_hsv_ranges lo requiere así
                frame_vis, error = process_pastillas_frame(frame_vis, COLOR_OBJETIVO.lower())
                
                if error:
                    # El brazo se moverá dinámicamente basándose en el error X, Y de la pastilla
                    centrado = brazo.centrar_ibvs(error[0], error[1])
                    if centrado:
                        print("[INFO] Pastilla centrada exitosamente por visión.")
                        estado_actual = Estado.RECOLECCION
                        macro_movimiento_hecho = False
                else:
                    cv2.putText(frame_vis, "Rastreando base de pastillero...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

            # =================================================
            # 4. RECOLECCIÓN
            # =================================================
            elif estado_actual == Estado.RECOLECCION:
                print("[INFO] Ejecutando maniobra de recolección.")
                brazo.mover_tiempo([(1, 100), (3, 80)]) # Bajar
                time.sleep(0.5)
                brazo.mover_tiempo([(15, 110)])          # Agarrar (Pin 15)
                time.sleep(0.5)
                brazo.mover_a_estado("PRE_RECOLECCION") # Levantar carga
                
                estado_actual = Estado.OBSERVACION_MANIQUI
                macro_movimiento_hecho = False

            # =================================================
            # 5. OBSERVACIÓN MANIQUÍ Y CENTRADO DE BOCA (IBVS)
            # =================================================
            elif estado_actual == Estado.OBSERVACION_MANIQUI:
                if not macro_movimiento_hecho:
                    brazo.mover_a_estado("ENTREGA")
                    time.sleep(1)
                    macro_movimiento_hecho = True
                
                frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                
                if coords_boca:
                    error_x = coords_boca[0] - (frame_vis.shape[1] // 2)
                    error_y = coords_boca[1] - (frame_vis.shape[0] // 2)
                    
                    # Se reutiliza la lógica IBVS para centrar la boca a 15cm (tamaño relativo)
                    centrado = brazo.centrar_ibvs(error_x, error_y)
                    if centrado:
                        print("[INFO] Maniquí centrado y en posición de entrega.")
                        estado_actual = Estado.SOLTAR
                        macro_movimiento_hecho = False
                else:
                    cv2.putText(frame_vis, "Detectando landmarks faciales...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

            # =================================================
            # 6. SOLTAR y 7. REGRESO A HOME
            # =================================================
            elif estado_actual == Estado.SOLTAR:
                print("[INFO] Liberando pastilla.")
                brazo.mover_tiempo([(15, 0)]) # Abrir pinza (Pin 15)
                time.sleep(1)
                
                print("[INFO] Ciclo finalizado. Regresando a HOME.")
                estado_actual = Estado.INICIO_HOME
                macro_movimiento_hecho = False

            # UI Visual
            cv2.putText(frame_vis, f"ESTADO: {estado_actual}", (10, frame_vis.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow('Prototipo Control Hibrido', frame_vis)

    except KeyboardInterrupt:
        print("\n[INFO] Ejecución interrumpida por el usuario.")
    finally:
        print("\n[INFO] Finalizando programa. Regresando brazo a HOME...")
        brazo.mover_a_estado("HOME")
        brazo.cerrar()
        camara.liberar()
        cv2.destroyAllWindows()
        print("[INFO] Recursos liberados correctamente.")

if __name__ == "__main__":
    main()