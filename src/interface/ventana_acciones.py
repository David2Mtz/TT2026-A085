import customtkinter as ctk
from PIL import Image, ImageTk
import os
import sys
import cv2
import threading
import time

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path: sys.path.insert(0, ROOT_DIR)

class VentanaAccionesBrazo(ctk.CTkToplevel):
    def __init__(self, master, estado="Home", color=None):
        super().__init__(master)
        self.title("Panel de Control Robótico - ESCOM")
        self.geometry("1000x700")
        self.configure(fg_color="#F0F0F0")
        self.color = color or "Desconocido"
        self.ciclo = None
        self.camera_feed_running = False
        
        # Interceptar el botón "X" de la ventana para que también haga el cierre seguro
        self.protocol("WM_DELETE_WINDOW", self.regresar_inicio)
        
        self._setup_ui()

    def _get_color_hex(self, color_name):
        colores = {"Rojo": "#E74C3C", "Verde": "#2ECC71", "Azul": "#3498DB"}
        return colores.get(color_name.capitalize(), "#333333")

    def _setup_ui(self):
        self.lbl_titulo_principal = ctk.CTkLabel(self, text="SUPERVISIÓN DE CICLO ROBÓTICO", font=("Arial", 32, "bold"), text_color="#333333")
        self.lbl_titulo_principal.pack(pady=(30, 20))

        self.frame_telemetria = ctk.CTkFrame(self, fg_color="white", corner_radius=15, border_width=2, border_color="#D1D1D1")
        self.frame_telemetria.place(relx=0.5, rely=0.48, anchor="center")

        ctk.CTkLabel(self.frame_telemetria, text="OBJETIVO ASIGNADO", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 2), padx=60)
        color_texto = self._get_color_hex(self.color)
        self.lbl_objetivo = ctk.CTkLabel(self.frame_telemetria, text=self.color.upper(), font=("Consolas", 30, "bold"), text_color=color_texto)
        self.lbl_objetivo.pack(pady=(0, 20), padx=60)

        ctk.CTkLabel(self.frame_telemetria, text="ESTADO DEL ROBOT", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(5, 2), padx=60)
        self.lbl_estado = ctk.CTkLabel(self.frame_telemetria, text="PREPARANDO SISTEMA...", font=("Consolas", 24, "bold"), text_color="#007ACC")
        self.lbl_estado.pack(pady=(0, 20), padx=60)

        ctk.CTkLabel(self.frame_telemetria, text="ESTADO DE LA PINZA", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(5, 2), padx=60)
        self.lbl_pinza = ctk.CTkLabel(self.frame_telemetria, text="---", font=("Consolas", 24, "bold"), text_color="#333333")
        self.lbl_pinza.pack(pady=(0, 25), padx=60)

        self.frame_camara = ctk.CTkFrame(self, fg_color="black", corner_radius=8)
        self.frame_camara.place(relx=0.98, rely=0.97, anchor="se")

        self.label_feed_camara = ctk.CTkLabel(self.frame_camara, text="[ Sincronizando Cámara... ]", width=480, height=270, font=("Consolas", 14), text_color="gray")
        self.label_feed_camara.pack(padx=3, pady=3)

        self.btn_regresar = ctk.CTkButton(
            self, text="Cancelar y Regresar a Inicio", 
            height=45, width=220, fg_color="#E74C3C", hover_color="#C0392B", 
            font=("Arial", 14, "bold"), command=self.regresar_inicio
        )
        self.btn_regresar.place(relx=0.02, rely=0.97, anchor="sw")
        
        self.after(2000, self.iniciar_ciclo)

    def iniciar_ciclo(self):
        if self.ciclo and self.ciclo.is_alive(): return
        from modules.ciclo_robot import CicloRobot
        self.ciclo = CicloRobot(color_objetivo=self.color, callback_datos=self.actualizar_telemetria)
        self.ciclo.start()
        self.camera_feed_running = True
        self._actualizar_live_feed()

    def actualizar_telemetria(self, datos):
        self.after(0, lambda: self._dibujar_telemetria(datos))

    def _dibujar_telemetria(self, datos):
        estado = datos.get("estado", "DESCONOCIDO").replace("_", " ")
        pinza = datos.get("pinza", "---").replace("_", " ")
        
        self.lbl_estado.configure(text=estado)
        self.lbl_pinza.configure(text=pinza)
        
        if "EMERGENCIA" in estado or "ERROR" in estado or "ABORTANDO" in estado:
            self.lbl_estado.configure(text_color="#CC0000")
        elif "FINALIZADO" in estado:
            self.lbl_estado.configure(text_color="#008000")
            self.camera_feed_running = False
        # Para la nueva alerta en naranja:
        elif "SOLTANDO EN" in estado:
            self.lbl_estado.configure(text_color="#F39C12") 
        else:
            self.lbl_estado.configure(text_color="#007ACC")

        if "CON OBJETO" in pinza:
            self.lbl_pinza.configure(text_color="#008000")
        elif "VACIA" in pinza:
            self.lbl_pinza.configure(text_color="#CC0000")
        else:
            self.lbl_pinza.configure(text_color="#333333")

    def _actualizar_live_feed(self):
        if not self.camera_feed_running or not hasattr(self, 'ciclo') or not self.ciclo.is_alive():
            return

        frame_cv2 = self.ciclo.get_latest_frame()
        if frame_cv2 is not None:
            frame_rgb = cv2.cvtColor(frame_cv2, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            ctk_img = ctk.CTkImage(light_image=pil_image, size=(480, 270))
            self.label_feed_camara.configure(image=ctk_img, text="")
            self.label_feed_camara.image = ctk_img 

        self.after(30, self._actualizar_live_feed)

    # ========================================================
    # NUEVA RUTINA DE CIERRE SEGURO (MANDA A HOME Y LUEGO CIERRA)
    # ========================================================
    def regresar_inicio(self):
        # 1. Bloqueamos el botón y avisamos al usuario
        self.btn_regresar.configure(state="disabled", text="Aparcando robot...")
        self.lbl_estado.configure(text="ABORTANDO A HOME...", text_color="#E74C3C")
        self.camera_feed_running = False
        
        # 2. Iniciamos el cierre en un hilo para no congelar la ventana gráfica
        threading.Thread(target=self._hilo_cierre_seguro, daemon=True).start()

    def _hilo_cierre_seguro(self):
        if self.ciclo and self.ciclo.is_alive():
            self.ciclo.stop() # Activa el bloque 'finally' de ciclo_robot.py
            
            # Le damos 4 segundos físicos al brazo para que llegue a HOME antes de apagar
            time.sleep(4.0) 
        
        # 3. Cerramos la ventana desde el hilo principal
        self.after(0, self._destruir_ventana)

    def _destruir_ventana(self):
        try:
            self.master.deiconify()
        except:
            pass
        self.destroy()