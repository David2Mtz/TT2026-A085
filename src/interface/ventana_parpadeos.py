import customtkinter as ctk
from PIL import Image, ImageTk
import os
import sys
import cv2
import time

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from configuracion import VentanaConfiguracion
from modules.blinkDetector import BlinkDetector

PARPADEOS_REQUERIDOS = 2

class VentanaParpadeos:
    def __new__(cls, master=None, color=""):
        if master is not None:
            instance = object.__new__(VentanaParpadeos_Toplevel)
            instance.__init__(master, color)
            return instance
        else:
            instance = object.__new__(VentanaParpadeos_CTk)
            instance.__init__(color)
            return instance


class VentanaParpadeos_CTk(ctk.CTk):
    def __init__(self, color=""):
        super().__init__()
        self.color = color
        self.title("Sistema de Prototipo de Brazo Robótico - ESCOM")
        self.geometry("1000x700")
        self.configure(fg_color="#D9D9D9")

        self._setup_ui()
        self.actualizar_color_detectado(color)

        # Retrasamos la carga pesada para que la UI se alcance a dibujar primero
        self.camera_label.configure(text="Cargando modelo facial (dlib)...\nPor favor espere.")
        self.after(500, self._inicializar_detector)

    def _inicializar_detector(self):
        try:
            self.blink_detector = BlinkDetector(target_blinks=PARPADEOS_REQUERIDOS, window_time=3.0)
            ok = self.blink_detector.start_cam()
            if ok:
                self._camera_running = True
                self.after(50, self._update_camera_frame)
            else:
                print("[ventana_parpadeos] No se pudo abrir la cámara del BlinkDetector.")
                self._camera_running = False
                self.camera_label.configure(text="Error: No se pudo abrir la cámara local.")
        except Exception as e:
            print(f"[ventana_parpadeos] Error inicializando BlinkDetector: {e}")
            self._camera_running = False
            self.camera_label.configure(text="Error al cargar componentes de visión.")

    def _setup_ui(self):
        self.label_titulo = ctk.CTkLabel(self, text="Color detectado en el experimento:",
                                         font=ctk.CTkFont(family="Arial", size=28, weight="bold"),
                                         text_color="black")
        self.label_titulo.pack(pady=(20, 10))

        self.label_subtitulo = ctk.CTkLabel(self, text="Si el color detectado es correcto, parpadea 2 veces frente a la cámara",
                                            font=ctk.CTkFont(family="Arial", size=14), text_color="black")
        self.label_subtitulo.pack(pady=(0, 10))

        # Área de cámara
        self.camera_frame = ctk.CTkFrame(self, width=640, height=360)
        self.camera_frame.pack(pady=(10, 10))
        self.camera_label = ctk.CTkLabel(self.camera_frame, text="Inicializando interfaz...", width=640, height=360)
        self.camera_label.pack()

        self.blink_status = ctk.CTkLabel(self, text=f"Blinks detectados: 0/{PARPADEOS_REQUERIDOS}",
                                         font=ctk.CTkFont(size=16), text_color="black")
        self.blink_status.pack(pady=(10, 10))

        # Botones
        self.frame_boton = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_boton.pack(side="bottom", anchor="se", padx=20, pady=20)
        self.btn_regresar = ctk.CTkButton(self.frame_boton, text="Regresar a Inicio", command=self.regresar_inicio,
                                          fg_color="#333333", width=150, height=40)
        self.btn_regresar.pack()

    def _update_camera_frame(self):
        if not getattr(self, '_camera_running', False):
            return
        try:
            cam = getattr(self.blink_detector, 'cam', None)
            if cam is None:
                self.after(100, self._update_camera_frame)
                return

            ret, frame = cam.read()
            if not ret:
                self.after(50, self._update_camera_frame)
                return

            trigger, annotated = self.blink_detector.process_frame(frame)
            current_blinks = len(self.blink_detector.blink_timestamps)
            self.blink_status.configure(text=f"Blinks detectados: {current_blinks}/{PARPADEOS_REQUERIDOS}")

            annotated_rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(annotated_rgb)
            pil = pil.resize((640, 360))
            photo = ImageTk.PhotoImage(pil)

            self.camera_label.configure(image=photo, text="")
            self.camera_label.image = photo

            if trigger:
                self.abrir_ventana_acciones(color=self.color)
                return

        except Exception as e:
            print(f"[ventana_parpadeos] Error en _update_camera_frame: {e}")

        self.after(50, self._update_camera_frame)

    def stop_blink_monitoring(self):
        self._camera_running = False
        try:
            if getattr(self, 'blink_detector', None):
                self.blink_detector.stop_cam()
        except Exception:
            pass

    def abrir_ventana_acciones(self, color=None):
        self.stop_blink_monitoring()
        from ventana_carga import VentanaCarga
        
        def tarea_cargar_acciones():
            # Pausa visual para la transición a VentanaAcciones
            time.sleep(1.5)
            from ventana_acciones import VentanaAccionesBrazo
            return VentanaAccionesBrazo

        def al_terminar_de_cargar(clase_acciones):
            parent = self.master if getattr(self, 'master', None) else self
            self.withdraw()
            if clase_acciones:
                self.after(50, lambda: clase_acciones(parent, estado="Home", color=(color or self.color)))

        VentanaCarga(self, mensaje="Sincronizando controladores seriales ESP32...", 
                     tarea_hilo=tarea_cargar_acciones, callback_fin=al_terminar_de_cargar)

    def regresar_inicio(self):
        self.stop_blink_monitoring()
        from ventana_inicio import VentanaInicio
        self.withdraw()
        VentanaInicio(self)

    def actualizar_color_detectado(self, color):
        self.label_titulo.configure(text=f"Color detectado en el experimento: {color}")


class VentanaParpadeos_Toplevel(ctk.CTkToplevel):
    def __init__(self, master, color=""):
        super().__init__(master)
        self.color = color
        self.title("Sistema de Prototipo de Brazo Robótico - ESCOM")
        self.geometry("1000x700")
        self.configure(fg_color="#D9D9D9")

        self._setup_ui()
        self.actualizar_color_detectado(color)

        self.camera_label.configure(text="Cargando modelo facial (dlib)...\nPor favor espere.")
        self.after(500, self._inicializar_detector)

    def _inicializar_detector(self):
        try:
            self.blink_detector = BlinkDetector(target_blinks=PARPADEOS_REQUERIDOS, window_time=3.0)
            ok = self.blink_detector.start_cam()
            if ok:
                self._camera_running = True
                self.after(50, self._update_camera_frame)
            else:
                self._camera_running = False
                self.camera_label.configure(text="Error: No se pudo iniciar la cámara.")
        except Exception as e:
            print(f"[ventana_parpadeos] Error inicializando BlinkDetector: {e}")
            self._camera_running = False
            self.camera_label.configure(text="Error al cargar componentes de visión.")

    def _setup_ui(self):
        self.label_titulo = ctk.CTkLabel(self, text="Color detectado en el experimento:",
                                         font=ctk.CTkFont(family="Arial", size=28, weight="bold"),
                                         text_color="black")
        self.label_titulo.pack(pady=(20, 10))

        self.label_subtitulo = ctk.CTkLabel(self, text="Si el color detectado es correcto, parpadea 2 veces frente a la cámara",
                                            font=ctk.CTkFont(family="Arial", size=14), text_color="black")
        self.label_subtitulo.pack(pady=(0, 10))

        self.camera_frame = ctk.CTkFrame(self, width=640, height=360)
        self.camera_frame.pack(pady=(10, 10))
        self.camera_label = ctk.CTkLabel(self.camera_frame, text="Inicializando interfaz...", width=640, height=360)
        self.camera_label.pack()

        self.blink_status = ctk.CTkLabel(self, text=f"Blinks detectados: 0/{PARPADEOS_REQUERIDOS}",
                                         font=ctk.CTkFont(size=16), text_color="black")
        self.blink_status.pack(pady=(10, 10))

        self.frame_boton = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_boton.pack(side="bottom", anchor="se", padx=20, pady=20)
        self.btn_regresar = ctk.CTkButton(self.frame_boton, text="Regresar a Inicio", command=self.regresar_inicio,
                                          fg_color="#333333", width=150, height=40)
        self.btn_regresar.pack()

    def _update_camera_frame(self):
        if not getattr(self, '_camera_running', False):
            return
        try:
            cam = getattr(self.blink_detector, 'cam', None)
            if cam is None:
                self.after(100, self._update_camera_frame)
                return

            ret, frame = cam.read()
            if not ret:
                self.after(50, self._update_camera_frame)
                return

            trigger, annotated = self.blink_detector.process_frame(frame)
            current_blinks = len(self.blink_detector.blink_timestamps)
            self.blink_status.configure(text=f"Blinks detectados: {current_blinks}/{PARPADEOS_REQUERIDOS}")

            annotated_rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(annotated_rgb)
            pil = pil.resize((640, 360))
            photo = ImageTk.PhotoImage(pil)

            self.camera_label.configure(image=photo, text="")
            self.camera_label.image = photo

            if trigger:
                self.abrir_ventana_acciones(color=self.color)
                return

        except Exception as e:
            print(f"[ventana_parpadeos] Error en _update_camera_frame: {e}")

        self.after(50, self._update_camera_frame)

    def stop_blink_monitoring(self):
        self._camera_running = False
        try:
            if getattr(self, 'blink_detector', None):
                self.blink_detector.stop_cam()
        except Exception:
            pass

    def abrir_ventana_acciones(self, color=None):
        self.stop_blink_monitoring()
        from ventana_carga import VentanaCarga
        
        def tarea_cargar_acciones():
            time.sleep(1.5)
            from ventana_acciones import VentanaAccionesBrazo
            return VentanaAccionesBrazo

        def al_terminar_de_cargar(clase_acciones):
            parent = self.master if getattr(self, 'master', None) else self
            self.withdraw()
            if clase_acciones:
                self.after(50, lambda: clase_acciones(parent, estado="Home", color=(color or self.color)))

        VentanaCarga(self, mensaje="Sincronizando controladores seriales ESP32...", 
                     tarea_hilo=tarea_cargar_acciones, callback_fin=al_terminar_de_cargar)

    def regresar_inicio(self):
        self.stop_blink_monitoring()
        from ventana_inicio import VentanaInicio
        self.withdraw()
        VentanaInicio(self)

    def actualizar_color_detectado(self, color):
        self.label_titulo.configure(text=f"Color detectado en el experimento: {color}")