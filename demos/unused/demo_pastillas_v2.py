# demos/demo_pastillas_v2.py
import cv2
import numpy as np
import sys
import os

# Ajuste de ruta para importar módulos
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.flujo_camara import CameraSerial

def get_base_ranges():
    """Retorna rangos HSV para las bases (contenedores)."""
    return {
        "Azul": [(np.array([90, 50, 40]), np.array([140, 255, 255]))],
        "Verde": [(np.array([35, 50, 40]), np.array([90, 255, 255]))],
        "Rojo": [
            (np.array([0, 50, 40]), np.array([10, 255, 255])),
            (np.array([170, 50, 40]), np.array([180, 255, 255]))
        ]
    }

def process_frame(frame, color_objetivo):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    ranges = get_base_ranges().get(color_objetivo)
    if not ranges:
        return frame, "Color no configurado"

    # 1. Encontrar la BASE usando HSV
    mask_base = None
    for (lower, upper) in ranges:
        curr_mask = cv2.inRange(hsv, lower, upper)
        mask_base = curr_mask if mask_base is None else cv2.add(mask_base, curr_mask)
    
    kernel = np.ones((5,5), np.uint8)
    mask_base = cv2.morphologyEx(mask_base, cv2.MORPH_OPEN, kernel)
    mask_base = cv2.morphologyEx(mask_base, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask_base, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return frame, "Base no detectada"

    # Tomar la base más grande
    base_cnt = max(contours, key=cv2.contourArea)
    if cv2.contourArea(base_cnt) < 2000:
        return frame, "Base muy pequeña"

    # Crear una máscara limpia de la base
    clean_base_mask = np.zeros_like(gray)
    cv2.drawContours(clean_base_mask, [base_cnt], -1, 255, -1)
    
    # Dibujar contorno de base para feedback
    cv2.drawContours(frame, [base_cnt], -1, (0, 255, 0), 2)

    # 2. Segmentación de PASTILLA dentro de la base (Escala de Grises)
    # Aplicamos la máscara de la base al canal gris
    gray_roi = cv2.bitwise_and(gray, gray, mask=clean_base_mask)
    
    if color_objetivo in ["Azul", "Verde"]:
        # La pastilla NO es blanca, pero suele ser más clara que la sombra.
        # Paso A: Eliminar reflejos especulares extremos (>240)
        _, no_glare = cv2.threshold(gray_roi, 240, 255, cv2.THRESH_TOZERO_INV)
        
        # Paso B: Segmentación inicial para encontrar Pastilla + Sombra
        # Usamos un umbral para detectar el conjunto objeto-sombra
        _, combined_mask = cv2.threshold(no_glare, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        combined_mask = cv2.bitwise_and(combined_mask, combined_mask, mask=clean_base_mask)
        
        # Paso C: Refinamiento para SEPARAR pastilla de sombra
        # Dentro de la máscara combinada, la pastilla suele tener un valor de gris mayor que la sombra.
        pill_mask = np.zeros_like(gray)
        contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for cnt in contours:
            if cv2.contourArea(cnt) > 100:
                # ROI local del objeto detectado
                x_c, y_c, w_c, h_c = cv2.boundingRect(cnt)
                local_roi = no_glare[y_c:y_c+h_c, x_c:x_c+w_c]
                local_mask = combined_mask[y_c:y_c+h_c, x_c:x_c+w_c]
                
                if local_roi.size > 0:
                    # Calculamos el promedio de gris solo de la parte "objeto"
                    mean_val = cv2.mean(local_roi, mask=local_mask)[0]
                    # Solo tomamos lo que sea más claro que el promedio (la pastilla es clara, la sombra es oscura)
                    _, refined_local = cv2.threshold(local_roi, mean_val + 5, 255, cv2.THRESH_BINARY)
                    pill_mask[y_c:y_c+h_c, x_c:x_c+w_c] = cv2.bitwise_and(refined_local, local_mask)

    else:
        # La base es Roja, la pastilla ES blanca.
        # En este caso, la sombra es muy oscura y la pastilla muy clara.
        # Un umbral alto (180+) elimina la sombra automáticamente.
        _, pill_mask = cv2.threshold(gray_roi, 180, 255, cv2.THRESH_BINARY)
        pill_mask = cv2.bitwise_and(pill_mask, pill_mask, mask=clean_base_mask)

    # 3. Analizar Contornos de la Pastilla
    kernel_small = np.ones((3,3), np.uint8)
    pill_mask = cv2.morphologyEx(pill_mask, cv2.MORPH_OPEN, kernel_small)
    
    pill_contours, _ = cv2.findContours(pill_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    pill_found = False
    if pill_contours:
        # Filtrar por área razonable respecto a la base
        base_area = cv2.contourArea(base_cnt)
        possible_pills = [c for c in pill_contours if 150 < cv2.contourArea(c) < (base_area * 0.5)]
        
        if possible_pills:
            best_pill = max(possible_pills, key=cv2.contourArea)
            M = cv2.moments(best_pill)
            if M["m00"] != 0:
                cx, cy = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
                cv2.drawContours(frame, [best_pill], -1, (0, 0, 255), 2)
                cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)
                cv2.putText(frame, "PASTILLA", (cx - 20, cy - 20), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                pill_found = True

    status = f"Buscando en {color_objetivo} | Pastilla: {'OK' if pill_found else '??'}"
    return frame, status

def main():
    PUERTO = os.getenv('PUERTO_CAMARA', '/dev/ttyUSB1')
    try:
        camara = CameraSerial(port=PUERTO, baud_rate=460800)
    except:
        print("Error: No se pudo abrir la cámara.")
        return

    print("Demo Pastillas v2 - Presiona 'a' (Azul), 'v' (Verde), 'r' (Rojo), 'q' (Salir)")
    color_actual = "Azul"

    while True:
        frame = camara.get_frame()
        if frame is None: continue

        frame_proc, status = process_frame(frame, color_actual)
        
        cv2.putText(frame_proc, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.imshow("Demo Robustez Pastillas", frame_proc)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'): break
        elif key == ord('a'): color_actual = "Azul"
        elif key == ord('v'): color_actual = "Verde"
        elif key == ord('r'): color_actual = "Rojo"

    camara.liberar()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
