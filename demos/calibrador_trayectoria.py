# demos/calibrador_trayectoria.py
import sys
import os
import time
import csv
import datetime
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.arm_controller import ArmController
from constants.posiciones import POSICIONES

load_dotenv()

def main():
    print("=== CALIBRADOR DE TRAYECTORIA MAGNÉTICA (PINZA VACÍA) ===")
    print("Este script moverá el brazo por las posiciones clave del proyecto")
    print("con la pinza CERRADA (vacía) para mapear el campo magnético.")
    print("¡ASEGÚRATE DE QUE NO HAYA NADA EN LA PINZA!\n")
    
    puerto = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
    brazo = ArmController(puerto=puerto, baudios=115200)
    
    archivo_csv = "log_trayectoria_vacia.csv"
    file_exists = os.path.isfile(archivo_csv)
    
    # Secuencia de la trayectoria real del proyecto
    secuencia = [
        "HOME",
        "OBSERVACION",
        "PRE_RECOLECCION",
        "OBSERVACION_MANIQUI",
        "ENTREGA"
    ]

    try:
        with open(archivo_csv, mode='a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                # Cabeceras incluyendo la magnitud (Norm) y los ángulos relevantes
                writer.writerow(["Timestamp", "Estado_Posicion", "Mag_X", "Mag_Y", "Mag_Z", "Norma", "Servo_Base", "Servo_Muneca"])

            # 1. Asegurar pinza cerrada al máximo (VACÍA)
            print("[INFO] Cerrando pinza al máximo (0 grados)...")
            brazo.mover_tiempo([(12, 0)], forzar=True, esperar=True)
            time.sleep(2)

            # 2. Recorrer la secuencia
            for posicion in secuencia:
                print(f"\n[MOVIMIENTO] Yendo a: {posicion}...")
                brazo.mover_a_estado(posicion, esperar=True)
                
                # Pausa para estabilización mecánica y magnética
                print("   Esperando estabilización (3s)...")
                time.sleep(3)
                
                # Tomar un promedio de 5 lecturas para mayor precisión
                x_sum, y_sum, z_sum = 0, 0, 0
                for _ in range(5):
                    m = brazo.mag1
                    x_sum += m[0]
                    y_sum += m[1]
                    z_sum += m[2]
                    time.sleep(0.1)
                
                mag_x = x_sum / 5
                mag_y = y_sum / 5
                mag_z = z_sum / 5
                norma = (mag_x**2 + mag_y**2 + mag_z**2)**0.5
                
                s_base = brazo.estado_actual[0]
                s_muneca = brazo.estado_actual[15]
                
                # Guardar en CSV
                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                writer.writerow([timestamp, posicion, round(mag_x, 1), round(mag_y, 1), round(mag_z, 1), round(norma, 1), s_base, s_muneca])
                
                print(f"   [LOG] {posicion} -> Norm: {norma:.1f} | X: {mag_x:.1f}, Y: {mag_y:.1f}, Z: {mag_z:.1f}")

        print(f"\n[ÉXITO] Mapeo completado. Datos guardados en '{archivo_csv}'.")

    except KeyboardInterrupt:
        print("\nCalibración cancelada.")
    finally:
        print("Regresando a HOME y liberando...")
        brazo.mover_a_estado("HOME", forzar=True, esperar=True)
        brazo.cerrar()

if __name__ == "__main__":
    main()
