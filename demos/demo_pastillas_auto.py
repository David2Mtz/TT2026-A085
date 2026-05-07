# demos/demo_pastillas_auto.py
import sys
import os
import cv2
import time
from dotenv import load_dotenv

# Agregar la ruta raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.flujo_camara import CameraSerial
from modules.pastillas_detector import process_pastillas_frame
from modules.auto_exposure import AutoExposureControl

load_dotenv()

def main():
    puerto = os.getenv('PUERTO_CAMARA', '/dev/cu.usbserial-2130')
    baud = 460800
    
    print(f"--- DEMO DETECCIÓN DE PASTILLAS (MODO AUTÓNOMO) ---")
    camara = CameraSerial(port=puerto, baud_rate=baud)
    
    if not camara.ser:
        return

    # Inicializar el control autónomo de exposición
    auto_exp = AutoExposureControl(target_brightness=135) # Un poco más brillante para detectar mejor
    
    colores = ["verde", "azul", "rojo"]
    color_idx = 0 # Empezar con verde
    
    print("\nInstrucciones:")
    print("- La cámara ajustará el LED y la Exposición automáticamente.")
    print("- Presiona 'c' para cambiar el color de la base.")
    print("- Presiona 'q' para salir.")

    try:
        while True:
            frame = camara.get_frame()
            
            if frame is not None:
                # 1. Ajustar exposición automáticamente basándose en el frame actual
                auto_exp.update(frame, camara)
                
                # 2. Procesar pastillas
                color_base = colores[color_idx]
                processed_frame, error = process_pastillas_frame(frame, color_base)
                
                # UI
                cv2.putText(processed_frame, f"Modo: AUTONOMO | Base: {color_base}", (10, 25), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.putText(processed_frame, f"LED: {auto_exp.current_led} | EXP: {auto_exp.current_exp}", (10, 50), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                cv2.imshow("Deteccion Autonoma", processed_frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('c'):
                color_idx = (color_idx + 1) % len(colores)
                print(f"Cambiando a base color: {colores[color_idx]}")

    except KeyboardInterrupt:
        pass
    finally:
        camara.set_led_brightness(0)
        camara.liberar()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
