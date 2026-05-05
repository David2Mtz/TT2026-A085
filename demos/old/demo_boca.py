# demos/demo_boca.py
import sys
import os
import cv2
from dotenv import load_dotenv

# Agregamos la ruta raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.flujo_camara import CameraSerial
from modules.mouth_detector import get_mouth_coordinates

# Cargar variables de entorno
load_dotenv()

def main():
    print("--- INICIANDO DEMO: Detector de Boca (Dlib) ---")
    print("Asegúrate de que el archivo .dat esté en la raíz o ajusta su ruta en el módulo.")
    print("Presiona 'q' en la ventana de video para salir.\n")
    
    # Inicializando la conexión con tu XH-32S
    puerto_camara = os.getenv('PUERTO_CAMARA', '/dev/cu.usbserial-210')
    camara = CameraSerial(port=puerto_camara, baud_rate=460800)

    try:
        while True:
            frame = camara.get_frame()
            
            if frame is not None:
                # Procesar únicamente la detección del rostro/boca
                frame_procesado, coords_boca = get_mouth_coordinates(frame)
                
                if coords_boca is not None:
                    print(f"Objetivo localizado. Coordenadas del centro de la boca: X={coords_boca[0]}, Y={coords_boca[1]}")
                else:
                    print("Buscando rostro/boca en el frame...")
                
                # Mostrar resultado
                cv2.imshow('DEMO - Deteccion de Boca', frame_procesado)
            else:
                print("Esperando frame válido...")
            
            # Condición de salida
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("Cerrando demo de boca...")
                break

    except KeyboardInterrupt:
        print("\nEjecución detenida por el usuario.")
    finally:
        camara.liberar()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()