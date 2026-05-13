# src/test_magnetometro.py
import sys
import os
import time
from dotenv import load_dotenv

# Configurar rutas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.arm_controller import ArmController
from modules.mag_logger import log_mag_data

load_dotenv()

def main():
    print("=== HERRAMIENTA DE CALIBRACIÓN DE MAGNETÓMETRO ===")
    puerto = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
    
    try:
        brazo = ArmController(puerto=puerto, baudios=115200)
    except Exception as e:
        print(f"Error: {e}")
        return

    try:
        while True:
            print("\nOpciones:")
            print("1. Abrir Pinza (80) y registrar baseline ABIERTO")
            print("2. Cerrar Pinza VACÍA (0) y registrar baseline VACÍO")
            print("3. Cerrar Pinza CON OBJETO (0) y registrar CON OBJETO")
            print("q. Salir")
            
            opcion = input("Selecciona una opción: ").lower()
            
            if opcion == '1':
                print("Abriendo pinza...")
                brazo.mover_tiempo([(12, 80)], esperar=True)
                time.sleep(1.5)
                m = brazo.mag1
                log_mag_data(m[0], m[1], m[2], "ABIERTO")
                print(f"Registrado ABIERTO: {m}")
                
            elif opcion == '2':
                print("Cerrando pinza (vacía)...")
                brazo.mover_tiempo([(12, 0)], esperar=True)
                time.sleep(1.5)
                m = brazo.mag1
                log_mag_data(m[0], m[1], m[2], "VACIO_CERRADO")
                print(f"Registrado VACÍO: {m}")
                
            elif opcion == '3':
                print("\n*** POR FAVOR COLOCA LA PASTILLA EN LA PINZA ***")
                input("Presiona ENTER cuando estés listo para cerrar...")
                brazo.mover_tiempo([(12, 0)], esperar=True)
                time.sleep(1.5)
                m = brazo.mag1
                log_mag_data(m[0], m[1], m[2], "CON_OBJETO")
                print(f"Registrado CON OBJETO: {m}")
                
            elif opcion == 'q':
                break
            else:
                print("Opción no válida.")

    finally:
        print("Regresando a HOME y cerrando...")
        brazo.mover_a_estado("HOME")
        brazo.cerrar()

if __name__ == "__main__":
    main()
