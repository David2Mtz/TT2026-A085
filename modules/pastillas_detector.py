# modules/pastillas_detector.py
import cv2
import numpy as np

# Se mantienen tus rangos HSV
def get_hsv_ranges(color_name):
    min_saturation = 70
    min_value = 60
    ranges = {}
    
    lower_red1 = np.array([0, min_saturation, min_value])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, min_saturation, min_value])
    upper_red2 = np.array([180, 255, 255])
    ranges['rojo'] = ((lower_red1, upper_red1), (lower_red2, upper_red2))

    lower_green = np.array([40, min_saturation, min_value])
    upper_green = np.array([85, 255, 255])
    ranges['verde'] = ((lower_green, upper_green),)

    lower_blue = np.array([95, min_saturation, min_value])
    upper_blue = np.array([135, 255, 255])
    ranges['azul'] = ((lower_blue, upper_blue),)
    
    return ranges.get(color_name.lower())

def find_base(hsv_frame, base_color_name):
    ranges = get_hsv_ranges(base_color_name)
    if not ranges: return None, None 

    mask = cv2.inRange(hsv_frame, ranges[0][0], ranges[0][1])
    if len(ranges) > 1: 
        mask2 = cv2.inRange(hsv_frame, ranges[1][0], ranges[1][1])
        mask = cv2.add(mask, mask2)
        
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    base_color_mask = mask.copy()

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours: return None, None 

    largest_contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest_contour) < 5000: return None, None
        
    return largest_contour, base_color_mask

def process_pastillas_frame(frame, color_base):
    """
    Recibe un frame de la ESP32-CAM.
    Retorna el frame anotado y la tupla de error (error_x, error_y) desde el centro.
    """
    alto, ancho = frame.shape[:2]
    cx_pantalla, cy_pantalla = ancho // 2, alto // 2
    
    hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    base_contour, base_color_mask = find_base(hsv_frame, color_base)
    
    error_tracking = None

    # Dibujar cruz central (Punto ciego de la pinza)
    cv2.line(frame, (cx_pantalla, 0), (cx_pantalla, alto), (255, 0, 0), 1)
    cv2.line(frame, (0, cy_pantalla), (ancho, cy_pantalla), (255, 0, 0), 1)

    if base_contour is not None:
        cv2.drawContours(frame, [base_contour], -1, (0, 255, 0), 2)
        
        moi_mask = np.zeros(hsv_frame.shape[:2], dtype="uint8")
        cv2.drawContours(moi_mask, [base_contour], -1, 255, -1) 
        pills_mask = cv2.subtract(moi_mask, base_color_mask)

        kernel = np.ones((3, 3), np.uint8)
        pills_mask = cv2.morphologyEx(pills_mask, cv2.MORPH_OPEN, kernel, iterations=2)
        pills_mask = cv2.morphologyEx(pills_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(pills_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            pill_contours = [c for c in contours if cv2.contourArea(c) > 150]
            if pill_contours:
                selected_pill = max(pill_contours, key=cv2.contourArea)
                M = cv2.moments(selected_pill)
                
                if M["m00"] != 0:
                    cx_pastilla = int(M["m10"] / M["m00"])
                    cy_pastilla = int(M["m01"] / M["m00"])
                    
                    # Calcular error relativo al centro
                    error_x = cx_pastilla - cx_pantalla
                    error_y = cy_pastilla - cy_pantalla
                    error_tracking = (error_x, error_y)
                    
                    # Dibujar rastreo
                    (x, y, w, h) = cv2.boundingRect(selected_pill)
                    cv2.drawContours(frame, [selected_pill], -1, (0, 0, 255), 2)
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
                    
                    # Línea desde el centro a la pastilla
                    cv2.line(frame, (cx_pantalla, cy_pantalla), (cx_pastilla, cy_pastilla), (0, 255, 255), 2)
                    
                    # Mostrar error en pantalla
                    texto_err = f"Err X:{error_x} Y:{error_y}"
                    cv2.putText(frame, texto_err, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    return frame, error_tracking