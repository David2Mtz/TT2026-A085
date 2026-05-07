# demos/demo_auto_ajuste.py
import sys
import os
import cv2
import time
from dotenv import load_dotenv

# Agregar la ruta raíz para poder importar utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.flujo_camara import CameraSerial

load_dotenv()

def main():
    puerto = os.getenv('PUERTO_CAMARA', '/dev/cu.usbserial-2130')
    print(f"--- DEMO AUTO-AJUSTE DE ILUMINACIÓN ---")
    
    camara = CameraSerial(port=puerto, baud_rate=230400)
    
    if not camara.ser:
        print("[ERROR] No se pudo conectar con la cámara.")
        return

    print("\nInstrucciones:")
    print("- Presiona 'a' para ejecutar el Auto-Ajuste Autónomo.")
    print("- Presiona 'q' para salir.")

    try:
        while True:
            frame = camara.get_frame()
            
            if frame is not None:
                # Añadir un indicador de que el auto-ajuste está activo
                cv2.putText(frame, "Auto-Ajuste: ON", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow("Demo Auto-Ajuste", frame)
            else:
                print("Esperando frame de la cámara...", end="\r")
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('a'):
                print("\n[Comando] Disparando auto-ajuste manual...")
                exito = camara.auto_ajustar()
                if exito:
                    print("[OK] Ajuste completado.")
                else:
                    print("[FAIL] El ajuste falló.")
            elif key == ord('d'):
                print("\n[Comando] Desactivando modo autónomo...")
                camara.ser.write(b'D')
            elif key == ord('e'):
                print("\n[Comando] Activando modo autónomo...")
                camara.ser.write(b'E')
                
    except KeyboardInterrupt:
        pass
    finally:
        camara.liberar()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
