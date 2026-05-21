# utils/flujo_camara.py
import os
import serial
import cv2
import numpy as np
import time
import struct
from dotenv import load_dotenv

load_dotenv()

class CameraSerial:
    def __init__(self, port=None, baud_rate=460800):
        self.port = port or os.getenv('PUERTO_CAMARA', '/dev/cu.usbserial-210')
        self.baud_rate = baud_rate
        self.ser = None
        self.last_brightness = -1 
        
        # Ajustes de imagen manuales (Neutrales)
        self.contrast = 1.0   
        self.saturation = 1.0 
        
        self.conectar()

    def conectar(self):
        print(f"Intentando abrir puerto serial de cámara: {self.port} a {self.baud_rate}...")
        try:
            print("   [DEBUG] Abriendo objeto Serial...")
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=1.0)
            print("   [DEBUG] Puerto abierto, esperando 2s para estabilización...")
            time.sleep(2) 
            self.ser.reset_input_buffer() 
            print("Cámara XIAO ESP32-S3 conectada exitosamente.")
        except Exception as e:
            print(f"Error crítico al abrir el puerto de cámara: {e}")
            self.ser = None
            
    def apply_image_adjustments(self, frame):
        """ Aplica contraste y saturación de forma manual """
        if frame is None:
            return None
        if self.contrast != 1.0:
            frame = cv2.convertScaleAbs(frame, alpha=self.contrast, beta=0)
        if self.saturation != 1.0:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype("float32")
            (h, s, v) = cv2.split(hsv)
            s = s * self.saturation
            s = np.clip(s, 0, 255)
            hsv = cv2.merge([h, s, v])
            frame = cv2.cvtColor(hsv.astype("uint8"), cv2.COLOR_HSV2BGR)
        return frame

    def get_frame(self, max_intentos=3):
        if not self.ser:
            return None

        for intento in range(max_intentos):
            self.ser.write(b'R')
            self.ser.flush()

            # 1. Esperar la cabecera
            sync = self.ser.read_until(b'IMG:')
            if not sync.endswith(b'IMG:'):
                self.ser.reset_input_buffer()
                continue

            # 2. Leer el tamaño
            size_bytes = self.ser.read(4)
            if len(size_bytes) != 4:
                continue
            
            img_size = struct.unpack('<I', size_bytes)[0]
            if img_size == 0 or img_size > 500000: 
                continue

            # 3. Leer bytes por trozos
            img_data = bytearray()
            tiempo_inicio = time.time()
            while len(img_data) < img_size:
                faltan = img_size - len(img_data)
                chunk = self.ser.read(min(faltan, 4096)) 
                if not chunk:
                    if time.time() - tiempo_inicio > 1.0: break
                else:
                    img_data.extend(chunk)
                    tiempo_inicio = time.time()
            
            if len(img_data) != img_size:
                continue

            # 4. Decodificar
            frame = None
            if img_data[0] == 0xFF and img_data[1] == 0xD8: # JPEG
                frame = cv2.imdecode(np.frombuffer(img_data, dtype=np.uint8), cv2.IMREAD_COLOR)
            elif img_size == 153600: # RGB565 fallback
                width, height = 320, 240
                frame_array = np.frombuffer(img_data, dtype=np.uint16).byteswap().view(np.uint8).reshape((height, width, 2))
                frame = cv2.cvtColor(frame_array, cv2.COLOR_BGR5652BGR)

            if frame is not None:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                frame = self.apply_image_adjustments(frame)
                return frame 
        return None

    def set_led_brightness(self, level):
        if not self.ser or not self.ser.is_open: return
        level = max(0, min(255, int(level)))
        if level == self.last_brightness: return
        self.ser.write(b'L' + struct.pack('B', level))
        self.ser.flush()
        self.last_brightness = level

    def liberar(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Puerto serial cerrado.")
