# modules/3blinks.py
import cv2
import dlib
import imutils
import time
from scipy.spatial import distance as dist
from imutils import face_utils

class BlinkDetector:
    def __init__(self, target_blinks=3, window_time=2.5, threshold=0.4):
        self.target_blinks = target_blinks
        self.window_time = window_time
        self.blink_thresh = threshold
        self.succ_frame = 2
        self.count_frame = 0
        self.blink_timestamps = []
        
        # Inicializar dlib
        self.detector = dlib.get_frontal_face_detector()
        # Ruta corregida al modelo
        self.landmark_predict = dlib.shape_predictor('models/shape_predictor_68_face_landmarks.dat')
        (self.L_start, self.L_end) = face_utils.FACIAL_LANDMARKS_IDXS["left_eye"]
        (self.R_start, self.R_end) = face_utils.FACIAL_LANDMARKS_IDXS['right_eye']
        
        self.cam = None

    def start_cam(self):
        if self.cam is None:
            self.cam = cv2.VideoCapture(0)
        return self.cam.isOpened()

    def stop_cam(self):
        if self.cam:
            self.cam.release()
            self.cam = None
            cv2.destroyWindow("Detector de Parpadeo")

    def calculate_EAR(self, eye):
        y1 = dist.euclidean(eye[1], eye[5])
        y2 = dist.euclidean(eye[2], eye[4])
        x1 = dist.euclidean(eye[0], eye[3])
        EAR = (y1 + y2) / x1
        return EAR

    def check_for_trigger(self):
        """
        Captura un frame de la laptop y verifica si se alcanzó el número de parpadeos.
        Retorna True si se detectaron los parpadeos requeridos.
        """
        if self.cam is None:
            return False

        ret, frame = self.cam.read()
        if not ret:
            return False

        frame = imutils.resize(frame, width=400)
        img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.detector(img_gray)

        trigger = False
        for face in faces:
            shape = self.landmark_predict(img_gray, face)
            shape = face_utils.shape_to_np(shape)
            
            lefteye = shape[self.L_start : self.L_end]
            righteye = shape[self.R_start : self.R_end]

            left_EAR = self.calculate_EAR(lefteye)
            right_EAR = self.calculate_EAR(righteye)
            avg = (left_EAR + right_EAR) / 2

            if avg < self.blink_thresh:
                self.count_frame += 1
            else:
                if self.count_frame >= self.succ_frame:
                    ahora = time.time()
                    self.blink_timestamps.append(ahora)
                    # Limpiar timestamps viejos
                    self.blink_timestamps = [t for t in self.blink_timestamps if ahora - t <= self.window_time]
                    print(f"[Blink] Detectado. Total en ventana: {len(self.blink_timestamps)}")
                self.count_frame = 0

            if len(self.blink_timestamps) >= self.target_blinks:
                trigger = True
                self.blink_timestamps = [] # Resetear tras éxito

        # Feedback visual
        cv2.putText(frame, f"Blinks: {len(self.blink_timestamps)}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.imshow("Detector de Parpadeo", frame)
        
        return trigger
