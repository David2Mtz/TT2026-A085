# modules/detectarColor.py
import cv2
import numpy as np

def get_present_colors(frame):
    """
    Analiza el frame completo y devuelve una lista de colores detectados
    que superan un umbral mínimo de píxeles.
    """
    height, width = frame.shape[:2]
    total_pixels = height * width
    min_pixel_threshold = total_pixels * 0.01 # Al menos 1% de la imagen
    
    # Suavizado para reducir ruido
    frame_blur = cv2.GaussianBlur(frame, (5, 5), 0)
    hsv = cv2.cvtColor(frame_blur, cv2.COLOR_BGR2HSV)
    
    detected_colors = []
    
    # Definición de rangos
    ranges = {
        "Rojo": [
            (np.array([0, 120, 70]), np.array([10, 255, 255])),
            (np.array([170, 120, 70]), np.array([180, 255, 255]))
        ],
        "Verde": [(np.array([40, 70, 70]), np.array([85, 255, 255]))],
        "Azul": [(np.array([95, 70, 70]), np.array([135, 255, 255]))]
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
            
            # Dibujar contorno para feedback visual si se encuentra
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
                cv2.putText(frame, f"Detectado: {color_name}", (x, y - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                
    return frame, detected_colors

def process_color_frame(frame):
    # Función puente para mantener compatibilidad con ciclo_completo.py
    return get_present_colors(frame)
