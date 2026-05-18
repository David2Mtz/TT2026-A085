# modules/mag_logger.py
import csv
import os
import datetime

# Definir la ruta absoluta basada en la ubicación de este archivo
# para que siempre se guarde en la carpeta raíz del proyecto TT2026-A085
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE_NAME = os.path.join(BASE_DIR, "log_calibracion_dinamica.csv")

def log_mag_data(x, y, z, success):
    """
    Guarda los datos del magnetómetro y el resultado del agarre en un archivo CSV.
    """
    file_exists = os.path.isfile(FILE_NAME)
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        with open(FILE_NAME, mode='a', newline='') as f:
            writer = csv.writer(f)
            
            # Escribir cabecera si el archivo es nuevo
            if not file_exists:
                writer.writerow(["Timestamp", "Mag_X", "Mag_Y", "Mag_Z", "Agarrado"])
            
            writer.writerow([timestamp, x, y, z, success])
        
        print(f"[LOGGER] Datos guardados exitosamente en: {FILE_NAME}")
    except Exception as e:
        print(f"[ERROR LOGGER] No se pudo escribir en el archivo: {e}")

def ask_user_success():
    """
    Pregunta al usuario si el agarre fue exitoso por consola.
    Retorna 'y' o 'n'.
    """
    while True:
        # Usamos input() estándar. Nota: En un entorno con OpenCV, 
        # esto detendrá la ejecución hasta que se presione Enter en la terminal.
        val = input("\n>>> ¿Se agarro la pastilla correctamente? (y/n): ").lower().strip()
        if val in ['y', 'n']:
            return val
        print("Entrada no valida. Por favor presiona 'y' o 'n'.")
