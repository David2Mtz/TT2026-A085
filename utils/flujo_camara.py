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

    def get_frame(self, max_intentos=3):
        if not self.ser:
            return None

        for intento in range(max_intentos):
            self.ser.reset_input_buffer()
            self.ser.write(b'R')
            self.ser.flush()

            # 1. Esperar la cabecera usando read_until para ignorar basura inicial
            sync = self.ser.read_until(b'IMG:')
            if not sync.endswith(b'IMG:'):
                print(f"[Intento {intento+1}] Sin sincronización. Recibido: {sync}")
                time.sleep(0.05)
                continue

            # 2. Leer el tamaño
            size_bytes = self.ser.read(4)
            if len(size_bytes) != 4:
                print(f"[Intento {intento+1}] No se pudieron leer los 4 bytes de tamaño.")
                continue
            
            img_size = struct.unpack('<I', size_bytes)[0]
            if img_size == 0 or img_size > 500000: 
                print(f"[Intento {intento+1}] Tamaño de imagen anómalo: {img_size} bytes.")
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

            # 4. Decodificar
            frame_array = np.frombuffer(img_data, dtype=np.uint8)
            frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)

            if frame is not None:
                # --- Rotación de Imagen ---
                # Opciones: cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                
                return frame 
            else:
                print(f"[Intento {intento+1}] Error al decodificar la imagen.")
                
        return None

    def liberar(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Puerto serial cerrado.")