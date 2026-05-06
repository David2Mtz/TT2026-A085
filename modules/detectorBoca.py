import cv2
import numpy as np
import os

def detect_mouth_landmarks_by_color(frame):
    h, w = frame.shape[:2]
    # 1. Conversión a HSV
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # Rango para el nuevo rosa brillante (Cerca del límite de rojo en HSV)
    lower_magenta = np.array([150, 80, 50]) 
    upper_magenta = np.array([180, 255, 255])
    
    mask = cv2.inRange(hsv, lower_magenta, upper_magenta)
    
    # --- MÁSCARA DE ÁREA DE INTERÉS (ROI) ---
    # Ignorar bordes laterales (15% cada lado)
    mask[:, :int(w*0.15)] = 0
    mask[:, int(w*0.85):] = 0
    
    # Ignorar la mitad inferior del frame (donde está la pinza y la pastilla)
    mask[int(h*0.55):, :] = 0
    
    # 2. Limpieza de ruido
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.dilate(mask, kernel, iterations=1)
    
    # 3. Encontrar contornos
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        # Marcadores de boca: aumentamos el área máxima (los nuevos son más grandes)
        if 50 < area < 4000:
            # Filtro de circularidad aún más permisivo
            perimetro = cv2.arcLength(cnt, True)
            if perimetro > 0:
                circularidad = 4 * np.pi * (area / (perimetro * perimetro))
                if circularidad > 0.2: 
                    M = cv2.moments(cnt)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        candidates.append((cx, cy))

    # --- LÓGICA DE FILTRADO (CLUSTERING OPTIMIZADO) ---
    if len(candidates) < 4:
        return None, None

    # Si hay demasiados candidatos, tomamos solo los más centrales para no saturar la CPU
    if len(candidates) > 8:
        centro_x_frame = w // 2
        candidates = sorted(candidates, key=lambda p: abs(p[0] - centro_x_frame))[:8]

    # Búsqueda del cluster de 4 puntos más compacto
    if len(candidates) > 4:
        from itertools import combinations
        min_dist_sum = float('inf')
        best_landmarks = candidates[:4]
        
        # Con 8 candidatos hay 70 combinaciones, lo cual es manejable (antes era ilimitado)
        for combo in combinations(candidates, 4):
            combo_pts = np.array(combo)
            # Cálculo rápido de compacidad: dispersión máxima entre puntos
            # (Más rápido que calcular centroide y distancias para cada punto)
            dist_sum = 0
            for i in range(4):
                for j in range(i + 1, 4):
                    dist_sum += np.linalg.norm(combo_pts[i] - combo_pts[j])
            
            if dist_sum < min_dist_sum:
                # Validación rápida de forma: no deben estar todos en línea (área mínima)
                hull = cv2.convexHull(combo_pts.astype(np.int32))
                if cv2.contourArea(hull) > 150:
                    min_dist_sum = dist_sum
                    best_landmarks = list(combo)
        landmarks = best_landmarks
    else:
        landmarks = candidates

    # --- LÓGICA DE IDENTIFICACIÓN ---
    # Ordenar por coordenada Y para identificar Arriba y Abajo
    pts_y = sorted(landmarks, key=lambda p: p[1])
    top_lip = pts_y[0]
    bottom_lip = pts_y[-1]
    
    # Los dos puntos restantes se ordenan por X para Izquierda y Derecha
    middle_pts = pts_y[1:-1]
    pts_x = sorted(middle_pts, key=lambda p: p[0])
    left_corner = pts_x[0]
    right_corner = pts_x[-1]

    # Dibujar Landmarks
    pts_dict = {
        "Top": top_lip, "Bottom": bottom_lip, 
        "Left": left_corner, "Right": right_corner
    }
    
    for name, pt in pts_dict.items():
        cv2.circle(frame, pt, 6, (255, 0, 255), -1)
        cv2.putText(frame, name, (pt[0]+10, pt[1]), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    # Calcular el Centro de Objetivo
    avg_x = int(np.mean([p[0] for p in landmarks]))
    avg_y = int(np.mean([p[1] for p in landmarks]))
    centro_objetivo = (avg_x, avg_y)

    # Feedback visual
    cv2.drawMarker(frame, centro_objetivo, (0, 0, 255), cv2.MARKER_CROSS, 25, 2)
    cv2.putText(frame, "Boca (Magenta)", (avg_x + 15, avg_y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
    
    return centro_objetivo, pts_dict

def get_mouth_by_color(frame):
    """
    Alias para compatibilidad con mouth_detector.py.
    Retorna solo el centro del objetivo basado en los 4 marcadores Lima.
    """
    centro, _ = detect_mouth_landmarks_by_color(frame)
    return centro

def get_mouth_coordinates(frame):
    """
    Función de compatibilidad para ciclo_completo.py.
    Detecta la boca EXCLUSIVAMENTE por color (4 puntos Lima).
    """
    centro, _ = detect_mouth_landmarks_by_color(frame)
    return frame, centro

def iniciar_deteccion(camara):
    """
    Aumenta el brillo del LED para la fase de detección.
    """
    print("[DETECTOR BOCA] Ajustando iluminación: 255")
    camara.set_led_brightness(255)

def finalizar_deteccion(camara):
    """
    Apaga el LED al finalizar la detección.
    """
    print("[DETECTOR BOCA] Restaurando iluminación: 0")
    camara.set_led_brightness(0)
