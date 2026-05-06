# demos/test_acercamiento_boca.py
import sys
import os
import cv2
import time
import numpy as np
from dotenv import load_dotenv

# Ruta para importar módulos desde la raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.flujo_camara import CameraSerial
from modules.arm_controller import ArmController
from modules.detectorBoca import get_mouth_coordinates, iniciar_deteccion, finalizar_deteccion
from constants.posiciones import POSICIONES

load_dotenv()

PUERTO_CAMARA = os.getenv('PUERTO_CAMARA', '/dev/ttyUSB1')
PUERTO_BRAZO = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')

def main():
    print("--- DEMO: TEST DE ACERCAMIENTO AL MANIQUÍ ---")
    
    try:
        camara = CameraSerial(port=PUERTO_CAMARA, baud_rate=460800)
        brazo = ArmController(puerto=PUERTO_BRAZO, baudios=115200)
    except Exception as e:
        print(f"[ERROR] Hardware no disponible: {e}")
        return

    # Parámetros de control (iguales a ciclo_completo.py)
    Z_LIMITE_ENTREGA = 150
    TOLERANCIA_CENTRADO = 12
    contador_sondeo = 0
    lockon_activado_boca = False

    print("Yendo a posición inicial de búsqueda...")
    iniciar_deteccion(camara)
    brazo.mover_a_estado("OBSERVACION_MANIQUI", forzar=True, esperar=True)
    time.sleep(1)

    print("Presiona 'q' para salir.")

    try:
        while True:
            frame = camara.get_frame()
            if frame is None: continue

            # Rotar frame para el maniquí
            frame_rotated = cv2.rotate(frame, cv2.ROTATE_180)
            frame_vis = frame_rotated.copy()
            
            # Centro objetivo visual (Mira azul)
            cv_h, cv_w = frame_vis.shape[:2]
            cv2.drawMarker(frame_vis, (cv_w // 2, cv_h // 2), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)

            dist_actual = brazo.obtener_distancia()
            frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break

            if coords_boca:
                contador_sondeo = 0
                # Cálculo de errores
                ex = coords_boca[0] - (cv_w // 2)
                ey = coords_boca[1] - (cv_h // 2)
                
                targets = {}
                
                # 1. Centrado Horizontal (S0)
                if abs(ex) > 8:
                    paso_x = 2 if abs(ex) > 60 else 1
                    targets[0] = brazo.estado_actual[0] + (paso_x if ex > 0 else -paso_x)
                
                # 2. Centrado Vertical Dinámico (S15 + S6)
                if abs(ey) > 10:
                    # S15: Ajuste fino de inclinación
                    paso_y = 1
                    targets[15] = brazo.estado_actual[15] + (paso_y if ey > 0 else -paso_y)
                    
                    # S6: Compensación de altura del antebrazo (S6 aumenta para bajar)
                    if abs(ey) > 30:
                        targets[6] = brazo.estado_actual[6] + (1 if ey > 0 else -1)

                # 3. ACERCAMIENTO COORDINADO (Extensión S1 + S6)
                if dist_actual > Z_LIMITE_ENTREGA:
                    # S1: Progresión constante
                    if brazo.estado_actual[1] > 70:
                        targets[1] = brazo.estado_actual[1] - 1
                    
                    # S6: Extensión subordinada al centrado vertical
                    if 6 not in targets and brazo.estado_actual[6] > 0:
                        targets[6] = brazo.estado_actual[6] - 1
                    
                    if dist_actual <= 250 and abs(ex) <= TOLERANCIA_CENTRADO:
                        if not lockon_activado_boca:
                            print("[DETECCIÓN] Lock-On Activado.")
                            lockon_activado_boca = True
                else:
                    cv2.putText(frame_vis, "OBJETIVO ALCANZADO (150mm)", (10, 100), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                if targets:
                    brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
            
            else:
                # Sondeo si no hay boca
                contador_sondeo += 1
                if contador_sondeo < 100:
                    offset = 8 * np.sin(contador_sondeo * 0.15)
                    brazo.mover_tiempo([(0, POSICIONES["OBSERVACION_MANIQUI"][0][1] + offset)], esperar=False)
                    cv2.putText(frame_vis, "SONDEO DE BOCA...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                else:
                    cv2.putText(frame_vis, "BOCA PERDIDA", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # Info en pantalla
            cv2.putText(frame_vis, f"Distancia ToF: {dist_actual}mm", (10, 30), 
                        cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 255, 0) if dist_actual <= Z_LIMITE_ENTREGA else (0, 255, 255), 2)
            cv2.imshow('Demo Acercamiento Maniqui', frame_vis)

    except KeyboardInterrupt: pass
    finally:
        print("Cerrando...")
        finalizar_deteccion(camara)
        brazo.mover_a_estado("HOME", forzar=True, esperar=True)
        brazo.cerrar()
        camara.liberar()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
