# demos/demo_pastillas.py
import sys
import os
import cv2
import time
from dotenv import load_dotenv

# Agregamos la ruta raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.flujo_camara import CameraSerial
from modules.arm_controller import ArmController
from modules.pastillas_detector import process_pastillas_frame

# Cargar variables de entorno
load_dotenv()

def main():
    print("\n" + "="*50)
    print("--- INICIANDO DEMO: Centrado de Pastilla (IBVS) ---")
    print("="*50)
    print("Pasos:\n1. Mover brazo a OBSERVACION\n2. Iniciar cámara\n3. Centrar color azul")
    print("\nPresiona 'q' para salir.\n")
    
    # Configuración de puertos
    puerto_camara = os.getenv('PUERTO_CAMARA', '/dev/cu.usbserial-2110')
    puerto_brazo = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
    color_objetivo = "azul"

    # 1. Inicialización del Brazo primero
    try:
        brazo = ArmController(puerto=puerto_brazo, baudios=9600)
        
        print("\n[INFO] Moviendo brazo a posición de OBSERVACION...")
        brazo.mover_a_estado("OBSERVACION")
        print("[INFO] Brazo en posición. Esperando 2s para estabilización...")
        time.sleep(2)
    except Exception as e:
        print(f"[ERROR] No se pudo inicializar el brazo: {e}")
        return

    # 2. Inicialización de la cámara después de llegar
    try:
        print("\n[INFO] Iniciando cámara...")
        camara = CameraSerial(port=puerto_camara, baud_rate=460800)
        print("[INFO] Cámara lista.")
    except Exception as e:
        print(f"[ERROR] No se pudo conectar a la cámara: {e}")
        brazo.cerrar()
        return

    objetivo_centrado = False

    try:
        while True:
            frame = camara.get_frame()
            if frame is None:
                continue

            frame_vis = frame.copy()

            if not objetivo_centrado:
                # 3. Procesar búsqueda de pastilla
                frame_vis, error = process_pastillas_frame(frame_vis, color_objetivo)
                
                if error:
                    # 4. Ejecutar centrado visual
                    # centrado_ok será True cuando el error esté dentro de la tolerancia
                    centrado_ok = brazo.centrar_ibvs(error[0], error[1])
                    
                    if centrado_ok:
                        print(f"\n[¡ÉXITO!] Pastilla {color_objetivo} centrada perfectamente.")
                        print("[INFO] El brazo se mantendrá estático. Presiona 'q' para terminar.")
                        objetivo_centrado = True
                else:
                    cv2.putText(frame_vis, f"Buscando pastilla {color_objetivo}...", (10, 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            else:
                # Una vez centrado, solo mostramos el feed
                cv2.putText(frame_vis, "OBJETIVO CENTRADO", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # Mostrar resultado
            cv2.imshow('DEMO - Centrado de Pastilla', frame_vis)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("\nEjecución detenida por el usuario.")
    finally:
        print("\n[INFO] Cerrando recursos...")
        if 'camara' in locals():
            camara.liberar()
        if 'brazo' in locals():
            brazo.mover_a_estado("HOME")
            brazo.cerrar()
        cv2.destroyAllWindows()
        print("[INFO] Demo finalizado.")

if __name__ == '__main__':
    main()
