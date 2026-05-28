import pandas as pd
import numpy as np
import mne
import joblib
import os
import matplotlib.pyplot as plt
from scipy.fft import fft
from scipy.signal import correlate

class PredictorP300:
    def __init__(self, ruta_modelo, ruta_scaler):
        self.emotiv_ch_names = ['AF3', 'F7', 'F3', 'FC5', 'T7', 'P7', 'O1', 'O2', 'P8', 'T8', 'FC6', 'F4', 'F8', 'AF4']
        self.sfreq = 128
        self.modelo_cargado = False
        
        # Normalizar rutas y Carga de modelo y escalador
        ruta_modelo = os.path.abspath(os.path.expanduser(ruta_modelo)) if ruta_modelo else ruta_modelo
        ruta_scaler = os.path.abspath(os.path.expanduser(ruta_scaler)) if ruta_scaler else ruta_scaler

        if ruta_modelo and ruta_scaler and os.path.exists(ruta_modelo) and os.path.exists(ruta_scaler):
            self.model = joblib.load(ruta_modelo)
            self.scaler = joblib.load(ruta_scaler)
            self.modelo_cargado = True
            print("[OK] Modelo y Escalador Universal cargados correctamente.")
        else:
            print(f"[Error] No se encontraron los archivos .joblib. Verifica las rutas: {ruta_modelo}, {ruta_scaler}")

    def convertir_a_uv(self, ruta_archivo, factor=0.5):
        """
        Lee el CSV, convierte las columnas EEG de ADC a µV restando el offset,
        guarda el nuevo archivo '_uV.csv' y retorna la ruta del nuevo archivo.
        """
        if not os.path.exists(ruta_archivo):
            print(f"[Error] No se encontró el archivo: {ruta_archivo}")
            return ruta_archivo

        # Si el archivo ya tiene el sufijo _uV, evitamos procesarlo doblemente
        if ruta_archivo.endswith("_uV.csv"):
            return ruta_archivo

        try:
            df = pd.read_csv(ruta_archivo)
            
            # Detectar automáticamente las columnas del EEG (Channel 1, Channel 2, etc.)
            columnas_eeg = [c for c in df.columns if 'Channel' in c]
            
            if not columnas_eeg:
                # Fallback por si las columnas ya se llaman AF3, F7, etc.
                columnas_eeg = [c for c in self.emotiv_ch_names if c in df.columns]

            for col in columnas_eeg:
                # Calcular el offset como la media del canal (componente DC)
                offset = df[col].mean()
                # Restar offset para centrar en 0, luego escalar a µV
                df[col] = (df[col] - offset) * factor

            # Generar el nuevo nombre de archivo
            nombre_base, extension = os.path.splitext(ruta_archivo)
            ruta_salida = f"{nombre_base}_uV{extension}"

            # Guardar el archivo convertido
            df.to_csv(ruta_salida, index=False)
            print(f"[OK] Archivo convertido a µV y guardado como: {os.path.basename(ruta_salida)}")
            
            return ruta_salida

        except Exception as e:
            print(f"[Error] Fallo al convertir a µV: {e}")
            return ruta_archivo # Retorna el original en caso de fallo para no romper el programa

    def extraer_7_features(self, epoch, lat_muestras=48):
        """Extrae los 7 predictores por canal."""
        n_ch = epoch.shape[1]
        feats = []
        t = np.linspace(0, 0.8, epoch.shape[0])
        template = np.exp(-((t - (lat_muestras/self.sfreq))**2) / (2 * 0.05**2))

        for ch in range(n_ch):
            sig = epoch[:, ch]
            corr = correlate(sig, template, mode='same')
            yf = np.abs(fft(sig))
            
            feats.extend([
                np.max(sig), np.argmax(sig),
                corr[len(corr)//2], np.trapezoid(np.abs(corr)),
                np.mean(yf[int(len(sig)*4/self.sfreq):int(len(sig)*6/self.sfreq)]),
                np.trapezoid(np.abs(sig)),
                np.var(sig)
            ])
        return np.array(feats)

    def predecir_intencion(self, ruta_csv):
        if not self.modelo_cargado:
            print("[Error] No se puede predecir, el modelo no está cargado.")
            return None

        # 1. Convertir el archivo a µV ANTES de analizarlo
        ruta_csv_uv = self.convertir_a_uv(ruta_csv)

        # 2. Cargar datos y limpiar (ahora usando el archivo en µV)
        df = pd.read_csv(ruta_csv_uv)
        df.columns = [c.strip() for c in df.columns]
        
        # Corrección de columnas
        if 'AF3' not in df.columns:
            columnas_eeg = [c for c in df.columns if 'Channel' in c]
            if len(columnas_eeg) >= 14:
                mapeo = dict(zip(columnas_eeg[:14], self.emotiv_ch_names))
                df = df.rename(columns=mapeo)
            else:
                columnas_idx = df.columns[0:14] 
                df = df.rename(columns=dict(zip(columnas_idx, self.emotiv_ch_names)))

        col_eventos = [c for c in df.columns if 'Event' in c or 'Id' in c]
        if col_eventos:
            df = df.rename(columns={col_eventos[0]: 'Event Id'})
        else:
            print("[Error] No se encontró la columna de eventos (Event Id)")
            return None

        # 3. Limpiar y Filtrar (0.1 - 15 Hz)
        # Nota: Multiplicamos por 1e-6 porque MNE siempre espera recibir Voltios (y los datos están en µV)
        data = df[self.emotiv_ch_names].apply(pd.to_numeric, errors='coerce').fillna(0).values.T * 1e-6
        info = mne.create_info(ch_names=self.emotiv_ch_names, sfreq=self.sfreq, ch_types='eeg')
        raw = mne.io.RawArray(data, info, verbose=False)
        raw.filter(l_freq=0.1, h_freq=15.0, verbose=False)
        raw_car, _ = mne.set_eeg_reference(raw, ref_channels='average', copy=True, verbose=False)

        # 4. Segmentar épocas
        markers = pd.to_numeric(df['Event Id'], errors='coerce').fillna(0).values
        data_uv = raw_car.get_data().T * 1e6
        
        puntajes = {1: 0.0, 2: 0.0, 3: 0.0}
        conteo_epocas = {1: 0, 2: 0, 3: 0}

        indices = np.where((markers >= 1) & (markers <= 3))[0]
        
        for idx in indices:
            color_id = int(markers[idx])
            if idx + 102 < len(data_uv):
                epoch = data_uv[idx : idx + 102]
                epoch -= np.mean(epoch[:12], axis=0) # Baseline
                
                feats = self.extraer_7_features(epoch).reshape(1, -1)
                feats_sc = self.scaler.transform(feats)
                prob = self.model.predict_proba(feats_sc)[0][1]
                
                puntajes[color_id] += prob
                conteo_epocas[color_id] += 1

        # 5. Decisión Final
        ganador = max(puntajes, key=puntajes.get)
        colores_map = {1: "Rojo", 2: "Verde", 3: "Azul"}
        
        print("\n--- RESULTADOS PREDICCIÓN ---")
        for cid, p in puntajes.items():
            avg_p = p / conteo_epocas[cid] if conteo_epocas[cid] > 0 else 0
            print(f"Color {colores_map[cid]}: Confianza {avg_p:.4f} ({conteo_epocas[cid]} épocas)")
            
        return colores_map[ganador]

    def graficar_erp(self, ruta_csv, sujeto_nombre="Nuevo Sujeto"):
        # Se convierte a µV si es necesario para graficar limpio
        ruta_csv_uv = self.convertir_a_uv(ruta_csv)
        window_size = int(self.sfreq * 0.8) 

        df = pd.read_csv(ruta_csv_uv)
        data = df[self.emotiv_ch_names].apply(pd.to_numeric, errors='coerce').fillna(0).values.T * 1e-6
        info = mne.create_info(ch_names=self.emotiv_ch_names, sfreq=self.sfreq, ch_types='eeg')
        raw = mne.io.RawArray(data, info, verbose=False)
        raw.filter(l_freq=1.0, h_freq=12.0, verbose=False) 
        raw_car, _ = mne.set_eeg_reference(raw, ref_channels='average', copy=True, verbose=False)
        
        clean_data = raw_car.get_data().T * 1e6
        markers = pd.to_numeric(df['Event Id'], errors='coerce').fillna(0).values

        target_id = 0
        ruta_lower = ruta_csv_uv.lower()
        if 'azul' in ruta_lower: target_id = 3
        elif 'rojo' in ruta_lower: target_id = 1
        elif 'verde' in ruta_lower: target_id = 2

        target_epochs, nontarget_epochs = [], []
        indices = np.where((markers >= 1) & (markers <= 3))[0]
        
        for idx in indices:
            if idx + window_size < len(clean_data):
                epoch = clean_data[idx : idx + window_size]
                epoch -= np.mean(epoch[:12], axis=0)
                
                if int(markers[idx]) == target_id: target_epochs.append(epoch)
                else: nontarget_epochs.append(epoch)

        if len(target_epochs) > 0:
            avg_target = np.mean(target_epochs, axis=0)
            avg_nontarget = np.mean(nontarget_epochs, axis=0)
            t = np.linspace(0, 800, window_size)

            plt.figure(figsize=(15, 10))
            canales_a_ver = ['O1', 'O2', 'P7', 'P8', 'F3', 'F4']
            
            for i, ch in enumerate(canales_a_ver):
                plt.subplot(3, 2, i+1)
                ch_idx = self.emotiv_ch_names.index(ch)
                plt.plot(t, avg_target[:, ch_idx], label='TARGET', color='blue', linewidth=2)
                plt.plot(t, avg_nontarget[:, ch_idx], label='Non-Target', color='gray', linestyle='--', alpha=0.6)
                plt.title(f'Canal {ch}')
                plt.axvline(x=300, color='red', linestyle=':', alpha=0.4)
                plt.axvline(x=450, color='red', linestyle=':', alpha=0.4)
                plt.axhline(0, color='black', linewidth=0.5)
                plt.xlabel('ms')
                plt.ylabel('uV')
                plt.grid(True, alpha=0.2)
                if i == 0: plt.legend()

            plt.suptitle(f'ERP - {sujeto_nombre}\n{os.path.basename(ruta_csv_uv)}', fontsize=16)
            plt.tight_layout(rect=[0, 0.03, 1, 0.95])
            plt.show()
        else:
            print("No se encontraron marcas de estímulos para graficar.")