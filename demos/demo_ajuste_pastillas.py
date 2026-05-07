# demos/demo_ajuste_pastillas.py
import sys
import os
import cv2
import time
from dotenv import load_dotenv

# Agregar la ruta raíz para poder importar utils y modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.flujo_camara import CameraSerial
from modules.pastillas_detector import process_pastillas_frame

load_dotenv()

def nothing(x):
    pass

def main():
    puerto = os.getenv('PUERTO_CAMARA', '/dev/cu.usbserial-2130')
    # Si test_camara.py te funciona a 460800, usemos esa misma velocidad aquí
    baud = 460800 
    
    print(f"--- DEMO CALIBRACIÓN DETECCIÓN DE PASTILLAS ---")
    print(f"Puerto: {puerto} | Baud: {baud}")
    
    camara = CameraSerial(port=puerto, baud_rate=baud)
    
    if not camara.ser:
        print("[ERROR] No se pudo conectar con la cámara.")
        return

    # Nombre de ventana consistente
    win_name = "Calibracion de Pastillas"
    cv2.namedWindow(win_name)
    cv2.createTrackbar("LED", win_name, 48, 255, nothing)
    cv2.createTrackbar("Exposicion", win_name, 300, 1200, nothing)
    cv2.createTrackbar("Color Base", win_name, 0, 2, nothing)
    colores = ["verde", "azul", "rojo"]

    print("\nInstrucciones:")
    print("- Ajusta los sliders.")
    print("- 'q' para salir.")

    last_led = -1
    last_exp = -1

    try:
        while True:
            # Obtener frame PRIMERO para asegurar flujo
            frame = camara.get_frame()
            
            # Leer valores de trackbars
            led_val = cv2.getTrackbarPos("LED", win_name)
            exp_val = cv2.getTrackbarPos("Exposicion", win_name)
            color_idx = cv2.getTrackbarPos("Color Base", win_name)
            
            # Evitar indices fuera de rango
            color_idx = max(0, min(2, color_idx))
            color_base = colores[color_idx]

            # Aplicar cambios solo si variaron
            if led_val != last_led:
                camara.set_led_brightness(led_val)
                last_led = led_val
            
            if exp_val != last_exp:
                camara.set_exposure(exp_val)
                last_exp = exp_val

            if frame is not None:
                # Procesar frame
                processed_frame, error = process_pastillas_frame(frame, color_base)
                
                # Info en pantalla
                status_text = f"Base: {color_base} | LED: {led_val} | EXP: {exp_val}"
                cv2.putText(processed_frame, status_text, (10, 20), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                
                cv2.imshow(win_name, processed_frame)
            else:
                # Si no hay frame, mostrar algo para saber que el loop sigue vivo
                print("Esperando imagen...", end="\r")

            # Aumentamos un poco el tiempo de waitKey para dar tiempo a renderizar
            if cv2.waitKey(30) & 0xFF == ord('q'):
                break
                
    except KeyboardInterrupt:
        pass
    finally:
        camara.set_led_brightness(0)
        camara.liberar()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
