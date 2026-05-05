# modules/pastillas_detector.py
import cv2
import numpy as np
from constants.config import OFFSET_X, OFFSET_Y

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

def process_pastillas_frame(frame, color_base, offset_y=OFFSET_Y, offset_x=OFFSET_X, dist_actual=999):
    """
    Lógica de detección de pastillas por sustracción con filtro de reflejos.
    """
    alto, ancho = frame.shape[:2]
    cx_pantalla, cy_pantalla = (ancho // 2) + offset_x, (alto // 2) + offset_y
    
    hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    error_tracking = None

    # --- DIBUJAR REFERENCIA DE PINZA (AZUL) ---
    cv2.circle(frame, (cx_pantalla, cy_pantalla), 8, (255, 0, 0), -1)

    base_contour, base_color_mask = find_base(hsv_frame, color_base)
    
    if base_contour is not None:
        cv2.drawContours(frame, [base_contour], -1, (0, 255, 0), 2)
        
        moi_mask = np.zeros(hsv_frame.shape[:2], dtype="uint8")
        cv2.drawContours(moi_mask, [base_contour], -1, 255, -1) 
        pills_mask = cv2.subtract(moi_mask, base_color_mask)
        
        # FILTRO DE REFLEJOS
        _, s_plane, v_plane = cv2.split(hsv_frame)
        reflejos = cv2.bitwise_and(
            cv2.threshold(s_plane, 70, 255, cv2.THRESH_BINARY_INV)[1],
            cv2.threshold(v_plane, 200, 255, cv2.THRESH_BINARY)[1]
        )
        pills_mask = cv2.subtract(pills_mask, reflejos)

        kernel = np.ones((5, 5), np.uint8)
        pills_mask = cv2.morphologyEx(pills_mask, cv2.MORPH_OPEN, kernel, iterations=2)
        pills_mask = cv2.morphologyEx(pills_mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        
        contours, _ = cv2.findContours(pills_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            pill_contours = [c for c in contours if cv2.contourArea(c) > 150]
            if pill_contours:
                selected_pill = max(pill_contours, key=cv2.contourArea)
                M = cv2.moments(selected_pill)
                if M["m00"] != 0:
                    cx_p, cy_p = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
                    error_tracking = (cx_p - cx_pantalla, cy_p - cy_pantalla, cv2.contourArea(selected_pill))
                    
                    cv2.drawContours(frame, [selected_pill], -1, (0, 0, 255), 2)
                    cv2.circle(frame, (cx_p, cy_p), 5, (0, 0, 255), -1)
                    cv2.line(frame, (cx_pantalla, cy_pantalla), (cx_p, cy_p), (0, 255, 255), 2)

    return frame, error_tracking

def iniciar_deteccion(camara):
    """ Ajusta el brillo del LED para la fase de búsqueda de pastillas (48) """
    print("[DETECTOR PASTILLAS] Ajustando iluminación: 48")
    camara.set_led_brightness(48)

def finalizar_deteccion(camara):
    """ Apaga el LED al terminar la recolección (0) """
    print("[DETECTOR PASTILLAS] Restaurando iluminación: 0")
    camara.set_led_brightness(0)
