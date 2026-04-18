# modules/arm_controller.py
import os
import serial
import time
from dotenv import load_dotenv
from constants.posiciones import POSICIONES

load_dotenv()

class ArmController:
    def __init__(self, puerto=None, baudios=9600):
        self.puerto = puerto or os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
        self.baudios = baudios
        # Estado inicial (Gemelo Digital)
        self.estado_actual = {0: 0, 1: 180, 3: 170, 4: 90, 5: 90, 6: 10}
        self.intentos_y = 0 # Contador para asistencia del servo 3
        self.esp32 = None
        self.conectar()

    def conectar(self):
        try:
            self.esp32 = serial.Serial(self.puerto, self.baudios, timeout=1)
            time.sleep(2)
            self.esp32.reset_input_buffer()
            print("[BRAZO] Conectado exitosamente.")
        except Exception as e:
            print(f"[BRAZO] Error de conexión: {e}")

    def mover_a_estado(self, nombre_posicion):
        """Busca en el diccionario y ejecuta el movimiento."""
        if nombre_posicion in POSICIONES:
            print(f"\n--- [BRAZO] Moviendo a: {nombre_posicion} ---")
            movimientos = POSICIONES[nombre_posicion]
            # Usamos forzar=True para asegurar que todos los servos alcancen el ángulo,
            # incluso si el controlador cree que ya están ahí.
            self.mover_tiempo(movimientos, forzar=True)
        else:
            print(f"[ERROR] Posición {nombre_posicion} no definida.")

    def mover_tiempo(self, movimientos, forzar=False):
        """Envía comandos en bloques de 4 servos y espera confirmación 'OK'."""
        if not self.esp32 or not self.esp32.is_open:
            return

        # Filtrar solo los que realmente cambian y asegurar rango 0-180
        necesarios = []
        for p, a in movimientos:
            # Asegurar que el ángulo esté entre 0 y 180
            angulo_seguro = max(0, min(180, a))
            if forzar or self.estado_actual.get(p) != angulo_seguro:
                necesarios.append((p, angulo_seguro))
        
        if not necesarios: return

        # Limpiar basura previa solo una vez al inicio de la ráfaga
        self.esp32.reset_input_buffer()

        # Enviar de 1 en 1 para máxima fiabilidad en la recepción del ESP32
        for p, a in necesarios:
            print(f"   -> Enviando Servo {p} a {a}...", end=" ", flush=True)
            cadena = f"{p},{a}\n"
            try:
                self.esp32.write(cadena.encode('utf-8'))
                self.esp32.flush()
                
                # Espera síncrona del OK con mayor margen de tiempo
                timeout_espera = time.time() + 5.0 
                confirmado = False
                while time.time() < timeout_espera:
                    if self.esp32.in_waiting > 0:
                        # Leer todo lo disponible y buscar "OK"
                        respuesta = self.esp32.read(self.esp32.in_waiting).decode('utf-8', errors='ignore')
                        if "OK" in respuesta.upper():
                            self.estado_actual[p] = a
                            confirmado = True
                            print("OK")
                            break
                    time.sleep(0.01)
                
                if not confirmado:
                    print("TIMEOUT")
                    print(f"[BRAZO] Advertencia: No se recibió confirmación para servo {p}")
                
                # Pequeña pausa para estabilidad eléctrica
                time.sleep(0.02)
                
            except Exception as e:
                print(f"ERROR: {e}")

    def cerrar(self):
        """Cierra la conexión serial de forma segura."""
        if self.esp32 and self.esp32.is_open:
            self.esp32.close()
            print("[BRAZO] Puerto serial cerrado.")

    def centrar_ibvs(self, error_x, error_y):
        """Ajuste fino basado en visión (IBVS)."""
        tolerancia = 8
        paso = 1
        if abs(error_x) <= tolerancia and abs(error_y) <= tolerancia:
            return True # Centrado
            
        cmds = []
        # Ajuste X (Horizontal) -> Base (Servo 0)
        # Si el error es positivo (objeto a la derecha), sumamos para girar a esa dirección
        if error_x > tolerancia: cmds.append((0, self.estado_actual[0] + paso))
        elif error_x < -tolerancia: cmds.append((0, self.estado_actual[0] - paso))
        
        # Ajuste Y (Vertical) -> Muñeca (Servo 4)
        # Si el error es positivo (objeto abajo), sumamos para bajar la pinza (180 es abajo)
        if error_y > tolerancia: cmds.append((4, self.estado_actual[4] + paso))
        elif error_y < -tolerancia: cmds.append((4, self.estado_actual[4] - paso))
        
        if cmds: self.mover_tiempo(cmds)
        return False

    def centrar_proporcional(self, error_x, error_y):
        """Ajuste inteligente basado en un controlador Proporcional."""
        tolerancia = 10
        kp_x = 0.02  # Ganancia proporcional para X
        kp_y = 0.02  # Ganancia proporcional para Y
        max_paso = 3 # Límite de grados por movimiento
        
        if abs(error_x) <= tolerancia and abs(error_y) <= tolerancia:
            return True # Centrado
            
        cmds = []
        
        # Ajuste X (Horizontal) -> Base (Servo 0)
        # Calculamos paso proporcional al error
        paso_x = int(error_x * kp_x)
        if abs(paso_x) > max_paso:
            paso_x = max_paso if paso_x > 0 else -max_paso
        # Forzamos al menos 1 grado de movimiento si supera la tolerancia
        if paso_x == 0 and abs(error_x) > tolerancia:
            paso_x = 1 if error_x > 0 else -1
        
        if abs(error_x) > tolerancia:
            nuevo_angulo = self.estado_actual[0] + paso_x
            cmds.append((0, nuevo_angulo))
            
        # Ajuste Y (Vertical) -> Muñeca (Servo 4)
        paso_y = int(error_y * kp_y)
        if abs(paso_y) > max_paso:
            paso_y = max_paso if paso_y > 0 else -max_paso
        if paso_y == 0 and abs(error_y) > tolerancia:
            paso_y = 1 if error_y > 0 else -1
            
        if abs(error_y) > tolerancia:
            self.intentos_y += 1
            nuevo_angulo_4 = self.estado_actual[4] + paso_y
            cmds.append((4, nuevo_angulo_4))
            
            # Si después de 5 intentos el servo 4 no es suficiente, movemos el servo 3 un poquito
            if self.intentos_y >= 5:
                print(f"[ASISTENCIA] Servo 4 lento, moviendo Servo 3 para ayudar (Error Y: {error_y})")
                paso_3 = 1 if error_y > 0 else -1
                nuevo_angulo_3 = self.estado_actual[3] + paso_3
                cmds.append((3, nuevo_angulo_3))
                self.intentos_y = 0 # Reiniciamos contador tras la asistencia
        else:
            self.intentos_y = 0
            
        if cmds:
            self.mover_tiempo(cmds)
            
        return False
