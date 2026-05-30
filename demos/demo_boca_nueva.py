# demos/demo_boca_nueva.py
import sys
import os
import cv2
import numpy as np
import time
from dotenv import load_dotenv

# Agregamos la ruta raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.flujo_camara import CameraSerial
# Importamos las funciones de detección
from modules.detectorBoca import get_mouth_coordinates

# Cargar variables de entorno
load_dotenv()

def main():
    print("--- INICIANDO DEMO: Detector de Boca Mejorado (Color Lima) ---\n")
    
    # Intentar obtener puerto de cámara desde .env
    puerto_camara = os.getenv('PUERTO_CAMARA', '/dev/ttyUSB1')
    
    try:
        camara = CameraSerial(port=puerto_camara, baud_rate=460800)
    except Exception as e:
        print(f"[ERROR] No se pudo conectar a la cámara en {puerto_camara}: {e}")
        return

    time.sleep(1) # Tiempo para que la cámara ajuste exposición

    try:
        while True:
            frame = camara.get_frame()
            
            if frame is not None:
                # Procesar la detección (Módulo Puro)
                frame_procesado, coords_boca = get_mouth_coordinates(frame)
                
                if coords_boca is not None:
                    cv2.putText(frame_procesado, f"Boca: {coords_boca}", (10, frame_procesado.shape[0] - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
                
                # Mostrar resultado
                cv2.imshow('DEMO - Detector Boca (Nuevo)', frame_procesado)
            
            # Condición de salida
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("\nCerrando demo por teclado...")
                break

    except KeyboardInterrupt:
        print("\nEjecución detenida por Ctrl+C.")
    except Exception as e:
        print(f"\n[ERROR CRITICO] {e}")
    finally:
        camara.liberar()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
