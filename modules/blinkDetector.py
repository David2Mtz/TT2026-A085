# modules/3blinks.py
import os
import cv2
import dlib
import imutils
import time
from scipy.spatial import distance as dist
from imutils import face_utils

class BlinkDetector:
    def __init__(self, target_blinks=2, window_time=2.7, threshold=0.4):
        self.target_blinks = target_blinks
        self.window_time = window_time
        self.blink_thresh = threshold
        self.succ_frame = 2
        self.count_frame = 0
        self.blink_timestamps = []
        
        # Inicializar dlib
        self.detector = dlib.get_frontal_face_detector()
        # Ruta corregida al modelo usando la raíz del proyecto
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        predictor_path = os.path.join(base_path, 'models', 'shape_predictor_68_face_landmarks.dat')
        self.landmark_predict = dlib.shape_predictor(predictor_path)
        (self.L_start, self.L_end) = face_utils.FACIAL_LANDMARKS_IDXS["left_eye"]
        (self.R_start, self.R_end) = face_utils.FACIAL_LANDMARKS_IDXS['right_eye']
        
        self.cam = None

    def start_cam(self):
        if self.cam is None:
            self.cam = cv2.VideoCapture(0)
            # Bajar resolución de hardware para ganar FPS (Mac/Laptop)
            self.cam.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
            self.cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
            self.cam.set(cv2.CAP_PROP_FPS, 24)
        return self.cam.isOpened()

    def stop_cam(self):
        if self.cam:
            self.cam.release()
            self.cam = None
            try:
                cv2.destroyWindow("Detector de Parpadeo")
            except: pass

    def calculate_EAR(self, eye):
        y1 = dist.euclidean(eye[1], eye[5])
        y2 = dist.euclidean(eye[2], eye[4])
        x1 = dist.euclidean(eye[0], eye[3])
        EAR = (y1 + y2) / x1
        return EAR

    def process_frame(self, frame):
        """Procesa un frame y retorna si se alcanzó el trigger de parpadeo."""
        if frame is None:
            return False, frame

        # Reducir aún más para el detector dlib (que es lo más pesado)
        img_small = imutils.resize(frame, width=250)
        img_gray = cv2.cvtColor(img_small, cv2.COLOR_BGR2GRAY)
        
        # dlib es mucho más rápido con imágenes pequeñas
        faces = self.detector(img_gray, 0)

        trigger = False
        # Factor de escala para los landmarks
        scale = frame.shape[1] / img_small.shape[1]

        for face in faces:
            scaled_face = dlib.rectangle(
                int(face.left() * scale), int(face.top() * scale),
                int(face.right() * scale), int(face.bottom() * scale)
            )
            
            frame_gray_full = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            shape = self.landmark_predict(frame_gray_full, scaled_face)
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
                    self.blink_timestamps = [t for t in self.blink_timestamps if ahora - t <= self.window_time]
                    print(f"[Blink] Detectado. Total en ventana: {len(self.blink_timestamps)}")
                self.count_frame = 0

            if len(self.blink_timestamps) >= self.target_blinks:
                trigger = True
                self.blink_timestamps = []

        cv2.putText(frame, f"Blinks: {len(self.blink_timestamps)}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        return trigger, frame

    def check_for_trigger(self):
        """Captura un frame de la cámara y verifica el trigger de parpadeo."""
        if self.cam is None:
            return False

        ret, frame = self.cam.read()
        if not ret:
            return False

        trigger, _ = self.process_frame(frame)
        return trigger
