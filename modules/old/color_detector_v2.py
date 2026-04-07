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
    Recibe un frame en crudo, aplica la detección de color en el centro,
    dibuja los resultados y devuelve el frame modificado.
    """
    height, width, _ = frame.shape
    roi_size = 100
    roi_half = roi_size // 2
    roi_area = roi_size * roi_size 

    x1 = (width // 2) - roi_half
    y1 = (height // 2) - roi_half
    x2 = (width // 2) + roi_half
    y2 = (height // 2) + roi_half

    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), 2)
    roi = frame[y1:y2, x1:x2]
    
    # Aplicar un ligero desenfoque para mitigar artefactos del JPEG antes de pasar a HSV
    roi_suavizado = cv2.GaussianBlur(roi, (5, 5), 0)
    hsv_roi = cv2.cvtColor(roi_suavizado, cv2.COLOR_BGR2HSV)
    
    color_name = get_color_name(hsv_roi, roi_area)

    cv2.putText(frame, color_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

    return frame