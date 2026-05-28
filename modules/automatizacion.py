import subprocess
import os
import time

class AutomatizadorBCI:
    def __init__(self, ov_path=None):
        # Rutas a los ejecutables de OpenViBE (Ajusta según tu instalación)
        # Prioridad: argumento > env OPENVIBE_PATH > valor por defecto
        default_path = r"C:\Program Files\openvibe-3.7.0-64bit\bin\openvibe-acquisition-server.exe"
        self.ov_path = ov_path or os.environ.get('OPENVIBE_PATH') or default_path
        self.proceso_server = None

    def iniciar_servidor(self):
        """Lanza el Acquisition Server en segundo plano configurado para LSL"""
        print(">>> Iniciando OpenViBE Acquisition Server...")
        try:
            # Verificar existencia del ejecutable antes de intentar iniciar
            if not os.path.exists(self.ov_path):
                print(f"[Error] No se encontró el ejecutable de OpenViBE en: {self.ov_path}")
                print("Indica la ruta correcta en el constructor o en la variable de entorno OPENVIBE_PATH.")
                return False

            # --no-gui permite que corra sin estorbar la interfaz de Python
            # --play inicia la adquisición inmediatamente
            self.proceso_server = subprocess.Popen([self.ov_path, "--no-gui", "--play"])
            time.sleep(2) # Esperar a que el driver conecte
            print("[OK] Servidor adquiriendo datos.")
            return True
        except Exception as e:
            print(f"[Error] No se pudo iniciar OpenViBE: {e}")
            self.proceso_server = None
            return False

    def detener_todo(self):
        if self.proceso_server:
            try:
                self.proceso_server.terminate()
                print(">>> Servidor detenido.")
            except Exception as e:
                print(f"[Error] No se pudo detener OpenViBE: {e}")