import customtkinter as ctk
import threading

class VentanaCarga(ctk.CTkToplevel):
    def __init__(self, master, mensaje="Cargando componentes...", tarea_hilo=None, callback_fin=None):
        super().__init__(master)
        self.title("Por favor espere")
        self.geometry("450x200")
        self.configure(fg_color="#D9D9D9")
        
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        self.label = ctk.CTkLabel(self, text=mensaje, font=("Arial", 16, "bold"), text_color="black")
        self.label.pack(pady=(40, 20))

        self.progreso = ctk.CTkProgressBar(self, width=300, mode="indeterminate", progress_color="#333333")
        self.progreso.pack(pady=10)
        self.progreso.start()

        # --- LÍNEAS CRÍTICAS ---
        # Fuerza a la ventana a dibujarse físicamente en el monitor ANTES de iniciar el hilo pesado
        self.update_idletasks()
        self.update() 

        if tarea_hilo:
            threading.Thread(target=self._ejecutar_tarea, args=(tarea_hilo, callback_fin), daemon=True).start()

    def _ejecutar_tarea(self, tarea, callback):
        try:
            resultado = tarea()
        except Exception as e:
            print(f"[Error Carga] Fallo en la subtarea: {e}")
            resultado = None

        self.after(0, lambda: self._finalizar(callback, resultado))

    def _finalizar(self, callback, resultado):
        self.progreso.stop()
        try:
            self.grab_release()
            self.withdraw() # Ocultar en lugar de destruir de golpe
            
            if callback:
                callback(resultado)
                
            self.after(150, self.destroy)
        except:
            pass