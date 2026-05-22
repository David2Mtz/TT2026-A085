# src/prueba_maniqui.py
import sys
import os
import cv2
import time
import numpy as np
from dotenv import load_dotenv

# Corrección de ruta para importar módulos desde la raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.flujo_camara import CameraSerial
from modules.detectorBoca import get_mouth_coordinates

# Cargar variables de entorno
load_dotenv()

# Clase Mock para simular el brazo sin hardware
class MockArm:
    def __init__(self):
        self.estado_actual = [90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90]
        self.en_emergencia = False
        self.estado_pinza = "ABIERTA"
        self.mag1 = [0.0, 0.0, 0.0]
    def obtener_distancia(self): return 300 # Distancia fija simulada
    def mover_a_estado(self, estado, **kwargs): print(f"[MOCK] Moviendo a {estado}")
    def mover_tiempo(self, movimientos, **kwargs): 
        for p, a in movimientos:
            self.estado_actual[p] = a
        print(f"[MOCK] Movimiento: {movimientos}")
    def cerrar(self): pass

def main():
    print("--- INICIANDO PRUEBA DE DETECCIÓN DE MANIQUÍ (SIN BRAZO) ---")
    
    PUERTO_CAMARA = os.getenv('PUERTO_CAMARA', '/dev/cu.usbmodem2101')
    BAUD_CAMARA = int(os.getenv('BAUD_CAMARA', 460800))

    try:
        camara = CameraSerial(port=PUERTO_CAMARA, baud_rate=BAUD_CAMARA)
        brazo = MockArm()
    except Exception as e:
        print(f"[ERROR] No se pudo inicializar la cámara: {e}")
        return

    print("\nControles:")
    print(" - 'q': Salir")
    print(" - 'r': Alternar Rotación 180 (Maniquí suele verse invertido)")

    rotate_180 = True

    try:
        while True:
            frame = camara.get_frame()
            if frame is None:
                print(".", end="", flush=True)
                continue
            
            if rotate_180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            
            frame_vis = frame.copy()
            
            # Centro objetivo visual (Cruz azul)
            cv_h, cv_w = frame_vis.shape[:2]
            cv2.drawMarker(frame_vis, (cv_w // 2, cv_h // 2), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)
            
            # 1. Intentar detectar boca y landmarks
            frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
            
            if coords_boca:
                ex = coords_boca[0] - (cv_w // 2)
                ey = coords_boca[1] - (cv_h // 2)
                
                # Dibujar línea al objetivo
                cv2.line(frame_vis, (cv_w // 2, cv_h // 2), (coords_boca[0], coords_boca[1]), (0, 255, 0), 2)
                cv2.putText(frame_vis, f"Error: X={ex}, Y={ey}", (10, 60), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                print(f"\rBoca detectada en: {coords_boca} | Error: X={ex}, Y={ey}    ", end="")
            else:
                cv2.putText(frame_vis, "Buscando Rostro/Boca...", (10, 60), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                print("\rBuscando...                                         ", end="")

            cv2.putText(frame_vis, f"Rotacion 180: {'SI' if rotate_180 else 'NO'} (tecla 'r')", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

            cv2.imshow('Prueba de Maniqui', frame_vis)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break
            if key == ord('r'): rotate_180 = not rotate_180

    except KeyboardInterrupt:
        print("\nPrueba detenida.")
    finally:
        camara.liberar()
        cv2.destroyAllWindows()
        print("\nRecursos liberados.")

if __name__ == "__main__":
    main()
