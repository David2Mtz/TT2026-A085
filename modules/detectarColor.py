# modules/detectarColor.py
import cv2
import numpy as np

def get_present_colors(frame):
    """
    Analiza el frame completo y devuelve una lista de colores detectados
    y un diccionario con las coordenadas (x, y) de cada color.
    """
    height, width = frame.shape[:2]
    total_pixels = height * width
    min_pixel_threshold = total_pixels * 0.002 # Bajamos a 0.2% para mayor sensibilidad
    
    # Suavizado para reducir ruido
    frame_blur = cv2.GaussianBlur(frame, (5, 5), 0)
    hsv = cv2.cvtColor(frame_blur, cv2.COLOR_BGR2HSV)
    
    detected_colors = []
    color_info = {} # Guardará { "Color": (x, y) }
    
    # Definición de rangos más inclusivos (coincidentes con pastillas_detector.py)
    min_sat = 40
    min_val = 40
    
    ranges = {
        "Rojo": [
            (np.array([0, min_sat, min_val]), np.array([10, 255, 255])),
            (np.array([170, min_sat, min_val]), np.array([180, 255, 255]))
        ],
        "Verde": [(np.array([35, min_sat, min_val]), np.array([90, 255, 255]))],
        "Azul": [(np.array([90, min_sat, min_val]), np.array([145, 255, 255]))]
    }
    
    for color_name, color_ranges in ranges.items():
        mask = None
        for (lower, upper) in color_ranges:
            curr_mask = cv2.inRange(hsv, lower, upper)
            if mask is None: mask = curr_mask
            else: mask = cv2.add(mask, curr_mask)
        
        count = cv2.countNonZero(mask)
        if count > min_pixel_threshold:
            detected_colors.append(color_name)
            
            # Dibujar contorno y obtener centro
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
                M = cv2.moments(largest)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    color_info[color_name] = (cx, cy)
                
                x, y, w, h = cv2.boundingRect(largest)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
                cv2.putText(frame, f"Detectado: {color_name}", (x, y - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                
    return frame, detected_colors, color_info

def process_color_frame(frame):
    return get_present_colors(frame)
