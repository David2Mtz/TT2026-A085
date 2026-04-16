# demos/demo_color.py
import sys
import os
import cv2
from dotenv import load_dotenv

# Agregamos la ruta raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.flujo_camara import CameraSerial
from modules.detectarColor import process_color_frame

# Cargar variables de entorno
load_dotenv()

def main():
    print("--- INICIANDO DEMO: Módulo de Colores ---")
    print("Presiona 'q' en la ventana de video para salir.\n")
    
    # Inicializando la conexión con tu XH-32S
    puerto_camara = os.getenv('PUERTO_CAMARA', '/dev/cu.usbserial-210')
    camara = CameraSerial(port=puerto_camara, baud_rate=460800)

    try:
        while True:
            frame = camara.get_frame()
            
            if frame is not None:
                # Procesar únicamente el color
                frame_procesado, arreglo_colores = process_color_frame(frame)
                
                # Imprimir el arreglo constantemente para verificar estabilidad
                print(f"Estado de zonas [Izquierda, Centro, Derecha]: {arreglo_colores}")
                
                # Mostrar resultado
                cv2.imshow('DEMO - Deteccion de Color', frame_procesado)
            else:
                print("Esperando frame válido...")
            
            # Condición de salida
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("Cerrando demo de colores...")
                break

    except KeyboardInterrupt:
        print("\nEjecución detenida por el usuario.")
    finally:
        camara.liberar()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()