import customtkinter as ctk
from tkinter import messagebox
import json
import os
import sys
from ayuda import VentanaAyuda

# Ruta al proyecto (raíz) y archivo de configuración dentro de `utils/`
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
RUTA_CONFIG = os.path.join(PROJECT_ROOT, 'utils', 'config_comprimidos.json')

class VentanaConfiguracion(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        
        self.title("Configuración de Comprimidos")
        self.geometry("1000x700")
        self.configure(fg_color="#D9D9D9")
        
        # Al cerrar esta ventana con la 'X', regresa al inicio
        self.protocol("WM_DELETE_WINDOW", self.regresar)

        # UI Elements
        ctk.CTkLabel(self, text="Configuracion de comprimidos", font=("Arial", 32, "bold"), text_color="black").pack(pady=(40, 10))
        ctk.CTkLabel(self, text="Ingrese el nombre del comprimido y seleccione\nsu respectivo color", font=("Arial", 18), text_color="black").pack(pady=(0, 40))

        self.frame_inputs = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_inputs.pack(pady=10)

        self.entries, self.combos = [], []
        for i in range(3):
            e = ctk.CTkEntry(self.frame_inputs, placeholder_text=f"Comprimido {i+1}", width=250, fg_color="white", text_color="black")
            e.grid(row=i, column=0, padx=10, pady=10)
            c = ctk.CTkOptionMenu(self.frame_inputs, values=["Seleccionar color", "Rojo", "Verde", "Azul"], fg_color="#333333")
            c.grid(row=i, column=1, padx=10, pady=10)
            self.entries.append(e); self.combos.append(c)

        self.cargar_configuracion()

        ctk.CTkButton(self, text="Guardar", fg_color="#333333", command=self.guardar_json).pack(pady=40)

        # Botones inferiores
        ctk.CTkButton(self, text="Regresar", command=self.regresar, fg_color="#333333").place(relx=0.05, rely=0.9, anchor="sw")
        ctk.CTkButton(self, text="?", width=40, corner_radius=20, command=self.abrir_ayuda, fg_color="#333333").place(relx=0.95, rely=0.9, anchor="se")

    def guardar_json(self):
        nombres = [e.get().strip() for e in self.entries]
        colores = [c.get() for c in self.combos]

        if any(n == "" for n in nombres) or any(c == "Seleccionar color" for c in colores):
            messagebox.showwarning("Campos incompletos", "Por favor, llene todos los campos.")
            return
        
        if len(set(colores)) < len(colores):
            messagebox.showerror("Error de color", "No se puede repetir el mismo color.")
            return

        data = {"mapeo_comprimidos": [{"id_interno": i+1, "nombre": n, "color_asignado": c} for i, (n, c) in enumerate(zip(nombres, colores))]}
        
        # --- USANDO LA RUTA ABSOLUTA AQUÍ ---
        with open(RUTA_CONFIG, "w") as f:
            json.dump(data, f, indent=4)
            
        messagebox.showinfo("Éxito", "Configuración guardada correctamente.")

    def abrir_ayuda(self):
        VentanaAyuda(self)

    def regresar(self):
        self.master.deiconify() # Muestra la VentanaInicio
        self.destroy()

    def cargar_configuracion(self):
        if not os.path.exists(RUTA_CONFIG):
            return

        try:
            with open(RUTA_CONFIG, "r", encoding="utf-8") as f:
                data = json.load(f)

            items = data.get("mapeo_comprimidos", [])
            for i, item in enumerate(items[:3]):
                nombre = item.get("nombre", "")
                color = item.get("color_asignado", "Seleccionar color")

                self.entries[i].delete(0, "end")
                self.entries[i].insert(0, nombre)
                if color in ["Rojo", "Verde", "Azul"]:
                    self.combos[i].set(color)
                else:
                    self.combos[i].set("Seleccionar color")

            for j in range(len(items), 3):
                self.entries[j].delete(0, "end")
                self.combos[j].set("Seleccionar color")

        except Exception as e:
            print(f"[Aviso] No se pudo cargar la configuración: {e}")
            return
