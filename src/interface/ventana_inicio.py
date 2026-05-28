import customtkinter as ctk
from PIL import Image
import os
import sys

# `ROOT_DIR` apunta a `src/` para permitir imports locales (configuracion, experimento...)
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# `PROJECT_ROOT` apunta a la raíz del repositorio (dos niveles arriba desde este archivo)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from configuracion import VentanaConfiguracion

class VentanaInicio:
    def __new__(cls, master=None):
        if master is not None:
            # Si hay master, crear como Toplevel
            instance = object.__new__(VentanaInicio_Toplevel)
            instance.__init__(master)
            return instance
        else:
            # Sin master, crear como CTk principal
            instance = object.__new__(VentanaInicio_CTk)
            instance.__init__()
            return instance


class VentanaInicio_CTk(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Sistema de Prototipo de Brazo Robótico - ESCOM")
        self.geometry("1000x700")
        self.configure(fg_color="#D9D9D9")
        self._setup_ui()

    def _setup_ui(self):
        # Título
        self.label_titulo = ctk.CTkLabel(
            self, 
            text="Sistema del prototipo de brazo robotico para la\nentrega de comprimidos",
            font=ctk.CTkFont(family="Arial", size=36, weight="bold"),
            text_color="black"
        )
        self.label_titulo.pack(pady=(80, 50))

        # Contenedor de Botones
        self.frame_botones = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_botones.pack(pady=20)

        self.btn_config = ctk.CTkButton(
            self.frame_botones, text="Configuración de comprimidos",
            font=ctk.CTkFont(size=14), fg_color="#333333", width=220, height=45,
            command=self.abrir_configuracion
        )
        self.btn_config.grid(row=0, column=0, padx=80)

        self.btn_exp = ctk.CTkButton(
            self.frame_botones, text="Realizar experimento",
            font=ctk.CTkFont(size=14), fg_color="#333333", width=220, height=45,
            command=self.abrir_experimento
        )
        self.btn_exp.grid(row=0, column=1, padx=80)

        # Imagen
        try:
            img_path = os.path.join(PROJECT_ROOT, "assets", "cerebro_color.png")
            cerebro_img = ctk.CTkImage(light_image=Image.open(img_path), size=(350, 350))
            self.label_imagen = ctk.CTkLabel(self, image=cerebro_img, text="")
            self.label_imagen.pack(pady=(40, 0))
        except:
            self.label_no_img = ctk.CTkLabel(self, text="[ Imagen del Cerebro ]", width=350, height=350, fg_color="white", text_color="gray")
            self.label_no_img.pack(pady=(40, 0))

    def abrir_configuracion(self):
        self.withdraw()
        VentanaConfiguracion(self)

    def abrir_experimento(self):
        from ventana_carga import VentanaCarga
        
        def tarea_cargar_experimento():
            # Forzamos los imports pesados aquí adentro para que ocurran en el hilo de carga
            from experimento import InterfazP300
            return InterfazP300

        def al_terminar_de_cargar(clase_interfaz):
            if clase_interfaz:
                self.withdraw()
                clase_interfaz(self)

        # Lanzamos la pantalla de carga sin ocultar inicio todavía
        VentanaCarga(self, mensaje="Inicializando paradigma BCI y LSL...", 
                     tarea_hilo=tarea_cargar_experimento, callback_fin=al_terminar_de_cargar)


class VentanaInicio_Toplevel(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Sistema de Prototipo de Brazo Robótico - ESCOM")
        self.geometry("1000x700")
        self.configure(fg_color="#D9D9D9")
        self._setup_ui()

    def _setup_ui(self):
        self.label_titulo = ctk.CTkLabel(
            self, 
            text="Sistema del prototipo de brazo robotico para la\nentrega de comprimidos",
            font=ctk.CTkFont(family="Arial", size=36, weight="bold"),
            text_color="black"
        )
        self.label_titulo.pack(pady=(80, 50))

        # Contenedor de Botones
        self.frame_botones = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_botones.pack(pady=20)

        self.btn_config = ctk.CTkButton(
            self.frame_botones, text="Configuración de comprimidos",
            font=ctk.CTkFont(size=14), fg_color="#333333", width=220, height=45,
            command=self.abrir_configuracion
        )
        self.btn_config.grid(row=0, column=0, padx=80)

        self.btn_exp = ctk.CTkButton(
            self.frame_botones, text="Realizar experimento",
            font=ctk.CTkFont(size=14), fg_color="#333333", width=220, height=45,
            command=self.abrir_experimento
        )
        self.btn_exp.grid(row=0, column=1, padx=80)

        # Imagen
        try:
            img_path = os.path.join(PROJECT_ROOT, "assets", "cerebro_color.png")
            cerebro_img = ctk.CTkImage(light_image=Image.open(img_path), size=(350, 350))
            self.label_imagen = ctk.CTkLabel(self, image=cerebro_img, text="")
            self.label_imagen.pack(pady=(40, 0))
        except:
            self.label_no_img = ctk.CTkLabel(self, text="[ Imagen del Cerebro ]", width=350, height=350, fg_color="white", text_color="gray")
            self.label_no_img.pack(pady=(40, 0))

    def abrir_configuracion(self):
        self.withdraw()
        VentanaConfiguracion(self)

    def abrir_experimento(self):
        from ventana_carga import VentanaCarga
        
        def tarea_cargar_experimento():
            # Forzamos los imports pesados aquí adentro para que ocurran en el hilo de carga
            from experimento import InterfazP300
            return InterfazP300

        def al_terminar_de_cargar(clase_interfaz):
            if clase_interfaz:
                self.withdraw()
                clase_interfaz(self)

        # Lanzamos la pantalla de carga sin ocultar inicio todavía
        VentanaCarga(self, mensaje="Inicializando paradigma BCI y LSL...", 
                     tarea_hilo=tarea_cargar_experimento, callback_fin=al_terminar_de_cargar)

if __name__ == "__main__":
    app = VentanaInicio()
    app.mainloop()