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
    # Si estamos a menos de 125mm (antes 115), usamos el 'Seguimiento Cercano'
    if dist_actual < 125:
        # EL OBJETIVO VISUAL: Donde queremos que la pastilla aparezca en la imagen
        # La cámara se queda fija en su posición relativa al brazo, pero el control
        # moverá el brazo hasta que la pastilla coincida con este "Visor".
        target_x = cx_pantalla + 30    # En X suele ser el centro
        target_y = cy_pantalla - 50   # En Y la queremos arriba (donde está la pinza)
        
        # ROI de búsqueda alrededor del target visual
        roi_size = 180
        x1 = max(0, target_x - roi_size // 2)
        y1 = max(0, target_y - roi_size // 2)
        x2 = min(ancho, target_x + roi_size // 2)
        y2 = min(alto, target_y + roi_size // 2)
        
        # Segmentación por escala de grises (más robusta cuando se pierde el color de base)
        roi = frame[y1:y2, x1:x2]
        if roi.size > 0:
            gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            gray_roi = cv2.GaussianBlur(gray_roi, (5, 5), 0)
            # Otsu para segmentación automática
            _, mask_pastilla = cv2.threshold(gray_roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Invertir si el objeto (pastilla) es más oscuro que el fondo (o viceversa)
            if cv2.countNonZero(mask_pastilla) > (roi.shape[0] * roi.shape[1] / 2):
                mask_pastilla = cv2.bitwise_not(mask_pastilla)
            
            kernel = np.ones((3,3), np.uint8)
            mask_pastilla = cv2.morphologyEx(mask_pastilla, cv2.MORPH_OPEN, kernel)
            
            contours, _ = cv2.findContours(mask_pastilla, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            pills = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if 150 < area < 20000:
                    M = cv2.moments(cnt)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"]) + x1
                        cy = int(M["m01"] / M["m00"]) + y1
                        dist_al_target = np.sqrt((cx - target_x)**2 + (cy - target_y)**2)
                        pills.append((cnt, cx, cy, area, dist_al_target))
            
            if pills:
                # Seleccionamos la más cercana al target visual (el visor)
                best = min(pills, key=lambda x: x[4])
                dist_al_target = best[4]
                
                # El error es la distancia de la pastilla al VISOR
                # Guardamos si está "dentro" del visor (ej: gap de 35px)
                esta_en_visor = dist_al_target < 35 
                error_tracking = (best[1] - target_x, best[2] - target_y, best[3], esta_en_visor, dist_al_target)
                
                # Dibujar seguimiento
                cv2.drawContours(frame, [best[0] + [x1, y1]], -1, (0, 255, 0), 2)
                cv2.circle(frame, (best[1], best[2]), 5, (0, 0, 255), -1)

        # --- DIBUJAR VISOR DE 4 LÍNEAS (Target Independiente) ---
        # Este visor NO está en el centro, está en (target_x, target_y)
        gap = 48
        l_len = 19
        c_visor = (0, 255, 255) # Amarillo
        
        # Esquinas del visor
        cv2.line(frame, (target_x - gap, target_y - gap), (target_x - gap, target_y - gap + l_len), c_visor, 2)
        cv2.line(frame, (target_x - gap, target_y + gap), (target_x - gap, target_y + gap - l_len), c_visor, 2)
        cv2.line(frame, (target_x + gap, target_y - gap), (target_x + gap, target_y - gap + l_len), c_visor, 2)
        cv2.line(frame, (target_x + gap, target_y + gap), (target_x + gap, target_y + gap - l_len), c_visor, 2)
        cv2.line(frame, (target_x - gap, target_y - gap), (target_x - gap + l_len, target_y - gap), c_visor, 2)
        cv2.line(frame, (target_x + gap, target_y - gap), (target_x + gap - l_len, target_y - gap), c_visor, 2)
        cv2.line(frame, (target_x - gap, target_y + gap), (target_x - gap + l_len, target_y + gap), c_visor, 2)
        cv2.line(frame, (target_x + gap, target_y + gap), (target_x + gap - l_len, target_y + gap), c_visor, 2)

        cv2.putText(frame, "AREA DE AGARRE", (target_x - 50, target_y - gap - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, c_visor, 1)

    else:
        # --- MODO NORMAL (CON COLOR DE BASE) ---
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
                else:
                    # FALLBACK: Si detecta base pero no pastilla, seguimos el centro de la base
                    M = cv2.moments(base_contour)
                    if M["m00"] != 0:
                        cx_b, cy_b = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
                        error_tracking = (cx_b - cx_pantalla, cy_b - cy_pantalla, M["m00"])
                        cv2.putText(frame, "BUSCANDO PASTILLA EN BASE...", (10, 80), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
            else:
                # FALLBACK: Si detecta base pero no pastilla (sin contornos internos)
                M = cv2.moments(base_contour)
                if M["m00"] != 0:
                    cx_b, cy_b = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
                    error_tracking = (cx_b - cx_pantalla, cy_b - cy_pantalla, M["m00"])
                    cv2.putText(frame, "BUSCANDO PASTILLA EN BASE...", (10, 80), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)

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