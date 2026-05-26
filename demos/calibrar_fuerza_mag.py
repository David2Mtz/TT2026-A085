# demos/calibrar_fuerza_mag.py
import sys
import os
import cv2
import time
import numpy as np
from dotenv import load_dotenv

# Ruta para importar módulos desde la raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.arm_controller import ArmController
from constants.config import PIN_PINZA, PIN_BASE

load_dotenv()

PUERTO_BRAZO = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')

def main():
    print("--- HERRAMIENTA DE CALIBRACIÓN DE FUERZA (ISO 13482) ---")
    print("Objetivo: Relacionar el Delta de Magnetómetro (uT) con la Fuerza (N)")
    print("\nInstrucciones:")
    print("1. Coloca un objeto (o báscula) en la pinza.")
    print("2. Cierra la pinza lentamente con 'S' hasta alcanzar la presión deseada.")
    print("3. Anota el valor de 'DELTA MAG' para usarlo como límite de 75N.")
    
    try:
        brazo = ArmController(puerto=PUERTO_BRAZO, baudios=115200)
    except Exception as e:
        print(f"[ERROR] No se pudo conectar al brazo: {e}")
        return

    # Posición inicial: Pinza abierta, brazo en reposo
    print("\nPreparando posición de prueba...")
    brazo.mover_a_estado("HOME", esperar=True)
    
    # Variables de monitoreo
    baseline_mag = None
    angulo_pinza = 80
    
    # Crear ventana para visualización de datos
    cv2.namedWindow("Calibrador de Fuerza")
    display = np.zeros((400, 600, 3), dtype=np.uint8)

    try:
        while True:
            # Obtener datos del magnetómetro
            m = brazo.mag1
            norma_actual = (m[0]**2 + m[1]**2 + m[2]**2)**0.5
            
            if baseline_mag is None:
                baseline_mag = norma_actual

            delta = abs(norma_actual - baseline_mag)

            # --- UI ---
            display.fill(0)
            cv2.putText(display, f"Angulo Pinza: {angulo_pinza}", (20, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            
            color_delta = (0, 255, 0) if delta < 50 else (0, 255, 255) if delta < 150 else (0, 0, 255)
            cv2.putText(display, f"DELTA MAG: {delta:.2f} uT", (20, 100), 
                        cv2.FONT_HERSHEY_DUPLEX, 1.0, color_delta, 2)
            
            cv2.putText(display, "CONTROLES:", (20, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
            cv2.putText(display, "[W] Abrir Pinza (+5)", (40, 230), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.putText(display, "[S] Cerrar Pinza (-1) - MAS PRESION", (40, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.putText(display, "[R] Reset Baseline (Poner a 0 con pinza vacia)", (40, 290), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.putText(display, "[Q] Salir", (40, 320), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)

            cv2.imshow("Calibrador de Fuerza", display)
            
            key = cv2.waitKey(50) & 0xFF
            
            if key == ord('q'):
                break
            elif key == ord('w'):
                angulo_pinza = min(90, angulo_pinza + 5)
                brazo.mover_tiempo([(PIN_PINZA, angulo_pinza)], esperar=False)
            elif key == ord('s'):
                angulo_pinza = max(0, angulo_pinza - 1)
                brazo.mover_tiempo([(PIN_PINZA, angulo_pinza)], esperar=False)
                print(f"Cerrando... Angulo: {angulo_pinza} | Delta: {delta:.2f} uT")
            elif key == ord('r'):
                baseline_mag = norma_actual
                print("Baseline reseteado.")

    except KeyboardInterrupt:
        pass
    finally:
        brazo.mover_tiempo([(PIN_PINZA, 80)], esperar=True)
        brazo.cerrar()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
