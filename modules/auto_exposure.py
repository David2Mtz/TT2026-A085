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
        
        # Límites conocidos
        self.min_led = 0
        self.max_led = 160
        self.min_exp = 100
        self.max_exp = 850
        
        # Estado actual
        self.current_led = 60
        self.current_exp = 300
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
        Analiza el frame y ajusta la cámara si es necesario.
        Retorna True si realizó un ajuste, False si el brillo es óptimo.
        """
        now = time.time()
        if now - self.last_adjustment_time < self.adjustment_cooldown:
            return False

        if frame is None:
            return False

        # Calcular brillo promedio (Luminancia)
        # Convertimos a escala de grises para medir rápido
        import cv2
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        avg_brightness = gray.mean()

        diff = self.target_brightness - avg_brightness

        if abs(diff) <= self.threshold:
            return False # Brillo óptimo

        # Lógica de ajuste tipo "Cámara Fotográfica"
        if diff > 0: # Demasiado oscuro -> Aumentar luz
            if self.current_led < self.max_led:
                self.current_led = min(self.max_led, self.current_led + 20)
                camara.set_led_brightness(self.current_led)
            elif self.current_exp < self.max_exp:
                self.current_exp = min(self.max_exp, self.current_exp + 50)
                camara.set_exposure(self.current_exp)
        
        else: # Demasiado brillante -> Reducir luz
            if self.current_exp > self.min_exp:
                self.current_exp = max(self.min_exp, self.current_exp - 50)
                camara.set_exposure(self.current_exp)
            elif self.current_led > self.min_led:
                self.current_led = max(self.min_led, self.current_led - 20)
                camara.set_led_brightness(self.current_led)

        self.last_adjustment_time = now
        print(f"[AutoExp] Brillo: {avg_brightness:.1f} -> Ajustando a LED:{self.current_led} EXP:{self.current_exp}")
        return True
