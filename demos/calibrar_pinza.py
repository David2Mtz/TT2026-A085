# demos/calibrar_pinza.py
import sys
import os
import cv2
import time
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.flujo_camara import CameraSerial
from modules.arm_controller import ArmController
from constants.config import OFFSET_X, OFFSET_Y

load_dotenv()

def calibrar():
    puerto_cam = os.getenv('PUERTO_CAMARA', '/dev/cu.usbserial-210')
    puerto_brazo = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
    
    camara = CameraSerial(port=puerto_cam, baud_rate=460800)
    brazo = ArmController(puerto=puerto_brazo, baudios=115200)
    
    # Mover a posición de observación para calibrar
    print("[INFO] Moviendo a posición de OBSERVACION...")
    brazo.mover_a_estado("OBSERVACION")
    
    offset_y = OFFSET_Y
    offset_x = OFFSET_X
    print("\n--- MODO CALIBRACIÓN DE PINZA ---")
    print("Usa 'w'/'s' para ajustar offset Y (arriba/abajo)")
    print("Usa 'a'/'d' para ajustar offset X (izquierda/derecha)")
    print("Usa 'q' para salir y ver los valores finales")

    try:
        while True:
            frame = camara.get_frame()
            if frame is None: continue
            
            alto, ancho = frame.shape[:2]
            cx, cy = ancho // 2, alto // 2
            
            # Centro ajustado (Azul)
            cx_offset = cx + offset_x
            cy_offset = cy + offset_y
            
            # Dibujar Centro Real (Blanco - Referencia)
            cv2.line(frame, (cx - 10, cy), (cx + 10, cy), (255, 255, 255), 1)
            cv2.line(frame, (cx, cy - 10), (cx, cy + 10), (255, 255, 255), 1)
            
            # Dibujar Cruceta de Calibración (Azul - Centro de Pinza)
            cv2.line(frame, (cx_offset, 0), (cx_offset, alto), (255, 0, 0), 1)
            cv2.line(frame, (0, cy_offset), (ancho, cy_offset), (255, 0, 0), 1)
            cv2.circle(frame, (cx_offset, cy_offset), 5, (0, 255, 0), -1)

            cv2.putText(frame, f"OFFSET X: {offset_x} Y: {offset_y}", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
            cv2.putText(frame, "Alinea el punto VERDE con el centro de tu pinza", (10, alto - 20), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            cv2.imshow("Calibracion de Offset - Vision", frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('w'):
                offset_y += 1
            elif key == ord('s'):
                offset_y -= 1
            elif key == ord('d'):
                offset_x += 1
            elif key == ord('a'):
                offset_x -= 1
                
    finally:
        print(f"\n[CALIBRACIÓN FINALIZADA] Valores ideales:")
        print(f"OFFSET_X = {offset_x}")
        print(f"OFFSET_Y = {offset_y}")
        print("\nActualiza estos valores en constants/config.py")
        print("[INFO] Moviendo a posición de home...")
        brazo.mover_a_estado("HOME")
        camara.liberar()
        brazo.cerrar()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    calibrar()
