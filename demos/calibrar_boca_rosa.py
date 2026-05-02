import cv2
import numpy as np
import sys
import os
from dotenv import load_dotenv

# Configurar rutas para importar módulos locales
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.flujo_camara import CameraSerial

load_dotenv()

PUERTO_CAMARA = os.getenv('PUERTO_CAMARA', '/dev/ttyUSB1')

def nothing(x):
    pass

# Variables globales para los rangos
h_min, s_min, v_min = 140, 100, 100
h_max, s_max, v_max = 170, 255, 255

def click_event(event, x, y, flags, param):
    global h_min, s_min, v_min, h_max, s_max, v_max
    if event == cv2.EVENT_LBUTTONDOWN:
        frame = param
        # Obtener el color del pixel clickeado (BGR)
        pixel = frame[y, x]
        # Convertir a HSV
        hsv_pixel = cv2.cvtColor(np.uint8([[pixel]]), cv2.COLOR_BGR2HSV)[0][0]
        
        h, s, v = hsv_pixel
        print(f"Pixel clickeado - HSV: {h}, {s}, {v}")
        
        # Definir rangos con una tolerancia
        h_min = max(0, h - 10)
        h_max = min(180, h + 10)
        s_min = max(50, s - 50)
        s_max = 255
        v_min = max(50, v - 50)
        v_max = 255
        
        # Actualizar posiciones de los trackbars
        cv2.setTrackbarPos('H Min', 'Configuracion Rosa', h_min)
        cv2.setTrackbarPos('H Max', 'Configuracion Rosa', h_max)
        cv2.setTrackbarPos('S Min', 'Configuracion Rosa', s_min)
        cv2.setTrackbarPos('S Max', 'Configuracion Rosa', s_max)
        cv2.setTrackbarPos('V Min', 'Configuracion Rosa', v_min)
        cv2.setTrackbarPos('V Max', 'Configuracion Rosa', v_max)

def main():
    global h_min, s_min, v_min, h_max, s_max, v_max
    print("--- CALIBRADOR INTELIGENTE (CLICK-TO-COLOR) ---")
    print("1. HAZ CLICK en un punto rosa del maniquí en la ventana 'Frame Original'.")
    print("2. El sistema detectará el color automáticamente.")
    print("3. Ajusta los sliders si es necesario para limpiar la máscara.")
    print("Presiona 'q' para salir.")

    camara = CameraSerial(port=PUERTO_CAMARA, baud_rate=460800)
    
    cv2.namedWindow('Configuracion Rosa', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Configuracion Rosa', 600, 600)
    cv2.namedWindow('Frame Original')
    
    # Vincular evento del mouse
    # El frame se pasará dinámicamente en el bucle
    
    cv2.createTrackbar('H Min', 'Configuracion Rosa', h_min, 180, nothing)
    cv2.createTrackbar('H Max', 'Configuracion Rosa', h_max, 180, nothing)
    cv2.createTrackbar('S Min', 'Configuracion Rosa', s_min, 255, nothing)
    cv2.createTrackbar('S Max', 'Configuracion Rosa', s_max, 255, nothing)
    cv2.createTrackbar('V Min', 'Configuracion Rosa', v_min, 255, nothing)
    cv2.createTrackbar('V Max', 'Configuracion Rosa', v_max, 255, nothing)

    try:
        while True:
            frame = camara.get_frame()
            if frame is None:
                continue

            # Actualizar el parámetro del callback con el frame actual
            cv2.setMouseCallback('Frame Original', click_event, frame)

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            # Leer trackbars (por si el usuario los mueve manualmente)
            h_min = cv2.getTrackbarPos('H Min', 'Configuracion Rosa')
            h_max = cv2.getTrackbarPos('H Max', 'Configuracion Rosa')
            s_min = cv2.getTrackbarPos('S Min', 'Configuracion Rosa')
            s_max = cv2.getTrackbarPos('S Max', 'Configuracion Rosa')
            v_min = cv2.getTrackbarPos('V Min', 'Configuracion Rosa')
            v_max = cv2.getTrackbarPos('V Max', 'Configuracion Rosa')

            lower = np.array([h_min, s_min, v_min])
            upper = np.array([h_max, s_max, v_max])

            mask = cv2.inRange(hsv, lower, upper)
            
            # Limpieza morfológica
            kernel = np.ones((5,5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            
            # Aplicar máscara al frame para ver resultado
            res = cv2.bitwise_and(frame, frame, mask=mask)

            # Mostrar ventanas
            cv2.imshow('Configuracion Rosa', mask)
            cv2.imshow('Resultado (Color)', res)
            cv2.imshow('Frame Original', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                print(f"\n--- RANGOS ENCONTRADOS ---")
                print(f"Lower: [{h_min}, {s_min}, {v_min}]")
                print(f"Upper: [{h_max}, {s_max}, {v_max}]")
                break

    finally:
        camara.liberar()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
