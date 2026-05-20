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
        self.last_brightness = -1 # Cache para evitar saturar el puerto
        
        # Ajustes de imagen manuales
        self.contrast = 1.1   # 1.0 = original, >1.0 = más contraste
        self.saturation = 1.2  # 1.0 = original, >1.0 = más saturación
        
        self.conectar()

    def conectar(self):
        print(f"Intentando abrir puerto serial de cámara: {self.port} a {self.baud_rate}...")
        try:
            # Añadimos un pequeño log antes de la llamada bloqueante
            print("   [DEBUG] Abriendo objeto Serial...")
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=1.0)
            print("   [DEBUG] Puerto abierto, esperando 2s para estabilización...")
            time.sleep(2) 
            self.ser.reset_input_buffer() 
            print("Cámara ESP32 conectada exitosamente.")
        except Exception as e:
            print(f"Error crítico al abrir el puerto de cámara: {e}")
            self.ser = None
            
    def set_exposure(self, value):
        """ Envía el comando 'E' seguido de 2 bytes (Big Endian) """
        if self.ser and self.ser.is_open:
            val = max(0, min(1200, int(value)))
            self.ser.write(b'E' + struct.pack('>H', val))
            self.ser.flush()

    def apply_image_adjustments(self, frame):
        """ Aplica contraste y saturación de forma manual """
        if frame is None:
            return None
            
        # 1. Aplicar Contraste (y un poco de brillo si se deseara, vía beta)
        # cv2.convertScaleAbs(src, alpha, beta) -> alpha es el factor de contraste
        frame = cv2.convertScaleAbs(frame, alpha=self.contrast, beta=0)
        
        # 2. Aplicar Saturación
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
            # No reseteamos el buffer de entrada aquí para no borrar la cabecera si ya llegó
            self.ser.write(b'R')
            self.ser.flush()

            # 1. Esperar la cabecera usando read_until
            sync = self.ser.read_until(b'IMG:')
            if not sync.endswith(b'IMG:'):
                # Si falla, entonces sí limpiamos para el siguiente intento
                self.ser.reset_input_buffer()
                time.sleep(0.05)
                continue


            # 2. Leer el tamaño
            size_bytes = self.ser.read(4)
            if len(size_bytes) != 4:
                # print(f"[Intento {intento+1}] No se pudieron leer los 4 bytes de tamaño.")
                continue
            
            img_size = struct.unpack('<I', size_bytes)[0]
            if img_size == 0 or img_size > 500000: 
                # print(f"[Intento {intento+1}] Tamaño de imagen anómalo: {img_size} bytes.")
                continue

            # 3. Leer exactamente los bytes requeridos por trozos
            img_data = bytearray()
            tiempo_inicio = time.time()
            
            while len(img_data) < img_size:
                faltan = img_size - len(img_data)
                chunk = self.ser.read(min(faltan, 4096)) 
                
                if not chunk:
                    if time.time() - tiempo_inicio > 1.0:
                        break
                else:
                    img_data.extend(chunk)
                    tiempo_inicio = time.time()
            
            if len(img_data) != img_size:
                # print(f"[Intento {intento+1}] Frame incompleto. Llegaron {len(img_data)} de {img_size} bytes.")
                continue

            # 4. Decodificar formato RGB565
            frame = None
            
            # Verificamos si la cantidad de bytes corresponde a QVGA (320x240) o QQVGA (160x120)
            if img_size == 153600:
                width, height = 320, 240
            elif img_size == 38400:
                width, height = 160, 120
            else:
                # Si el tamaño no coincide, descartamos el frame corrupto
                continue

            # Leemos los datos como enteros de 16 bits para manipular el Endianness
            # Luego volvemos a verlos como uint8 pero con la forma (H, W, 2) que OpenCV espera
            frame_array = np.frombuffer(img_data, dtype=np.uint16).byteswap().view(np.uint8).reshape((height, width, 2))
            
            # Convertimos el formato crudo de 16-bits a BGR estándar de OpenCV de 24-bits
            frame = cv2.cvtColor(frame_array, cv2.COLOR_BGR5652BGR)

            if frame is not None:
                # --- Rotación de Imagen ---
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                
                # --- Ajustes Manuales ---
                frame = self.apply_image_adjustments(frame)
                
                return frame 
            else:
                pass
                
        return None

    def set_led_brightness(self, level):
        """
        Envía un comando para ajustar el brillo del LED Flash.
        Solo envía el comando si el nivel es distinto al anterior.
        """
        if not self.ser or not self.ser.is_open:
            return

        try:
            # Asegurar que el nivel esté en el rango correcto
            level = max(0, min(255, int(level)))
            
            # Solo enviar si el nivel cambió (evita saturar el buffer serial)
            if level == self.last_brightness:
                return

            # Enviar comando 'L' seguido del byte de brillo
            self.ser.write(b'L' + struct.pack('B', level))
            self.ser.flush()
            self.last_brightness = level
        except Exception as e:
            print(f"Error al ajustar el brillo del LED: {e}")

    def liberar(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Puerto serial cerrado.")
