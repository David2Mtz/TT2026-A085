# modules/auto_exposure.py
import time

class AutoExposureControl:
    def __init__(self, target_brightness=128, threshold=15):
        """
        target_brightness: Brillo ideal (0-255). 128 es el punto medio.
        threshold: Margen de error antes de realizar un ajuste.
        """
        self.target_brightness = target_brightness
        self.threshold = threshold
        
        # Límites conocidos (solo exposición, sin LED)
        self.min_exp = 100
        self.max_exp = 900
        
        # Estado actual
        self.current_exp = 500
        self.last_adjustment_time = 0
        self.adjustment_cooldown = 0.5 # Segundos entre ajustes para dejar estabilizar

    def set_max_exposure(self, value):
        """ Permite ajustar el límite máximo de exposición dinámicamente """
        self.max_exp = value
        # Asegurar que la exposición actual no exceda el nuevo máximo
        if self.current_exp > self.max_exp:
            self.current_exp = self.max_exp

    def update(self, frame, camara):
        """
        Analiza el frame y ajusta la exposición de la cámara si es necesario.
        """
        import time
        if time.time() - self.last_adjustment_time < self.adjustment_cooldown:
            return False
            
        if frame is None or camara is None:
            return False

        import cv2
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        avg_brightness = gray.mean()
        diff = self.target_brightness - avg_brightness

        if abs(diff) <= self.threshold:
            return False # Brillo óptimo

        # Ajustamos SOLO exposición (sin LED)
        tiene_exp = hasattr(camara, 'set_exposure')

        if diff > 0: # Demasiado oscuro
            if self.current_exp < self.max_exp and tiene_exp:
                self.current_exp = min(self.max_exp, self.current_exp + 50)
                camara.set_exposure(self.current_exp)
        
        else: # Demasiado brillante
            if self.current_exp > self.min_exp and tiene_exp:
                self.current_exp = max(self.min_exp, self.current_exp - 50)
                camara.set_exposure(self.current_exp)

        self.last_adjustment_time = time.time()
        return True