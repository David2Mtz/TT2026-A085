import cv2
import numpy as np
import sys
import os
from dotenv import load_dotenv

# Configurar rutas para importar módulos locales
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.flujo_camara import CameraSerial
from constants.config import OFFSET_X, OFFSET_Y

load_dotenv()

PUERTO_CAMARA = os.getenv('PUERTO_CAMARA', '/dev/ttyUSB1')

def nothing(x):
    pass

def main():
    print("--- DEMO INTERACTIVO: CALIBRACIÓN DE VISOR DE AGARRE ---")
    print("Usa los trackbars para ajustar la posición y tamaño del visor.")
    print("Presiona 's' para guardar (simulado) o 'q' para salir.")

    camara = CameraSerial(port=PUERTO_CAMARA, baud_rate=460800)
    
    cv2.namedWindow('Calibracion Visor')
    
    # Crear trackbars
    # Offset X respecto al centro
    cv2.createTrackbar('Offset X', 'Calibracion Visor', 100, 200, nothing) # 100 es 0
    # Offset Y respecto al centro
    cv2.createTrackbar('Offset Y', 'Calibracion Visor', 40, 200, nothing)  # 100 es 0
    # Tamaño del gap (mitad del lado del cuadrado)
    cv2.createTrackbar('Tamano (Gap)', 'Calibracion Visor', 35, 100, nothing)
    # Largo de las líneas de las esquinas
    cv2.createTrackbar('Largo Lineas', 'Calibracion Visor', 15, 50, nothing)

    try:
        while True:
            frame = camara.get_frame()
            if frame is None:
                continue

            alto, ancho = frame.shape[:2]
            cx_pantalla = (ancho // 2) + OFFSET_X
            cy_pantalla = (alto // 2) + OFFSET_Y

            # Obtener valores de trackbars
            off_x = cv2.getTrackbarPos('Offset X', 'Calibracion Visor') - 100
            off_y = cv2.getTrackbarPos('Offset Y', 'Calibracion Visor') - 100
            gap = cv2.getTrackbarPos('Tamano (Gap)', 'Calibracion Visor')
            l_len = cv2.getTrackbarPos('Largo Lineas', 'Calibracion Visor')

            target_x = cx_pantalla + off_x
            target_y = cy_pantalla + off_y

            # Dibujar centro de pinza (Referencia)
            cv2.circle(frame, (cx_pantalla, cy_pantalla), 5, (255, 0, 0), -1)
            cv2.putText(frame, "Punto Ciego Pinza", (cx_pantalla + 10, cy_pantalla), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)

            # Dibujar Visor
            c_visor = (0, 255, 255) # Amarillo
            # Esquinas
            cv2.line(frame, (target_x - gap, target_y - gap), (target_x - gap, target_y - gap + l_len), c_visor, 2)
            cv2.line(frame, (target_x - gap, target_y + gap), (target_x - gap, target_y + gap - l_len), c_visor, 2)
            cv2.line(frame, (target_x + gap, target_y - gap), (target_x + gap, target_y - gap + l_len), c_visor, 2)
            cv2.line(frame, (target_x + gap, target_y + gap), (target_x + gap, target_y + gap - l_len), c_visor, 2)
            
            cv2.line(frame, (target_x - gap, target_y - gap), (target_x - gap + l_len, target_y - gap), c_visor, 2)
            cv2.line(frame, (target_x + gap, target_y - gap), (target_x + gap - l_len, target_y - gap), c_visor, 2)
            cv2.line(frame, (target_x - gap, target_y + gap), (target_x - gap + l_len, target_y + gap), c_visor, 2)
            cv2.line(frame, (target_x + gap, target_y + gap), (target_x + gap - l_len, target_y + gap), c_visor, 2)

            # Info en pantalla
            cv2.putText(frame, f"Target: ({off_x}, {off_y}) | Gap: {gap}", (10, alto - 20), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            cv2.imshow('Calibracion Visor', frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                print(f"\n--- VALORES CALIBRADOS ---")
                print(f"target_x = cx_pantalla + ({off_x})")
                print(f"target_y = cy_pantalla + ({off_y})")
                print(f"gap = {gap}")
                print(f"l_len = {l_len}")
                print("--------------------------\n")

    finally:
        camara.liberar()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
