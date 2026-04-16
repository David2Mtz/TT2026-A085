import cv2
import numpy as np

# --- Variable global para la calibración ---
pixels_per_millimeter = None # Se calculará al presionar 'c'

def listar_camaras_disponibles():
    """
    Prueba los índices de cámara (0-9) e imprime los que están disponibles.
    """
    print("--- Buscando cámaras disponibles ---")
    available_cameras = []
    for i in range(3):
        cap_test = cv2.VideoCapture(i)
        if cap_test.isOpened():
            print(f"Cámara detectada en el índice: {i}")
            available_cameras.append(i)
            cap_test.release()
    
    if not available_cameras:
        print("No se encontró ninguna cámara.")
    print("--------------------------------------")
    return available_cameras

def get_hsv_ranges(color_name):
    """
    Devuelve los rangos HSV (bajo y alto) para un nombre de color dado.
    """
    # --- Parámetros para ajustar ---
    min_saturation = 70
    min_value = 60
    # --- Fin de parámetros ---

    ranges = {}
    
    # Rojo (dividido en dos partes)
    lower_red1 = np.array([0, min_saturation, min_value])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, min_saturation, min_value])
    upper_red2 = np.array([180, 255, 255])
    ranges['rojo'] = ((lower_red1, upper_red1), (lower_red2, upper_red2))

    # Verde
    lower_green = np.array([40, min_saturation, min_value])
    upper_green = np.array([85, 255, 255])
    ranges['verde'] = ((lower_green, upper_green),)

    # Azul
    lower_blue = np.array([95, min_saturation, min_value])
    upper_blue = np.array([135, 255, 255])
    ranges['azul'] = ((lower_blue, upper_blue),)
    
    return ranges.get(color_name.lower())

def find_base(hsv_frame, base_color_name):
    """
    Encuentra el contorno de la base (el área más grande) de un color específico.
    """
    ranges = get_hsv_ranges(base_color_name)
    if not ranges:
        return None, None 

    mask = cv2.inRange(hsv_frame, ranges[0][0], ranges[0][1])
    if len(ranges) > 1: 
        mask2 = cv2.inRange(hsv_frame, ranges[1][0], ranges[1][1])
        mask = cv2.add(mask, mask2)
        
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    
    base_color_mask = mask.copy()

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None, None 

    largest_contour = max(contours, key=cv2.contourArea)

    min_base_area = 5000 
    if cv2.contourArea(largest_contour) < min_base_area:
        return None, None
        
    return largest_contour, base_color_mask

def find_pills_on_base(hsv_frame, base_contour, base_color_mask):
    """
    Encuentra objetos (pastillas) que están DENTRO del contorno de la base
    pero que NO SON del color de la base.
    """
    
    moi_mask = np.zeros(hsv_frame.shape[:2], dtype="uint8")
    cv2.drawContours(moi_mask, [base_contour], -1, 255, -1) 

    pills_mask = cv2.subtract(moi_mask, base_color_mask)

    kernel = np.ones((3, 3), np.uint8)
    pills_mask = cv2.morphologyEx(pills_mask, cv2.MORPH_OPEN, kernel, iterations=2)
    pills_mask = cv2.morphologyEx(pills_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(pills_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    min_pill_area = 150 
    pill_contours = [c for c in contours if cv2.contourArea(c) > min_pill_area]

    if not pill_contours:
        return None

    selected_pill_contour = max(pill_contours, key=cv2.contourArea)

    M = cv2.moments(selected_pill_contour)
    if M["m00"] == 0:
        return None 

    center_x = int(M["m10"] / M["m00"])
    center_y = int(M["m01"] / M["m00"])
    
    proximity = cv2.contourArea(selected_pill_contour)
    
    (x, y, w, h) = cv2.boundingRect(selected_pill_contour)
    
    return ((center_x, center_y), proximity, selected_pill_contour, (x, y, w, h))

# --- Bucle Principal ---

# 1. Inicialización de Cámara
# listar_camaras_disponibles()
# CAM_INDEX = int(input('Selecciona una cámara por su índice: '))

# *** NUEVO: Pedir el tamaño del objeto de referencia ***
KNOWN_WIDTH_MM = float(input('Ingresa el ancho en mm de tu objeto de referencia (ej: 28): '))

cap = cv2.VideoCapture(2)

if not cap.isOpened():
    print("Error: No se puede abrir la cámara.")
    exit()

# 2. Comando
comando = 'azul' 
print(f"Buscando pastillas sobre una base de color: {comando}")
print("\n*** APUNTE AL OBJETO DE REFERENCIA Y PRESIONE 'c' PARA CALIBRAR ***\n")

# *** NUEVO: Variable para guardar la última anchura detectada para calibrar ***
last_detected_w_px = 0

while True:
    ret, frame = cap.read()
    if not ret:
        print("Error al leer el fotograma.")
        break
        
    hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # --- Paso 1: Encontrar la base ---
    base_contour, base_color_mask = find_base(hsv_frame, comando)
    
    if base_contour is not None:
        cv2.drawContours(frame, [base_contour], -1, (0, 255, 0), 3)
        
        # --- Paso 2: Encontrar pastillas en la base ---
        pill_info = find_pills_on_base(hsv_frame, base_contour, base_color_mask)
        
        if pill_info is not None:
            (center, proximity, pill_contour, (x, y, w, h)) = pill_info
            
            # *** NUEVO: Guardar el ancho para la calibración ***
            last_detected_w_px = w
            
            # Dibujar la pastilla seleccionada (contorno rojo)
            cv2.drawContours(frame, [pill_contour], -1, (0, 0, 255), 2)
            cv2.circle(frame, center, 5, (0, 0, 255), -1)
            
            # Dibujar la caja delimitadora (rectángulo amarillo)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
            
            # --- Paso 3: Calcular y mostrar medidas ---
            text_area = f"Area: {int(proximity)} px^2"
            text_size = ""
            
            # *** CAMBIO: Mostrar mm si está calibrado, si no, mostrar px ***
            if pixels_per_millimeter is not None:
                # Calcular tamaño en mm
                w_mm = w / pixels_per_millimeter
                h_mm = h / pixels_per_millimeter
                text_size = f"Size: {w_mm:.1f} x {h_mm:.1f} mm" # .1f = 1 decimal
                
                # --- Paso 4: Comunicación con el Robot ---
                print(f"ROBOT_CMD:TARGET:X={center[0]},Y={center[1]},W_MM={w_mm:.1f},H_MM={h_mm:.1f}")
            else:
                # Aún no calibrado, mostrar píxeles
                text_size = f"Size: {w} x {h} px"

            # Colocar el texto justo arriba de la caja delimitadora
            cv2.putText(frame, text_area, (x, y - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(frame, text_size, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    # *** NUEVO: Mostrar estado de calibración en la pantalla ***
    if pixels_per_millimeter is None:
        status_text = "STATUS: NO CALIBRADO (Presione 'c' sobre el objeto de ref.)"
        status_color = (0, 0, 255) # Rojo
    else:
        status_text = f"STATUS: CALIBRADO (1mm = {pixels_per_millimeter:.2f} px)"
        status_color = (0, 255, 0) # Verde
        
    cv2.putText(frame, status_text, (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)


    # --- Manejador de teclas ---
    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        break
    
    # *** NUEVO: Lógica de calibración ***
    if key == ord('c'):
        if last_detected_w_px > 0:
            pixels_per_millimeter = last_detected_w_px / KNOWN_WIDTH_MM
            print("\n--- ¡CALIBRACIÓN COMPLETA! ---")
            print(f"  Ancho del objeto en píxeles: {last_detected_w_px} px")
            print(f"  Ancho del objeto en mm: {KNOWN_WIDTH_MM} mm")
            print(f"  Ratio calculado: {pixels_per_millimeter:.4f} px/mm")
            print("---------------------------------\n")
            last_detected_w_px = 0 # Resetear
        else:
            print("Error de calibración: No se detectó ningún objeto. Intente de nuevo.")


    # Mostrar el resultado
    cv2.imshow('Detector de Pastillas', frame)


print("Cerrando script.")
cap.release()
cv2.destroyAllWindows()