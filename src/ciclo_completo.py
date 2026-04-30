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
PUERTO_CAMARA = os.getenv('PUERTO_CAMARA', '/dev/ttyUSB1')
PUERTO_BRAZO = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
COLOR_OBJETIVO = "Verde" 

class Estado:
    HOME = "HOME"
    OBSERVACION = "OBSERVACION"
    SEGUIMIENTO_PASTILLA = "SEGUIMIENTO_PASTILLA"
    RECOLECCION = "RECOLECCION"
    ESPERA_CONFIRMACION_AGARRE = "ESPERA_CONFIRMACION_AGARRE"
    OBSERVACION_MANIQUI = "OBSERVACION_MANIQUI"
    SEGUIMIENTO_BOCA = "SEGUIMIENTO_BOCA"
    ENTREGA = "ENTREGA"

def main():
    print("--- INICIANDO CICLO COMPLETO CON SENSOR DE DISTANCIA ToF ---")
    
    try:
        camara = CameraSerial(port=PUERTO_CAMARA, baud_rate=460800)
        # Actualizado a 115200 baudios para el nuevo firmware con ToF
        brazo = ArmController(puerto=PUERTO_BRAZO, baudios=115200)
    except Exception as e:
        print(f"[ERROR] No se pudo inicializar el hardware: {e}")
        return

    estado_actual = Estado.HOME
    macro_movimiento_hecho = False
    
    # Memoria para persistencia de objetivo (Lock-On)
    pos_objetivo_anterior = None
    
    # Configuración de distancias (mm)
    Z_MAX_RECOLECCION = 95 
    Z_MIN_RECOLECCION = 80 # Rango ampliado 85-95mm

    frames_sin_pastilla = 0
    
    print("Presiona 'n' para iniciar el ciclo, 'q' para salir.")

    try:
        while True:
            frame = camara.get_frame()
            if frame is None: continue

            frame_vis = frame.copy()
            dist_actual = brazo.obtener_distancia() # Nueva lectura del ToF
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break

            # Dibujar distancia (Z) y ángulos de servos coordinados
            z_coord = dist_actual
            color_z = (0, 255, 0) if (Z_MIN_RECOLECCION <= z_coord <= Z_MAX_RECOLECCION) else (0, 255, 255)
            cv2.putText(frame_vis, f"COORD Z (ToF): {z_coord}mm", (10, 30), 
                        cv2.FONT_HERSHEY_DUPLEX, 0.8, color_z, 2)
            
            s1, s6, s15 = brazo.estado_actual[1], brazo.estado_actual[6], brazo.estado_actual[15]
            cv2.putText(frame_vis, f"S1:{s1} | S6:{s6} | S15:{s15}", (10, 60), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # =================================================
            # --- MÁQUINA DE ESTADOS ---
            # =================================================

            if estado_actual == Estado.HOME:
                pos_objetivo_anterior = None # Resetear memoria
                if not macro_movimiento_hecho:
                    print("[MOVIMIENTO] Sincronizando posición HOME...")
                    brazo.mover_a_estado("HOME", forzar=True)
                    macro_movimiento_hecho = True
                
                cv2.putText(frame_vis, "HOME - Esperando 'n'", (10, 100), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                if key == ord('n'):
                    estado_actual = Estado.OBSERVACION
                    macro_movimiento_hecho = False

            elif estado_actual == Estado.OBSERVACION:
                if not macro_movimiento_hecho:
                    print("[MOVIMIENTO] Moviendo a zona de observación...")
                    brazo.mover_a_estado("OBSERVACION")
                    time.sleep(2) # Esperar a que la imagen se estabilice
                    macro_movimiento_hecho = True
                
                frame_vis, colores = process_color_frame(frame_vis)
                
                if macro_movimiento_hecho and (COLOR_OBJETIVO in colores):
                    print(f"[INFO] Objetivo '{COLOR_OBJETIVO}' detectado. Transicionando a RECOLECCION.")
                    estado_actual = Estado.RECOLECCION
                    macro_movimiento_hecho = False
                else:
                    cv2.putText(frame_vis, f"Buscando color: {COLOR_OBJETIVO}...", (10, 130), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            elif estado_actual == Estado.RECOLECCION:
                # Quitamos pos_anterior de aquí para que el detector use el centro de la pinza
                frame_vis, info = process_pastillas_frame(frame_vis, COLOR_OBJETIVO.lower(), 
                                                       dist_actual=dist_actual)
                
                if info:
                    ex, ey, area = info
                    frames_sin_pastilla = 0
                    
                    # --- LÓGICA DE MOVIMIENTO SIMULTÁNEO (X, Y, Z) ---
                    targets = {} 
                    tolerancia_vision = 12
                    
                    # 1. Ajuste Horizontal (Base - S0)
                    if abs(ex) > tolerancia_vision:
                        paso_x = 1 if ex > 0 else -1
                        targets[0] = brazo.estado_actual[0] + paso_x
                    
                    # 2. Ajuste de Profundidad inicial (Muñeca - S15)
                    angulo_15 = brazo.estado_actual[15]
                    if abs(ey) > tolerancia_vision:
                        paso_y = 1 if ey > 0 else -1
                        angulo_15 += paso_y

                    # 3. Descenso Dinámico (Hombro/Codo - S1/S6)
                    if z_coord > Z_MAX_RECOLECCION:
                        # Si está centrado, bajamos un poco más rápido
                        vel_descenso = 2 if (abs(ex) < 30 and abs(ey) < 30) else 1
                        
                        targets[1] = max(5, brazo.estado_actual[1] - vel_descenso)
                        targets[6] = max(5, brazo.estado_actual[6] - 1) 
                        
                        # Compensación de inclinación
                        if abs(ey) < 20:
                            angulo_15 = min(180, angulo_15 + 1)
                    
                    if angulo_15 != brazo.estado_actual[15]:
                        targets[15] = angulo_15

                    # 4. Condición de Parada: Rango 85-95mm + Centrado aceptable
                    if (Z_MIN_RECOLECCION <= z_coord <= Z_MAX_RECOLECCION) and abs(ex) < 25 and abs(ey) < 25:
                        print(f"[ToF] ZONA DE RECOLECCION ALCANZADA ({z_coord}mm).")
                        estado_actual = Estado.ESPERA_CONFIRMACION_AGARRE
                        macro_movimiento_hecho = False
                    
                    # Si el sensor baja de 85mm por inercia, también nos detenemos
                    elif z_coord < Z_MIN_RECOLECCION:
                        print(f"[ALERTA] Límite de seguridad alcanzado ({z_coord}mm).")
                        estado_actual = Estado.ESPERA_CONFIRMACION_AGARRE
                        macro_movimiento_hecho = False
                    
                    # Enviar comandos
                    if targets:
                        lista_cmds = [(p, a) for p, a in targets.items()]
                        brazo.mover_tiempo(lista_cmds, esperar=False)

                else:
                    frames_sin_pastilla += 1
                    if frames_sin_pastilla >= 20:
                        print("[INFO] Pastilla perdida, regresando a observación.")
                        estado_actual = Estado.OBSERVACION
                        macro_movimiento_hecho = False

            elif estado_actual == Estado.ESPERA_CONFIRMACION_AGARRE:
                cv2.putText(frame_vis, "OBJETIVO EN LA MIRA - Presiona 'c' para atrapar", (10, 90), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                if key == ord('c'):
                    print("[INFO] Confirmacion recibida. Cerrando pinza.")
                    brazo.mover_tiempo([(12, 10)]) 
                    time.sleep(1.2)
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
                # Abrir pinza (80 grados abre)
                brazo.mover_tiempo([(12, 90)])

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
    except Exception as e:
        print(f"\n[ERROR CRÍTICO] {e}")
    finally:
        print("\n[SEGURIDAD] Iniciando secuencia de apagado suave...")
        try:
            # Reintentar conexión si se cerró bruscamente
            if not brazo.esp32 or not brazo.esp32.is_open:
                brazo.conectar()
            
            # Regresar a HOME usando la lógica sincronizada
            brazo.mover_a_estado("HOME")
            time.sleep(2) # Dar tiempo para terminar el movimiento
            brazo.cerrar()
            camara.liberar()
        except:
            print("[ADVERTENCIA] No se pudo completar el regreso a HOME de forma segura.")
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
