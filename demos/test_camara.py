# demos/test_camara.py
import sys
import os
import cv2
import time
from dotenv import load_dotenv

# Agregar la ruta raíz para poder importar utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.flujo_camara import CameraSerial

load_dotenv()

def test_stream():
    puerto = os.getenv('PUERTO_CAMARA', '/dev/cu.usbmodem21201')
    print(f"--- INICIANDO PRUEBA DE CÁMARA EN {puerto} ---")
    
    # Inicia con el baud rate corregido (460800)
    camara = CameraSerial(port=puerto, baud_rate=460800)
    
    if not camara.ser:
        print("[ERROR] No se pudo abrir el puerto serial. Revisa la conexión.")
        return

    print("\nControles del Demo:")
    print(" - 'q': Salir")
    
    fps_start_time = time.time()
    fps_counter = 0
    fps = 0

    try:
        while True:
            frame = camara.get_frame()
            
            if frame is not None:
                fps_counter += 1
                if time.time() - fps_start_time > 1.0:
                    fps = fps_counter
                    fps_counter = 0
                    fps_start_time = time.time()

                cv2.putText(frame, f"FPS: {fps}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow("Prueba de Conectividad XIAO S3", frame)
            else:
                print(".", end="", flush=True)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    except KeyboardInterrupt:
        print("\nPrueba detenida.")
    finally:
        camara.liberar()
        cv2.destroyAllWindows()
        print("\nRecursos liberados.")

if __name__ == "__main__":
    test_stream()
