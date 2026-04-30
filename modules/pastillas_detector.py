# modules/pastillas_detector.py
import cv2
import numpy as np
from constants.config import OFFSET_X, OFFSET_Y

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

def process_pastillas_frame(frame, color_base, offset_y=OFFSET_Y, offset_x=OFFSET_X, dist_actual=999):
    """
    Recibe un frame de la ESP32-CAM.
    dist_actual: Se usa para activar el 'Modo Lupa' a corta distancia.
    """
    alto, ancho = frame.shape[:2]
    # El centro objetivo (donde está la pinza físicamente)
    cx_pantalla, cy_pantalla = (ancho // 2) + offset_x, (alto // 2) + offset_y
    
    hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    error_tracking = None

    # --- DIBUJAR REFERENCIA DE PINZA (AZUL) ---
    cv2.circle(frame, (cx_pantalla, cy_pantalla), 8, (255, 0, 0), -1)

    # --- DECIDIR MODO DE SEGMENTACIÓN ---
    # Si estamos a menos de 130mm, usamos el 'Modo Lupa'
    if dist_actual < 100:
        # Siempre buscamos alrededor de la pinza (donde queremos llevar la pastilla)
        roi_size = 200 # ROI más grande para no perderla
        x1 = max(0, cx_pantalla - roi_size // 2)
        y1 = max(0, cy_pantalla - roi_size // 2)
        x2 = min(ancho, cx_pantalla + roi_size // 2)
        y2 = min(alto, cy_pantalla + roi_size // 2)
        
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
        cv2.putText(frame, "MODO LUPA (PINZA)", (x1, y1 - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        
        # Segmentación solo en el ROI
        hsv_roi = hsv_frame[y1:y2, x1:x2]
        ranges = get_hsv_ranges(color_base)
        mask_base = cv2.inRange(hsv_roi, ranges[0][0], ranges[0][1])
        if len(ranges) > 1:
            mask_base = cv2.add(mask_base, cv2.inRange(hsv_roi, ranges[1][0], ranges[1][1]))
        
        # La pastilla es "lo que no es base"
        mask_pastilla = cv2.bitwise_not(mask_base)
        kernel = np.ones((5, 5), np.uint8)
        mask_pastilla = cv2.morphologyEx(mask_pastilla, cv2.MORPH_OPEN, kernel)
        
        contours, _ = cv2.findContours(mask_pastilla, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        pills = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            # Aumentamos área máxima a 25000 porque de cerca se ve muy grande
            if 150 < area < 25000:
                M = cv2.moments(cnt)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"]) + x1
                    cy = int(M["m01"] / M["m00"]) + y1
                    dist_al_centro = np.sqrt((cx - cx_pantalla)**2 + (cy - cy_pantalla)**2)
                    pills.append((cnt, cx, cy, area, dist_al_centro))
        
        if pills:
            # Seleccionamos la que esté más cerca del centro físico de la pinza
            best = min(pills, key=lambda x: x[4])
            error_tracking = (best[1] - cx_pantalla, best[2] - cy_pantalla, best[3])
            
            # Dibujar seguimiento
            (x_c, y_c, w_c, h_c) = cv2.boundingRect(best[0])
            cv2.rectangle(frame, (x_c + x1, y_c + y1), (x_c + x1 + w_c, y_c + y1 + h_c), (0, 255, 0), 2)
            cv2.circle(frame, (best[1], best[2]), 5, (0, 0, 255), -1)

    else:
        # --- MODO NORMAL (SIN CAMBIOS) ---
        base_contour, base_color_mask = find_base(hsv_frame, color_base)
        if base_contour is not None:
            cv2.drawContours(frame, [base_contour], -1, (0, 255, 0), 2)
            moi_mask = np.zeros(hsv_frame.shape[:2], dtype="uint8")
            cv2.drawContours(moi_mask, [base_contour], -1, 255, -1) 
            pills_mask = cv2.subtract(moi_mask, base_color_mask)
            kernel = np.ones((3, 3), np.uint8)
            pills_mask = cv2.morphologyEx(pills_mask, cv2.MORPH_OPEN, kernel, iterations=2)
            contours, _ = cv2.findContours(pills_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if contours:
                pill_contours = [c for c in contours if cv2.contourArea(c) > 150]
                if pill_contours:
                    selected_pill = max(pill_contours, key=cv2.contourArea)
                    M = cv2.moments(selected_pill)
                    if M["m00"] != 0:
                        cx_p, cy_p = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
                        error_tracking = (cx_p - cx_pantalla, cy_p - cy_pantalla, M["m00"])
                        cv2.drawContours(frame, [selected_pill], -1, (0, 0, 255), 2)

    # Dibujar línea de error si hay objetivo
    if error_tracking:
        cv2.line(frame, (cx_pantalla, cy_pantalla), 
                 (cx_pantalla + error_tracking[0], cy_pantalla + error_tracking[1]), (0, 255, 255), 2)

    return frame, error_tracking

    # Dibujar línea de error si hay objetivo
    if error_tracking:
        cv2.line(frame, (cx_pantalla, cy_pantalla), 
                 (cx_pantalla + error_tracking[0], cy_pantalla + error_tracking[1]), (0, 255, 255), 2)

    return frame, error_tracking