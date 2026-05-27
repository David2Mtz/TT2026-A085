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
    def __init__(self, port=None, baud_rate=None):
        self.port = port or os.getenv('PUERTO_CAMARA', '/dev/cu.usbserial-210')
        self.baud_rate = baud_rate or int(os.getenv('BAUD_CAMARA', 460800))
        self.ser = None
        
        # Ajustes de imagen manuales (Neutrales)
        self.contrast = 1.0   
        self.saturation = 1.0 
        self.green_gain = 0.9 # Reducir verdes para evitar falsos positivos en sombras
        self.blue_gain = 0.9  # Reducir azules para balancear la imagen
        
        self.conectar()

    def conectar(self):
        print(f"Intentando abrir puerto serial de cámara: {self.port} a {self.baud_rate}...")
        try:
            print("   [DEBUG] Abriendo objeto Serial...")
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=2.0)
            self.ser.setDTR(True)
            self.ser.setRTS(True)
            print("   [DEBUG] Puerto abierto, esperando 3s para estabilización...")
            time.sleep(3) 
            self.ser.reset_input_buffer() 
            print("Cámara XIAO ESP32-S3 conectada exitosamente.")
        except Exception as e:
            print(f"Error crítico al abrir el puerto de cámara: {e}")
            self.ser = None
            
    def apply_image_adjustments(self, frame):
        """ Aplica contraste, saturación y balance de blancos de forma manual """
        if frame is None:
            return None

        # 1. Compensación de Tinte (Balance de Color Manual)
        if self.green_gain != 1.0 or self.blue_gain != 1.0:
            # Separar canales (BGR)
            b, g, r = cv2.split(frame)
            # Escalar canal verde si es necesario
            if self.green_gain != 1.0:
                g = (g.astype("float32") * self.green_gain).clip(0, 255).astype("uint8")
            # Escalar canal azul si es necesario
            if self.blue_gain != 1.0:
                b = (b.astype("float32") * self.blue_gain).clip(0, 255).astype("uint8")
            frame = cv2.merge([b, g, r])

        # 2. Contraste
        if self.contrast != 1.0:
            frame = cv2.convertScaleAbs(frame, alpha=self.contrast, beta=0)

        # 3. Saturación
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
            # Limpiar antes de pedir
            if self.ser.in_waiting > 10000:
                self.ser.reset_input_buffer()
                
            self.ser.write(b'R\n')
            self.ser.flush()

            # 1. Esperar la cabecera
            # Usamos read_until pero con un timeout interno más corto para no bloquear
            sync = self.ser.read_until(b'IMG:')
            if not sync.endswith(b'IMG:'):
                if sync:
                    try:
                        decoded = sync.decode(errors='ignore').strip()
                        if decoded:
                            print(f"DEBUG: Recibido texto en lugar de imagen: {decoded}")
                    except:
                        print(f"DEBUG: Recibido basura binaria ({len(sync)} bytes)")
                continue

            # 2. Leer el tamaño
            size_bytes = self.ser.read(4)
            if len(size_bytes) != 4:
                print("DEBUG: Error al leer tamaño (bytes incompletos)")
                continue
            
            img_size = struct.unpack('<I', size_bytes)[0]
            if img_size == 0 or img_size > 1000000: # Aumentamos límite para RGB VGA (614,400 bytes)
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
            elif img_size == 153600: # RGB565 QVGA (320x240)
                width, height = 320, 240
                frame_array = np.frombuffer(img_data, dtype=np.uint16).byteswap().view(np.uint8).reshape((height, width, 2))
                frame = cv2.cvtColor(frame_array, cv2.COLOR_BGR5652BGR)
            elif img_size == 236800: # RGB565 CIF (400x296)
                width, height = 400, 296
                frame_array = np.frombuffer(img_data, dtype=np.uint16).byteswap().view(np.uint8).reshape((height, width, 2))
                frame = cv2.cvtColor(frame_array, cv2.COLOR_BGR5652BGR)
            elif img_size == 614400: # RGB565 VGA (640x480)
                width, height = 640, 480
                frame_array = np.frombuffer(img_data, dtype=np.uint16).byteswap().view(np.uint8).reshape((height, width, 2))
                frame = cv2.cvtColor(frame_array, cv2.COLOR_BGR5652BGR)

            if frame is not None:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                frame = self.apply_image_adjustments(frame)
                return frame 
        return None

    def liberar(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Puerto serial cerrado.")
