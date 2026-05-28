import customtkinter as ctk

class VentanaAyuda(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        
        self.title("Ayuda")
        self.geometry("600x450")
        self.configure(fg_color="#D9D9D9")
        
        # Propiedades de ventana modal
        self.after(10, self.lift)
        self.after(10, self.attributes, '-topmost', True)
        self.grab_set()

        self.frame_central = ctk.CTkFrame(self, fg_color="white", border_width=2, border_color="black")
        self.frame_central.pack(padx=40, pady=40, fill="both", expand=True)

        texto = (
            "1. Ingrese el nombre del comprimido.\n"
            "2. Asigne un color único (Rojo, Verde o Azul).\n"
            "3. Guarde para generar el archivo .json.\n"
            "4. Estos datos serán usados por el modelo de visión."
        )

        ctk.CTkLabel(self.frame_central, text=texto, font=("Arial", 16), text_color="black", justify="left").pack(padx=20, pady=20)
        ctk.CTkButton(self, text="Entendido", fg_color="#333333", command=self.destroy).pack(pady=(0, 20))