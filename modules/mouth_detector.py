# modules/mouth_detector.py
import cv2
import dlib
import numpy as np

# Inicializar detector y predictor globalmente una sola vez
detector = dlib.get_frontal_face_detector()
try:
    predictor = dlib.shape_predictor("models/shape_predictor_68_face_landmarks.dat")
except Exception as e:
    print(f"Aviso: No se pudo cargar el predictor de landmarks: {e}")
    predictor = None

def get_mouth_by_color(frame):
    """
    Busca 3 marcadores de color Verde en la boca.
    Esto permite detectar la boca incluso si la pinza tapa el resto del rostro.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # Rango Verde estándar (consistente con el resto del proyecto)
    lower_green = np.array([40, 70, 70])
    upper_green = np.array([85, 255, 255])
    
    mask = cv2.inRange(hsv, lower_green, upper_green)
    
    # Limpieza de ruido
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    centers = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if 20 < area < 5000:
            M = cv2.moments(cnt)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                centers.append((cx, cy))

    # --- VALIDACIÓN DE 3 PUNTOS ---
    if len(centers) >= 3:
        points = np.array(centers)
        centroide = np.mean(points, axis=0)
        distancias = np.linalg.norm(points - centroide, axis=1)
        
        # Tomar los 3 puntos más cercanos entre sí
        indices_validos = np.argsort(distancias)[:3]
        puntos_validos = points[indices_validos]
        
        if np.max(distancias[indices_validos]) < 120:
            # Dibujar los 3 puntos
            for p in puntos_validos:
                cv2.circle(frame, (int(p[0]), int(p[1])), 6, (0, 255, 0), 2)

            # Calcular centro y cruceta
            min_x = np.min(puntos_validos[:, 0])
            max_x = np.max(puntos_validos[:, 0])
            min_y = np.min(puntos_validos[:, 1])
            max_y = np.max(puntos_validos[:, 1])
            
            avg_x = int((min_x + max_x) / 2)
            avg_y = int((min_y + max_y) / 2)
            centro_objetivo = (avg_x, avg_y)
            
            # Dibujar cruceta simple
            cv2.line(frame, (min_x, avg_y), (max_x, avg_y), (0, 255, 255), 1)
            cv2.drawMarker(frame, centro_objetivo, (0, 0, 255), cv2.MARKER_CROSS, 15, 2)
            cv2.putText(frame, "Boca (3 Puntos Verdes)", (max_x + 10, avg_y), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            
            return centro_objetivo
    
    if len(centers) > 0:
        cv2.putText(frame, f"Buscando marcadores... ({len(centers)}/3)", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
    return None


def get_mouth_coordinates(frame):
    """
    Detecta la boca intentando primero con marcadores de color (más robusto)
    y luego con landmarks faciales (respaldo).
    """
    # 1. Prioridad: Detectar por color (funciona con la pinza estorbando)
    centro_por_color = get_mouth_by_color(frame)
    if centro_por_color is not None:
        return frame, centro_por_color

    # 2. Respaldo: Detectar por rostro completo (Landmarks)
    if predictor is None:
        return frame, None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = detector(gray, 0)
    
    centro_boca = None

    for face in faces:
        landmarks = predictor(gray, face)
        mouth_points = []
        for i in range(48, 68): # MOUTH_START a MOUTH_END
            x = landmarks.part(i).x
            y = landmarks.part(i).y
            mouth_points.append((x, y))

        mouth_array = np.array(mouth_points)
        (x, y, w, h) = cv2.boundingRect(mouth_array)
        
        # Calcular el centro exacto de la boca
        centro_boca = (x + w // 2, y + h // 2)
        
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.circle(frame, centro_boca, 4, (0, 0, 255), -1)
        cv2.putText(frame, "Boca (Landmarks)", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    return frame, centro_boca
