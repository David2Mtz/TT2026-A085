# demos/demo_led.py
import sys
import os
import time
from dotenv import load_dotenv

# Agregamos la ruta raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.flujo_camara import CameraSerial

load_dotenv()

def main():
    print("--- DEMO: Control de Brillo del LED ---")
    
    puerto_camara = os.getenv('PUERTO_CAMARA', '/dev/ttyUSB1')
    try:
        camara = CameraSerial(port=puerto_camara, baud_rate=460800)
    except Exception as e:
        print(f"Error al conectar: {e}")
        return

    try:
        # 1. Apagar
        print("Apagando LED...")
        camara.set_led_brightness(0)
        time.sleep(1)

        # 2. Brillo bajo
        print("Brillo bajo (10)...")
        camara.set_led_brightness(10)
        time.sleep(2)

        # 3. Brillo medio
        print("Brillo medio (128)...")
        camara.set_led_brightness(128)
        time.sleep(2)

        # 4. Brillo máximo
        print("Brillo máximo (255)...")
        camara.set_led_brightness(255)
        time.sleep(2)

        # 5. Efecto respiración (Fade in/out)
        print("Efecto respiración...")
        for _ in range(2):
            for b in range(0, 256, 10):
                camara.set_led_brightness(b)
                time.sleep(0.05)
            for b in range(255, -1, -10):
                camara.set_led_brightness(b)
                time.sleep(0.05)

        print("Apagando finalmente.")
        camara.set_led_brightness(0)

    except KeyboardInterrupt:
        print("\nDemo interrumpida.")
    finally:
        camara.liberar()

if __name__ == '__main__':
    main()
