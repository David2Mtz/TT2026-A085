# modules/color_detector_v2.py
import cv2
import numpy as np

def get_color_name(hsv_roi, roi_area):
    min_saturation = 70  
    min_value = 60       
    min_pixel_percent = 0.20 

    lower_red1 = np.array([0, min_saturation, min_value])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, min_saturation, min_value])
    upper_red2 = np.array([180, 255, 255])

    lower_green = np.array([40, min_saturation, min_value])
    upper_green = np.array([85, 255, 255]) 

    lower_blue = np.array([95, min_saturation, min_value])
    upper_blue = np.array([135, 255, 255]) 

    mask_red1 = cv2.inRange(hsv_roi, lower_red1, upper_red1)
    mask_red2 = cv2.inRange(hsv_roi, lower_red2, upper_red2)
    mask_red = cv2.add(mask_red1, mask_red2) 
    
    mask_green = cv2.inRange(hsv_roi, lower_green, upper_green)
    mask_blue = cv2.inRange(hsv_roi, lower_blue, upper_blue)

    red_pixels = cv2.countNonZero(mask_red)
    green_pixels = cv2.countNonZero(mask_green)
    blue_pixels = cv2.countNonZero(mask_blue)

    colors = {"Rojo": red_pixels, "Verde": green_pixels, "Azul": blue_pixels}
    
    if not colors: 
        return "Desconocido"

    winner_name = max(colors, key=colors.get)
    winner_pixels = colors[winner_name]

    min_pixels = roi_area * min_pixel_percent
    
    if winner_pixels > min_pixels:
        return winner_name
    else:
        return "Desconocido"

def process_color_frame(frame):
    """
    Recibe un frame, aplica la detección de color en 3 zonas (Izquierda, Centro, Derecha),
    dibuja los resultados y devuelve (frame_modificado, arreglo_colores).
    """
    height, width, _ = frame.shape
    
    # Definir dimensiones basadas en proporciones (ej: 15% del ancho para el cuadro)
    roi_size = int(width * 0.15)
    gap = int(width * 0.10)
    
    roi_half = roi_size // 2
    roi_area = roi_size * roi_size 

    # Puntos centrales
    cx = width // 2
    cy = height // 2

    # Coordenadas Y (iguales para los 3 cuadros)
    y1 = cy - roi_half
    y2 = cy + roi_half

    # Coordenadas X para cada cuadro
    # Centro (Índice 1)
    cx1 = cx - roi_half
    cx2 = cx + roi_half

    # Izquierda (Índice 0)
    lx1 = cx1 - gap - roi_size
    lx2 = cx1 - gap

    # Derecha (Índice 2)
    rx1 = cx2 + gap
    rx2 = cx2 + gap + roi_size

    # Lista de configuraciones de los cuadros (x1, x2)
    cuadros = [
        (lx1, lx2), # Posición 0: Izquierda
        (cx1, cx2), # Posición 1: Centro
        (rx1, rx2)  # Posición 2: Derecha
    ]

    colores_detectados = []

    for idx, (x1, x2) in enumerate(cuadros):
        # Validar que el cuadro no se salga del tamaño del frame de la cámara
        if x1 < 0 or x2 > width or y1 < 0 or y2 > height:
            colores_detectados.append("Fuera de Limites")
            continue

        # Dibujar cuadro
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), 2)
        
        # Extraer región de interés
        roi = frame[y1:y2, x1:x2]
        
        # Procesamiento
        roi_suavizado = cv2.GaussianBlur(roi, (5, 5), 0)
        hsv_roi = cv2.cvtColor(roi_suavizado, cv2.COLOR_BGR2HSV)
        
        color_name = get_color_name(hsv_roi, roi_area)
        colores_detectados.append(color_name)

        # Imprimir el nombre del color sobre su cuadro respectivo
        cv2.putText(frame, color_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    return frame, colores_detectados