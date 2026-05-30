import os
import serial
import time
import threading
from dotenv import load_dotenv
from constants.posiciones import POSICIONES
from modules.sujecion_evaluator import SujecionEvaluator
from constants.config import (
    PIN_BASE, PIN_HOMBRO, PIN_CODO, PIN_MUÑECA, PIN_ROTADOR, PIN_PINZA
)

load_dotenv()

class ArmController:
    def __init__(self, puerto=None, baudios=115200):
        self.puerto = puerto or os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
        self.baudios = baudios
        # Estado inicial sincronizado con el firmware
        self.estado_actual = {
            PIN_BASE: 90, 
            PIN_HOMBRO: 180, 
            2: 0, 
            PIN_CODO: 140, 
            PIN_MUÑECA: 90, 
            PIN_ROTADOR: 0, 
            PIN_PINZA: 80
        }
        self.distancia = 999
        self.mag1 = [0.0, 0.0, 0.0]
        self.mag2 = [0.0, 0.0, 0.0]
        self.intentos_y = 0
        self.esp32 = None
        self.running = True
        self.en_emergencia = False  # Nueva variable de estado
        self.busy = False # Flag para indicar movimiento en curso
        self.lock = threading.Lock()
        self.event_ok = threading.Event() # Evento para esperar el 'OK'
        
        # Estado de la pinza
        self.estado_pinza = "DESCONOCIDO" # "ABIERTA", "VACIA", "CON_OBJETO"
        self.sujetando_objetivo = False # Mantener por compatibilidad
        
        # Filtro para el sensor ToF
        self.lecturas_distancia = []
        self.max_lecturas = 5 # Promedio de 5 muestras para eliminar ruido
        
        self.evaluador_agarre = SujecionEvaluator()
        self.nombre_estado_actual = "HOME" # Tracking de estado para compensación
        
        self.conectar()
        
        self.lector_thread = threading.Thread(target=self._leer_serial, daemon=True)
        self.lector_thread.start()

    def conectar(self):
        try:
            # Abrir puerto con parámetros que evitan el reseteo brusco si es posible
            self.esp32 = serial.Serial(self.puerto, self.baudios, timeout=0.1)
            
            # Forzar un reset limpio para empezar de cero
            self.esp32.setDTR(False)
            time.sleep(0.5)
            self.esp32.setDTR(True)
            
            print(f"[BRAZO] Conectado en {self.puerto}. Esperando SYSTEM_READY...")
            
            # Limpiar basura acumulada en el puerto de la PC
            self.esp32.reset_input_buffer()
            self.esp32.reset_output_buffer()

            inicio = time.time()
            ready = False
            while time.time() - inicio < 5: 
                if self.esp32.in_waiting > 0:
                    linea = self.esp32.readline().decode('utf-8', errors='ignore').strip()
                    if "SYSTEM_READY" in linea:
                        print("[BRAZO] ESP32 lista y sincronizada.")
                        ready = True
                        break
            
            if not ready:
                print("[BRAZO] Advertencia: No se detectó SYSTEM_READY, el inicio podría ser brusco.")
            
            # Un pequeño respiro antes del primer comando
            time.sleep(0.5)
            self.esp32.reset_input_buffer()
            
        except Exception as e:
            print(f"[BRAZO] Error de conexión: {e}")

    def _leer_serial(self):
        buffer = ""
        while self.running and self.esp32 and self.esp32.is_open:
            try:
                if self.esp32.in_waiting > 0:
                    datos = self.esp32.read(self.esp32.in_waiting).decode('utf-8', errors='ignore')
                    buffer += datos
                    if '\n' in buffer:
                        lineas = buffer.split('\n')
                        for linea in lineas[:-1]:
                            linea = linea.strip()
                            if linea == "OK":
                                self.event_ok.set()
                            elif "boton precionado" in linea:
                                with self.lock:
                                    self.en_emergencia = True
                                print("\n" + "!"*50)
                                print("!!! PARO DE EMERGENCIA DETECTADO !!!")
                                print("!"*50 + "\n")
                            elif "boton liberado" in linea:
                                with self.lock:
                                    self.en_emergencia = False
                                print("[SISTEMA] Botón de emergencia liberado.")
                            elif linea.startswith("DIST:"):
                                try:
                                    nueva_dist = int(linea.split(":")[1])
                                    # Filtro básico: Ignorar lecturas fuera de rango lógico (0-1200mm)
                                    if 0 < nueva_dist < 1200:
                                        with self.lock:
                                            self.lecturas_distancia.append(nueva_dist)
                                            if len(self.lecturas_distancia) > self.max_lecturas:
                                                self.lecturas_distancia.pop(0)
                                            # Mantener self.distancia como el promedio actual
                                            self.distancia = sum(self.lecturas_distancia) // len(self.lecturas_distancia)
                                except: pass
                            elif linea.startswith("MAG1:"):
                                try:
                                    vals = [float(x) for x in linea.split(":")[1].split(",")]
                                    
                                    with self.lock:
                                        self.mag1 = vals
                                        
                                        # PRIORIDAD: Verificar el ángulo del servo de la pinza
                                        angulo_pinza = self.estado_actual.get(PIN_PINZA, 80)
                                        
                                        if angulo_pinza >= 80:
                                            self.estado_pinza = "ABIERTA"
                                            self.sujetando_objetivo = False
                                            self.evaluador_agarre.reset() 
                                        else:
                                            # 1. Obtener estado de presencia
                                            resultado_presencia = self.evaluador_agarre.evaluar_agarre(
                                                vals[0], vals[1], vals[2], 
                                                estado_actual=self.nombre_estado_actual
                                            )
                                            self.estado_pinza = resultado_presencia
                                            self.sujetando_objetivo = (resultado_presencia == "CON_OBJETO")
                                            
                                            # 2. Sincronizar flag de colisión independiente
                                            self.colision_detectada = self.evaluador_agarre.hubo_colision
                                except: pass
                        buffer = lineas[-1]
                time.sleep(0.005)
            except: break

    def mover_tiempo(self, movimientos, forzar=False, esperar=True):
        if not self.esp32 or not self.esp32.is_open: return
        if self.en_emergencia:
            print("[BRAZO] Comando ignorado: El sistema está en PARO DE EMERGENCIA.")
            return

        with self.lock: self.busy = True

        necesarios = []
        for p, a in movimientos:
            # Límite extendido para el Pin de rotación (270 grados), 180 para los demás
            limite = 270 if p == PIN_ROTADOR else 180
            ang = max(0, min(limite, a))
            
            if forzar or self.estado_actual.get(p) != ang:
                necesarios.append((p, ang))
        
        if not necesarios: 
            with self.lock: self.busy = False
            return
        
        cadena = "$" + ";".join([f"{p}, {a}" for p, a in necesarios]) + "\n"
        
        with self.lock:
            try:
                print(f"[SERIAL SEND] {cadena.strip()}") 
                self.event_ok.clear()
                self.esp32.write(cadena.encode('utf-8'))
                self.esp32.flush()
                
                # Actualizar estado local
                for p, a in necesarios: self.estado_actual[p] = a
            except Exception as e:
                print(f"ERROR SERIAL: {e}")
                self.busy = False
                return

        # Esperar confirmación para sincronizar movimientos largos
        if esperar:
            if not self.event_ok.wait(timeout=10.0): 
                print("[BRAZO] Advertencia: Timeout esperando OK")
        
        with self.lock: self.busy = False

    def centrar_ibvs(self, error_x, error_y, paso_x=1, paso_y=1):
        """Ajuste fino basado en visión (IBVS) con compensación de muñeca integrada."""
        tolerancia = 8
        if abs(error_x) <= tolerancia and abs(error_y) <= tolerancia:
            return True
            
        cmds = []
        
        # Lectura segura utilizando .get()
        ang_base = self.estado_actual.get(PIN_BASE, 90)
        if error_x > tolerancia: 
            cmds.append((PIN_BASE, ang_base - paso_x))
        elif error_x < -tolerancia: 
            cmds.append((PIN_BASE, ang_base + paso_x))
        
        ang_muneca = self.estado_actual.get(PIN_MUÑECA, 90)
        if error_y > tolerancia: 
            cmds.append((PIN_MUÑECA, ang_muneca + paso_y))
        elif error_y < -tolerancia: 
            cmds.append((PIN_MUÑECA, ang_muneca - (paso_y + 1)))
        
        if cmds: self.mover_tiempo(cmds, esperar=False)
        return False

    def centrar_proporcional(self, error_x, error_y):
        """Ajuste inteligente basado en un controlador Proporcional con compensación reforzada."""
        tolerancia = 10
        kp_x = 0.03 
        kp_y = 0.02  
        max_paso = 4 
        
        if abs(error_x) <= tolerancia and abs(error_y) <= tolerancia:
            return True 
            
        cmds = []
        
        paso_x = int(error_x * kp_x)
        if abs(paso_x) > max_paso:
            paso_x = max_paso if paso_x > 0 else -max_paso
        if paso_x == 0 and abs(error_x) > tolerancia:
            paso_x = 1 if error_x > 0 else -1

        if abs(error_x) > tolerancia:
            ang_base = self.estado_actual.get(PIN_BASE, 90)
            nuevo_angulo = ang_base - paso_x
            cmds.append((PIN_BASE, nuevo_angulo))

        paso_y = int(error_y * kp_y)
        if abs(paso_y) > max_paso:
            paso_y = max_paso if paso_y > 0 else -max_paso
        if paso_y == 0 and abs(error_y) > tolerancia:
            paso_y = 1 if error_y > 0 else -1

        if abs(error_y) > tolerancia:
            self.intentos_y += 1
            ajuste_muñeca = paso_y
            if paso_y < 0: 
                ajuste_muñeca -= 1 
                
            ang_muneca = self.estado_actual.get(PIN_MUÑECA, 90)
            nuevo_angulo_15 = ang_muneca + ajuste_muñeca
            cmds.append((PIN_MUÑECA, nuevo_angulo_15))
            
            if self.intentos_y >= 5:
                paso_6 = 1 if error_y > 0 else -1
                ang_codo = self.estado_actual.get(PIN_CODO, 140)
                nuevo_angulo_6 = ang_codo + paso_6
                cmds.append((PIN_CODO, nuevo_angulo_6))
                self.intentos_y = 0 
        else:
            self.intentos_y = 0
            
        if cmds:
            self.mover_tiempo(cmds, esperar=False) 
            
        return False

    def obtener_distancia(self):
        """Retorna la última distancia leída por el sensor ToF."""
        return self.distancia

    def mover_a_estado(self, nombre_estado, forzar=False, esperar=False):
        """Mueve el brazo a una posición predefinida en posiciones.py."""
        if nombre_estado in POSICIONES:
            print(f"[BRAZO] Moviendo a estado: {nombre_estado}")
            self.nombre_estado_actual = nombre_estado 
            self.mover_tiempo(POSICIONES[nombre_estado], forzar=forzar, esperar=esperar)
        else:
            print(f"[BRAZO] Error: Estado '{nombre_estado}' no encontrado en posiciones.py")

    def cerrar(self):
        self.running = False
        if self.esp32 and self.esp32.is_open:
            self.esp32.close()
            print("[BRAZO] Puerto serial cerrado.")