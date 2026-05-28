import pandas as pd
from pylsl import StreamInlet, resolve_streams
import threading
import time
import os
import re

class GrabadorEEG:
    def __init__(self, ruta_archivo):
        self.ruta_archivo = ruta_archivo
        self.grabando = False
        self.datos = []
        self.eventos_recibidos = []
        self.canales = [f'Channel {i+1}' for i in range(14)]
        self.start_time = None

    def iniciar(self):
        print("\n>>> Iniciando Radar LSL (Buscando por 3 segundos)...")
        
        flujos_encontrados = {
            'eeg': None,
            'markers': None
        }
        
        try:
            streams = resolve_streams(3.0)
            
            print("\n--- FLUJOS LSL DETECTADOS EN TU PC ---")
            if not streams:
                print("Ninguno.")
            else:
                for s in streams:
                    print(f" -> Nombre: '{s.name()}' | Tipo: '{s.type()}' | Canales: {s.channel_count()}")
                    
                    # Identificamos tus marcadores
                    if s.type() == 'Markers' or 'Markers' in s.name():
                        flujos_encontrados['markers'] = s
                    
                    # Cualquier otra cosa que NO sean marcadores, la tomamos como el EEG
                    elif flujos_encontrados['eeg'] is None:
                        flujos_encontrados['eeg'] = s
            print("--------------------------------------\n")

            if flujos_encontrados['eeg'] is None:
                print("[Error Crítico] OpenViBE NO está enviando datos por LSL.")
                print("Solución: El administrador debe habilitar un 'LSL Export' o usar un Driver LSL en el Server.")
                return False

            # Si detectó algo, forzamos la conexión
            self.inlet_eeg = StreamInlet(flujos_encontrados['eeg'])
            print(f">>> Conectado exitosamente a la señal: {flujos_encontrados['eeg'].name()}")
            
            if flujos_encontrados['markers'] is not None:
                self.inlet_markers = StreamInlet(flujos_encontrados['markers'])
            else:
                self.inlet_markers = None

            self.grabando = True
            
            threading.Thread(target=self._capturar_eeg, daemon=True).start()
            if self.inlet_markers:
                threading.Thread(target=self._capturar_marcadores, daemon=True).start()
            
            return True

        except Exception as e:
            print(f"[Fallo en la lógica de inicio]: {e}")
            return False

    def _capturar_eeg(self):
        while self.grabando:
            try:
                muestra, timestamp = self.inlet_eeg.pull_sample(timeout=1.0)
                if muestra:
                    if self.start_time is None:
                        self.start_time = timestamp
                    
                    t_rel = timestamp - self.start_time
                    
                    # --- FILTRO DEFINITIVO (Anti-corchetes) ---
                    # 1. Convertimos lo que sea que haya mandado LSL a texto plano
                    str_muestra = str(muestra)
                    
                    # 2. Extraemos ÚNICAMENTE los números (ignorando corchetes y comillas)
                    numeros_texto = re.findall(r"[-+]?\d*\.\d+|[-+]?\d+", str_muestra)
                    
                    # 3. Convertimos esos textos a valores decimales puros
                    muestra_limpia = [float(n) for n in numeros_texto]
                    
                    # 4. Aseguramos tener exactamente 14 canales para que no se desfase el CSV
                    if len(muestra_limpia) >= 14:
                        muestra_limpia = muestra_limpia[:14]
                    else:
                        muestra_limpia += [0.0] * (14 - len(muestra_limpia))
                        
                    # 5. Agregamos el tiempo, el epoch (0) y los 14 canales separados
                    self.datos.append([f"{t_rel:.10f}", 0] + muestra_limpia)
            except Exception as e:
                continue

    def _capturar_marcadores(self): # <-- Cambiar "markers" por "marcadores"
        while self.grabando:
            try:
                marker, timestamp = self.inlet_markers.pull_sample(timeout=0.1)
                if marker and self.start_time:
                    self.eventos_recibidos.append({
                        'id': marker[0],
                        'time': timestamp - self.start_time
                    })
            except:
                continue

    def detener(self):
        self.grabando = False
        if not self.datos:
            print("[Error] No se recibieron datos de señal.")
            return
            
        print(">>> Sincronizando marcas y exportando CSV...")
        df = pd.DataFrame(self.datos, columns=['Time:128Hz', 'Epoch'] + self.canales)
        df['Event Id'], df['Event Date'], df['Event Duration'] = "", "", "0"

        for ev in self.eventos_recibidos:
            idx = (df['Time:128Hz'].astype(float) - ev['time']).abs().idxmin()
            df.at[idx, 'Event Id'] = ev['id']
            df.at[idx, 'Event Date'] = f"{ev['time']:.10f}"

        df.to_csv(self.ruta_archivo, index=False, float_format='%.10f')
        print(f"[EXITO] Archivo generado: {self.ruta_archivo}")