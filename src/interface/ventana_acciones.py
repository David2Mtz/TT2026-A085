import customtkinter as ctk
from PIL import Image, ImageTk
import os
import sys
import cv2

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path: sys.path.insert(0, ROOT_DIR)

class VentanaAccionesBrazo(ctk.CTkToplevel):
    def __init__(self, master, estado="Home", color=None):
        super().__init__(master)
        self.title("Panel de Control Robótico - ESCOM")
        self.geometry("900x700")
        self.configure(fg_color="#F0F0F0")
        self.color = color
        self.ciclo = None
        self.camera_feed_running = False
        self._setup_ui()

    def _setup_ui(self):
        # Estado Principal
        self.lbl_titulo = ctk.CTkLabel(self, text="PREPARANDO SISTEMA...", font=("Arial", 28, "bold"), text_color="#007ACC")
        self.lbl_titulo.pack(pady=(30, 20))

        # --- MONITOR DE CÁMARA (640x360) ---
        self.label_feed_camara = ctk.CTkLabel(
            self, 
            text="[ Sincronizando Hardware... ]", 
            width=640, height=360, 
            corner_radius=10, 
            fg_color="black", text_color="gray",
            font=("Consolas", 16)
        )
        self.label_feed_camara.pack(pady=10)

        # Contenedor de Botón Inferior
        self.frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_btn.pack(pady=40)

        self.btn_regresar = ctk.CTkButton(
            self.frame_btn, text="Cancelar y Regresar a Inicio", 
            height=50, width=250, fg_color="#333333", hover_color="#1A1A1A", 
            font=("Arial", 14, "bold"), command=self.regresar_inicio
        )
        self.btn_regresar.pack()
        
        # --- INICIO AUTOMÁTICO ---
        # Esperamos 2 segundos exactos para iniciar el robot automáticamente.
        # Esto previene "crashes" al permitir que Tkinter dibuje la ventana primero.
        self.after(2000, self.iniciar_ciclo)

    def iniciar_ciclo(self):
        if self.ciclo and self.ciclo.is_alive(): return
        
        from modules.ciclo_robot import CicloRobot
        self.ciclo = CicloRobot(color_objetivo=self.color or "Azul", callback_estado=self.actualizar_estado)
        self.ciclo.start()
        
        self.camera_feed_running = True
        self._actualizar_live_feed()

    def actualizar_estado(self, estado):
        """Callback que recibe el string de estado desde el hilo del robot."""
        self.after(0, lambda: self._dibujar_estado(estado))

    def _dibujar_estado(self, estado):
        estado_limpio = estado.replace("_", " ")
        self.lbl_titulo.configure(text=f"ESTADO: {estado_limpio}")
        
        if "EMERGENCIA" in estado or "ERROR" in estado:
            self.lbl_titulo.configure(text_color="#CC0000")
        elif "FINALIZADO" in estado:
            self.lbl_titulo.configure(text_color="#008000")
            self.camera_feed_running = False # Detenemos la cámara al acabar el ciclo
        else:
            self.lbl_titulo.configure(text_color="#007ACC")

    def _actualizar_live_feed(self):
        """Bucle para pintar la imagen procesada con OpenCV en la GUI."""
        if not self.camera_feed_running or not hasattr(self, 'ciclo') or not self.ciclo.is_alive():
            return

        frame_cv2 = self.ciclo.get_latest_frame()

        if frame_cv2 is not None:
            # Convertimos BGR (OpenCV) a RGB (Tkinter/PIL)
            frame_rgb = cv2.cvtColor(frame_cv2, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            
            # Usamos CTkImage para evitar errores de HighDPI
            ctk_img = ctk.CTkImage(light_image=pil_image, size=(640, 360))
            
            self.label_feed_camara.configure(image=ctk_img, text="", fg_color="black")
            self.label_feed_camara.image = ctk_img 

        # Repetir a ~33 FPS
        self.after(30, self._actualizar_live_feed)

    def regresar_inicio(self):
        self.camera_feed_running = False
        if self.ciclo: self.ciclo.stop()
        
        try:
            self.master.deiconify()
        except:
            pass
        self.destroy()