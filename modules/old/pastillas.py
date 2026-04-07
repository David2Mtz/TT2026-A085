import cv2
import numpy as np

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
        return None, None # Color no definido

    # Crear la máscara combinada para el color de la base
    mask = cv2.inRange(hsv_frame, ranges[0][0], ranges[0][1])
    if len(ranges) > 1: # Para el caso especial del rojo
        mask2 = cv2.inRange(hsv_frame, ranges[1][0], ranges[1][1])
        mask = cv2.add(mask, mask2)
        
    # --- Limpieza de la máscara ---
    # Elimina pequeños ruidos (puntos blancos)
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    # Rellena pequeños agujeros (puntos negros)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    
    # Guardar una copia de la máscara de color limpia para usarla después
    base_color_mask = mask.copy()

    # --- Encontrar contornos ---
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None, None # No se encontró la base

    # Asumir que el contorno más grande es la base
    largest_contour = max(contours, key=cv2.contourArea)

    # Filtrar por un área mínima para evitar falsos positivos
    min_base_area = 5000 # Ajustar según el tamaño de tu base en la cámara
    if cv2.contourArea(largest_contour) < min_base_area:
        return None, None
        
    return largest_contour, base_color_mask

def find_pills_on_base(hsv_frame, base_contour, base_color_mask):
    """
    Encuentra objetos (pastillas) que están DENTRO del contorno de la base
    pero que NO SON del color de la base.
    """
    
    # 1. Crear máscara del "Área de Interés" (solo la forma de la base)
    moi_mask = np.zeros(hsv_frame.shape[:2], dtype="uint8")
    cv2.drawContours(moi_mask, [base_contour], -1, 255, -1) # -1 = Relleno

    # 2. Encontrar lo que NO es color base, PERO está dentro de la base
    #    pills_mask = (Área de la base) - (Píxeles de color base)
    pills_mask = cv2.subtract(moi_mask, base_color_mask)

    # 3. Limpiar la máscara de pastillas
    kernel = np.ones((3, 3), np.uint8)
    pills_mask = cv2.morphologyEx(pills_mask, cv2.MORPH_OPEN, kernel, iterations=2)
    pills_mask = cv2.morphologyEx(pills_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    # 4. Encontrar contornos de las pastillas
    contours, _ = cv2.findContours(pills_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    # 5. Filtrar pastillas por área mínima
    min_pill_area = 150 # Ajustar al tamaño de tus pastillas
    pill_contours = [c for c in contours if cv2.contourArea(c) > min_pill_area]

    if not pill_contours:
        return None

    # 6. Seleccionar una pastilla (ej. la más grande o la más cercana a un punto)
    #    Por ahora, seleccionamos la más grande.
    selected_pill_contour = max(pill_contours, key=cv2.contourArea)

    # 7. Calcular su centro (coordenadas) y proximidad (área)
    M = cv2.moments(selected_pill_contour)
    if M["m00"] == 0:
        return None # Evitar división por cero

    # Coordenadas (centroide)
    center_x = int(M["m10"] / M["m00"])
    center_y = int(M["m01"] / M["m00"])
    
    # Proximidad (podemos usar el área del contorno)
    proximity = cv2.contourArea(selected_pill_contour)
    
    return ((center_x, center_y), proximity, selected_pill_contour)

# --- Bucle Principal ---

# 1. Inicialización de Cámara
listar_camaras_disponibles()
CAM_INDEX = int(input('Selecciona una cámara por su índice: '))
cap = cv2.VideoCapture(CAM_INDEX)
print(f"Cámara iniciada con el índice: {CAM_INDEX}")

if not cap.isOpened():
    print("Error: No se puede abrir la cámara.")
    exit()

# 2. Comando (aquí defines el color de la base)
# Cambia esto a 'rojo' o 'verde' según tu base
comando = 'azul' 

print(f"Buscando pastillas sobre una base de color: {comando}")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Error al leer el fotograma.")
        break
        
    # Convertir el fotograma completo a HSV
    hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # --- Paso 1: Encontrar la base ---
    base_contour, base_color_mask = find_base(hsv_frame, comando)
    
    if base_contour is not None:
        # Dibujar el contorno de la base en verde
        cv2.drawContours(frame, [base_contour], -1, (0, 255, 0), 3)
        
        # --- Paso 2: Encontrar pastillas en la base ---
        pill_info = find_pills_on_base(hsv_frame, base_contour, base_color_mask)
        
        if pill_info is not None:
            (center, proximity, pill_contour) = pill_info
            
            # Dibujar la pastilla seleccionada en rojo
            cv2.drawContours(frame, [pill_contour], -1, (0, 0, 255), 2)
            cv2.circle(frame, center, 5, (0, 0, 255), -1)
            
            # Mostrar información
            text = f"Objetivo: {center}, Prox: {int(proximity)}"
            cv2.putText(frame, text, (center[0] - 50, center[1] - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # --- Paso 3: Comunicación con el Robot ---
            # Aquí es donde enviarías los datos al brazo robótico.
            # Por ahora, lo imprimimos en la consola.
            print(f"ROBOT_CMD:TARGET_ACQUIRED:X={center[0]},Y={center[1]},AREA={int(proximity)}")

    # Mostrar el resultado
    cv2.imshow('Detector de Pastillas', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

print("Cerrando script.")
cap.release()
cv2.destroyAllWindows()
