# modules/detector_boca.py
import cv2
import dlib
import numpy as np

# Inicializar detector y predictor globalmente una sola vez
detector = dlib.get_frontal_face_detector()
try:
    predictor = dlib.shape_predictor("models/shape_predictor_68_face_landmarks.dat")
except RuntimeError:
    print("Error: No se encontró 'shape_predictor_68_face_landmarks.dat'.")

def get_mouth_coordinates(frame):
    """
    Recibe un frame, detecta la boca y devuelve el frame modificado 
    y las coordenadas (x_centro, y_centro). Si no hay boca, devuelve None.
    """
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
        cv2.putText(frame, "Boca Destino", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    return frame, centro_boca