import tkinter as tk
import random
import csv
import time
import threading
import os
import sys
import json
from tkinter import messagebox
from tkinter import ttk
from numpy import info
from pylsl import StreamInfo, StreamOutlet

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Ruta al root del proyecto (un par de niveles arriba desde src/interface)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.automatizacion import AutomatizadorBCI
from modules.grabador_eeg import GrabadorEEG
from modules.prediccion_p300 import PredictorP300

# ─── CONFIGURACIÓN DE COLORES Y RUTAS ──────────────────────────────────────────
RUTA_LOGS = os.path.join(PROJECT_ROOT, 'logs')

# Rutas relativas en el proyecto
ARCHIVO_CONFIG = os.path.join(PROJECT_ROOT, 'utils', 'config_comprimidos.json')
MODELO_P300_PATH = os.path.join(PROJECT_ROOT, 'models', 'modelo_P300_UNIVERSAL_v1.joblib')
SCALER_P300_PATH = os.path.join(PROJECT_ROOT, 'models', 'scaler_UNIVERSAL_v1.joblib')

# Paleta de Colores
NEGRO, BLANCO, GRIS = '#000000', '#FFFFFF', '#282828'
# Colores Brillantes (Objetivos)
COLORES_OBJETIVOS = {
    'Rojo': '#FF0000',
    'Verde': '#00FF00',
    'Azul': '#0000FF'
}
# Colores Pastel (Distractores / Requerimiento No Funcional)
AMARILLO_P, NARANJA_P, VIOLETA_P = '#FFFFCC', '#FFCCB3', '#E6B3E6'
ROSA_P, CIAN_P = '#F0C8FF', '#D9B3B3'

class InterfazP300(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title('Paradigma P300 - Estimulación Visual')
        self.geometry('800x600')
        self.configure(bg=NEGRO)
        
        self.corriendo = False
        self.medicamentos_config = {}
        self.marker_map = {'InicioExperimento': 99, 'FinExperimento': 100}
        
        self.cargar_configuracion_y_lsl()
        
        # UI Setup
        self.canvas = tk.Canvas(self, bg=NEGRO, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.id_circulo = self.canvas.create_oval(0, 0, 1, 1, fill=GRIS, outline=BLANCO, width=3)
        self.id_texto = self.canvas.create_text(0, 0, text='Presione espacio para iniciar', fill=BLANCO, font=('Arial', 20, 'bold'))
        
        # --- LÍNEA CLAVE: Detectar redimensionamiento ---
        self.canvas.bind('<Configure>', self.centrar_elementos)
        
        self.bind('<space>', self.iniciar_experimento)
        self.bind('<Escape>', lambda e: self.regresar_a_principal())
        self.protocol('WM_DELETE_WINDOW', self.regresar_a_principal)
        self.after(100, self.centrar_elementos)

    def cargar_configuracion_y_lsl(self):
        json_cargado_exito = False
        
        # 1. Intentar Cargar JSON generado en la pantalla anterior
        if os.path.exists(ARCHIVO_CONFIG):
            try:
                with open(ARCHIVO_CONFIG, 'r') as f:
                    data = json.load(f)
                    for item in data.get('mapeo_comprimidos', []):
                        nombre = item['nombre']
                        color_nombre = item['color_asignado']
                        self.medicamentos_config[nombre] = COLORES_OBJETIVOS.get(color_nombre, BLANCO)
                        self.marker_map[nombre] = item['id_interno']
                json_cargado_exito = True
            except Exception as e:
                print(f"[Aviso] Error al leer el JSON: {e}")

        # --- SISTEMA DE EMERGENCIA (FALLBACK) ---
        if not json_cargado_exito or len(self.medicamentos_config) == 0:
            print("[Aviso] Usando configuración de prueba (Rojo, Verde, Azul).")
            self.medicamentos_config['Opción_Rojo'] = COLORES_OBJETIVOS['Rojo']
            self.marker_map['Opción_Rojo'] = 1
            
            self.medicamentos_config['Opción_Verde'] = COLORES_OBJETIVOS['Verde']
            self.marker_map['Opción_Verde'] = 2
            
            self.medicamentos_config['Opción_Azul'] = COLORES_OBJETIVOS['Azul']
            self.marker_map['Opción_Azul'] = 3

        # 2. Agregar distractores pastel obligatorios
        distractores = {
            'D1': AMARILLO_P, 'D2': NARANJA_P, 
            'D3': VIOLETA_P, 'D4': ROSA_P, 'D5': CIAN_P
        }
        for k, v in distractores.items():
            self.medicamentos_config[k] = v
            self.marker_map[k] = len(self.marker_map) + 10 

        # 3. Preparar LSL
        info = StreamInfo('PythonP300_Markers', 'Markers', 1, 0, 'int32', 'p300_escom')
        self.outlet = StreamOutlet(info)
        
        # 4. Preparar Log CSV
        os.makedirs(RUTA_LOGS, exist_ok=True)
        self.ruta_csv = os.path.join(RUTA_LOGS, f"log_exp_{int(time.time())}.csv")
        self.archivo_log = open(self.ruta_csv, 'w', newline='')
        self.escritor = csv.writer(self.archivo_log)
        self.escritor.writerow(['timestamp', 'estimulo', 'codigo'])

    def centrar_elementos(self, event=None):
        # Obtener dimensiones actuales del Canvas
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        
        # Evitar cálculos si la ventana aún no se dibuja (w o h = 1)
        if w <= 1 or h <= 1:
            return

        # Calcular el centro
        cx, cy = w / 2, h / 2
        
        # Calcular radio dinámico (90% del espacio disponible)
        # Usamos min(w, h) para que no se corte si la ventana es muy ancha o muy alta
        r = (min(w, h) / 2) * 0.9
        
        # Actualizar círculo
        self.canvas.coords(self.id_circulo, cx - r, cy - r, cx + r, cy + r)
        
        # Actualizar texto (siempre al centro)
        self.canvas.coords(self.id_texto, cx, cy)
        
        # Ajustar tamaño de fuente dinámicamente según el tamaño del círculo
        nueva_fuente = int(r / 5) # Proporción ajustable
        if nueva_fuente < 12: nueva_fuente = 12 # Tamaño mínimo
        self.canvas.itemconfig(self.id_texto, font=('Arial', nueva_fuente, 'bold'))

    def generar_secuencia_sin_objetivos_consecutivos(self):
        nombres = list(self.medicamentos_config.keys())
        objetivos = set(k for k, v in self.medicamentos_config.items() if v in COLORES_OBJETIVOS.values())

        for _ in range(100):
            random.shuffle(nombres)
            anterior_objetivo = False
            valido = True

            for nombre in nombres:
                actual_objetivo = nombre in objetivos
                if anterior_objetivo and actual_objetivo:
                    valido = False
                    break
                anterior_objetivo = actual_objetivo

            if valido:
                return nombres.copy()

        # Si no encontramos una secuencia válida, devolvemos el orden original.
        return nombres

    def iniciar_experimento(self, event=None):
        if self.corriendo: return
        
        # 1. Crear el canal de marcadores inmediatamente
        info = StreamInfo('P300_Markers_TT', 'Markers', 1, 0, 'int32', 'escom_tt_2026')
        self.outlet = StreamOutlet(info)
        
        # 2. Pequeña pausa para que LSL registre el canal en la red
        print("Registrando marcadores en LSL...")
        time.sleep(1.0) 
        
        # 3. Iniciar OpenViBE si es necesario y luego el grabador
        self.auto = AutomatizadorBCI()

        nombre_csv = f"Exp_{time.strftime('%H%M%S')}.csv"
        self.ruta_completa_eeg = os.path.join(RUTA_LOGS, nombre_csv) # Guardamos la ruta en self para poder usarla al final
        self.grabador = GrabadorEEG(self.ruta_completa_eeg)
        
        if self.grabador.iniciar():
            self.corriendo = True
            self.canvas.itemconfig(self.id_texto, text='')
            threading.Thread(target=self.loop_estimulacion, daemon=True).start()
        else:
            if hasattr(self, 'auto'):
                self.auto.detener_todo()
            messagebox.showerror("Error LSL", 
                "No se encontró el flujo de OpenViBE.\n\n"
                "Verifique que en el Server el Driver sea 'Emotiv' y esté en 'PLAY'.")

    def loop_estimulacion(self):
        t_fin = time.time() + 35 # Duración 35s
        
        while self.corriendo and time.time() < t_fin:
            nombres = self.generar_secuencia_sin_objetivos_consecutivos()
            for nombre in nombres:
                if not self.corriendo: break
                
                # Encender estímulo
                color = self.medicamentos_config[nombre]
                codigo = self.marker_map[nombre]
                
                self.canvas.itemconfig(self.id_circulo, fill=color)
                self.outlet.push_sample([codigo])
                self.escritor.writerow([time.time(), nombre, codigo])
                
                time.sleep(0.175) # TIEMPO_ESTIMULO
                
                # Apagar (Relajación)
                self.canvas.itemconfig(self.id_circulo, fill=GRIS)
                time.sleep(0.250) # TIEMPO_RELAJACION
        
        self.finalizar()

    def finalizar(self):
        self.corriendo = False
        
        # 1. Enviar el marcador de finalización a LSL y cerrar log
        self.outlet.push_sample([self.marker_map['FinExperimento']])
        self.archivo_log.close()
        
        # 2. Detener el grabador EEG para que el CSV termine de escribirse
        if hasattr(self, 'grabador'):
            self.grabador.detener()
            
        # 3. Detener el servidor de OpenViBE si se inició desde aquí
        if hasattr(self, 'auto'):
            self.auto.detener_todo()
            
        # 4. TRANSICIÓN DE UI: Limpiar pantalla y mostrar barra de carga
        self.canvas.delete(self.id_circulo) # Ocultar el círculo parpadeante
        self.canvas.itemconfig(self.id_texto, text='Procesando señales EEG...\nAnalizando componentes P300...', fill=BLANCO)
        
        # Crear y posicionar la barra de progreso
        self.barra_progreso = ttk.Progressbar(self, mode='indeterminate', length=400)
        self.canvas.create_window(self.canvas.winfo_width()/2, self.canvas.winfo_height()/2 + 60, 
                                  window=self.barra_progreso, tags="barra")
        
        # Iniciar la animación de la barra
        self.barra_progreso.start(15) 
        
        self.after(4000, self.mostrar_resultado_modelo)

    def mostrar_resultado_modelo(self):
        # 1. Detener y destruir la barra de carga
        self.barra_progreso.stop()
        self.canvas.delete("barra")

        color_detectado = None
        codigo_hex = BLANCO

        try:
            predictor = PredictorP300(MODELO_P300_PATH, SCALER_P300_PATH)
            if predictor.modelo_cargado and hasattr(self, 'ruta_completa_eeg'):
                resultado = predictor.predecir_intencion(self.ruta_completa_eeg)
                if resultado:
                    color_detectado = resultado
        except Exception as e:
            print(f"[Error] Predicción P300 fallida: {e}")

        if color_detectado is None:
            objetivos_posibles = [nombre for nombre, color in self.medicamentos_config.items() if color in COLORES_OBJETIVOS.values()]
            if not objetivos_posibles:
                objetivos_posibles = ['Rojo', 'Verde', 'Azul']
            color_detectado = random.choice(objetivos_posibles)

        codigo_hex = COLORES_OBJETIVOS.get(color_detectado, BLANCO)

        # 3. Mostrar el gran resultado en pantalla
        mensaje_final = f"¡Análisis Completado!\n\nMayor nivel de atención detectado en:\n{color_detectado.upper()}"
        self.canvas.itemconfig(self.id_texto, text=mensaje_final, fill=codigo_hex, font=('Arial', 26, 'bold'))
        
        # Aquí podríamos agregar una transición a la ventana de parpadeos después de unos segundos
        self.after(5000, lambda: self.ventana_parpadeos(color_detectado))

        
        
    
    def regresar_a_principal(self):
        if hasattr(self.master, 'deiconify'):
            try:
                self.master.deiconify()
            except Exception:
                pass
        self.destroy()
        
    def ventana_parpadeos(self, color):
        from ventana_carga import VentanaCarga
        
        def tarea_cargar_parpadeos():
            import time
            # Truco de UX: Forzamos 1.5 segundos de carga visual para evitar el "flasheo" de la ventana
            time.sleep(1.5) 
            from ventana_parpadeos import VentanaParpadeos
            return VentanaParpadeos

        def al_terminar_de_cargar(clase_parpadeos):
            raiz = self.master
            self.destroy() # Destruimos la ventana del experimento
            if clase_parpadeos:
                clase_parpadeos(raiz, color)

        # 1. Ocultamos la ventana actual para limpiar la pantalla
        self.withdraw()
        
        # 2. Pasamos self.master (VentanaInicio) para que la pantalla de carga no desaparezca
        VentanaCarga(self.master, mensaje="Inicializando visión artificial (dlib)...", 
                     tarea_hilo=tarea_cargar_parpadeos, callback_fin=al_terminar_de_cargar)