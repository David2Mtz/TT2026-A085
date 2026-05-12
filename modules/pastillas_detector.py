# modules/pastillas_detector.py
import cv2
import numpy as np
from constants.config import OFFSET_X, OFFSET_Y

def get_hsv_ranges(color_name):
    min_saturation = 45
    min_value = 35
    ranges = {}
    
    lower_red1 = np.array([0, min_saturation, min_value])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, min_saturation, min_value])
    upper_red2 = np.array([180, 255, 255])
    ranges['rojo'] = ((lower_red1, upper_red1), (lower_red2, upper_red2))

    lower_green = np.array([35, min_saturation, min_value])
    upper_green = np.array([90, 255, 255])
    ranges['verde'] = ((lower_green, upper_green),)

    lower_blue = np.array([90, min_saturation, min_value])
    upper_blue = np.array([140, 255, 255])
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

def process_pastillas_frame(frame, color_base, offset_y=OFFSET_Y, offset_x=OFFSET_X):
    alto, ancho = frame.shape[:2]
    cx_p, cy_p = (ancho // 2) + offset_x, (alto // 2) + offset_y
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    error_tracking = None

    # 1. Detectar Base
    ranges = get_hsv_ranges(color_base)
    if not ranges: return frame, None
    
    mask_base = cv2.inRange(hsv, ranges[0][0], ranges[0][1])
    if len(ranges) > 1: mask_base = cv2.add(mask_base, cv2.inRange(hsv, ranges[1][0], ranges[1][1]))
    
    # 2. Refinar máscara de base (eliminar ruido)
    kernel = np.ones((5, 5), np.uint8)
    mask_base = cv2.morphologyEx(mask_base, cv2.MORPH_OPEN, kernel)
    
    # 3. Identificar objetos sobre la base (sustracción)
    # Creamos un área de interés (el contorno más grande de la base)
    cnts_base, _ = cv2.findContours(mask_base, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if cnts_base:
        base_cnt = max(cnts_base, key=cv2.contourArea)
        roi_mask = np.zeros_like(mask_base)
        cv2.drawContours(roi_mask, [base_cnt], -1, 255, -1)
        
        # Lo que está en la ROI pero NO es el color de la base es una pastilla/sombra
        pills_mask = cv2.subtract(roi_mask, mask_base)
        
        # Refinar máscara de pastillas
        pills_mask = cv2.morphologyEx(pills_mask, cv2.MORPH_OPEN, kernel)
        pills_mask = cv2.morphologyEx(pills_mask, cv2.MORPH_DILATE, kernel)

        # 4. Filtrar por Circularidad (Evita sombras irregulares)
        cnts_pills, _ = cv2.findContours(pills_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_pills = []
        for c in cnts_pills:
            area = cv2.contourArea(c)
            perimetro = cv2.arcLength(c, True)
            if perimetro == 0 or area < 80: continue # Bajamos un poco el área mínima
            
            circularidad = (4 * np.pi * area) / (perimetro ** 2)
            if circularidad > 0.50: # Umbral relajado para comprimidos (antes 0.65)
                valid_pills.append(c)

        if valid_pills:
            best_pill = max(valid_pills, key=cv2.contourArea)
            M = cv2.moments(best_pill)
            if M["m00"] != 0:
                px, py = int(M["m10"]/M["m00"]), int(M["m01"]/M["m00"])
                error_tracking = (px - cx_p, py - cy_p, cv2.contourArea(best_pill))
                cv2.drawContours(frame, [best_pill], -1, (0, 0, 255), 2)
                cv2.circle(frame, (px, py), 5, (0, 0, 255), -1)

    cv2.circle(frame, (cx_p, cy_p), 8, (255, 0, 0), -1)
    return frame, error_tracking

def iniciar_deteccion(camara):
    """ Ajusta el brillo del LED para la fase de búsqueda de pastillas (48) """
    print("[DETECTOR PASTILLAS] Ajustando iluminación: 48")
    camara.set_led_brightness(48)

def finalizar_deteccion(camara):
    """ Apaga el LED al terminar la recolección (0) """
    print("[DETECTOR PASTILLAS] Restaurando iluminación: 0")
    camara.set_led_brightness(0)
