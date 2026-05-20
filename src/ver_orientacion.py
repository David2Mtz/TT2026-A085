# src/ver_orientacion.py
import sys
import os
import time
import math
import cv2
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.arm_controller import ArmController

load_dotenv()

def main():
    print("=== MONITOR DE ORIENTACIÓN REAL (YAW) ===")
    print("Este script te permite ver cuánto se mueve físicamente el brazo.")
    print("Usa 'A' y 'D' para mover la base y observa el cambio en el ángulo magnético.")
    
    puerto = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
    brazo = ArmController(puerto=puerto, baudios=115200)
    
    try:
        while True:
            # 1. Obtener datos del magnetómetro
            mx, my, mz = brazo.mag1
            
            # 2. Calcular el ángulo real (Yaw) usando X e Y
            # atan2 nos da el ángulo en radianes, lo pasamos a grados
            angulo_real = math.atan2(my, mx) * (180 / math.pi)
            
            # 3. Interfaz simple
            print(f"\rComando Base: {brazo.estado_actual[0]}° | Ángulo Magnético Real: {angulo_real:.2f}°   ", end="")
            
            # 4. Control manual de prueba
            key = cv2.waitKey(100) & 0xFF
            if key == ord('d'):
                brazo.mover_tiempo([(0, brazo.estado_actual[0] + 1)], esperar=True)
            elif key == ord('a'):
                brazo.mover_tiempo([(0, brazo.estado_actual[0] - 1)], esperar=True)
            elif key == ord('q'):
                break
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        pass
    finally:
        brazo.cerrar()

if __name__ == "__main__":
    main()
