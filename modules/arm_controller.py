# modules/arm_controller.py
import serial
import time
from constants.posiciones import POSICIONES

class ArmController:
    def __init__(self, puerto='/dev/ttyUSB0', baudios=9600):
        self.puerto = puerto
        self.baudios = baudios
        # Estado inicial (Gemelo Digital)
        self.estado_actual = {0: 0, 1: 180, 3: 170, 4: 90, 5: 90, 6: 10}
        self.esp32 = None
        self.conectar()

    def conectar(self):
        try:
            self.esp32 = serial.Serial(self.puerto, self.baudios, timeout=1)
            time.sleep(2)
            print("[BRAZO] Conectado exitosamente.")
        except Exception as e:
            print(f"[BRAZO] Error de conexión: {e}")

    def mover_a_estado(self, nombre_posicion):
        """Busca en el diccionario y ejecuta el movimiento."""
        if nombre_posicion in POSICIONES:
            print(f"\n--- [BRAZO] Moviendo a: {nombre_posicion} ---")
            movimientos = POSICIONES[nombre_posicion]
            self.mover_tiempo(movimientos)
        else:
            print(f"[ERROR] Posición {nombre_posicion} no definida.")

    def mover_tiempo(self, movimientos):
        """Envía comandos en bloques de 4 servos y espera confirmación 'OK'."""
        if not self.esp32: return

        # Filtrar solo los que realmente cambian
        necesarios = [(p, a) for p, a in movimientos if self.estado_actual.get(p) != a]
        if not necesarios: return

        # Enviar en bloques de 4
        for i in range(0, len(necesarios), 4):
            bloque = necesarios[i:i+4]
            cadena = ";".join([f"{p},{a}" for p, a in bloque]) + "\n"
            self.esp32.write(cadena.encode('utf-8'))
            
            # Espera síncrona del OK
            while True:
                if self.esp32.in_waiting > 0:
                    res = self.esp32.readline().decode('utf-8').strip()
                    if res == "OK":
                        for p, a in bloque: self.estado_actual[p] = a
                        break
                time.sleep(0.01)

    def centrar_ibvs(self, error_x, error_y):
        """Ajuste fino basado en visión (IBVS)."""
        tolerancia = 15
        paso = 1
        if abs(error_x) <= tolerancia and abs(error_y) <= tolerancia:
            return True # Centrado
            
        cmds = []
        if error_x > tolerancia: cmds.append((0, self.estado_actual[0] - paso))
        elif error_x < -tolerancia: cmds.append((0, self.estado_actual[0] + paso))
        
        if error_y > tolerancia: cmds.append((4, self.estado_actual[4] - paso))
        elif error_y < -tolerancia: cmds.append((4, self.estado_actual[4] + paso))
        
        if cmds: self.mover_tiempo(cmds)
        return False