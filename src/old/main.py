# TT2026-A085/main_autonomo.py
import sys
import os
import cv2
import time

from dotenv import load_dotenv

# --- Agregamos la ruta raíz del proyecto para poder importar los módulos ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.flujo_camara import CameraSerial
from modules.arm_controller import ArmController
from modules.pastillas_detector import process_pastillas_frame
from modules.mouth_detector import get_mouth_coordinates

# Cargar variables de entorno
load_dotenv()

# ===============================================================
# --- CONFIGURACIÓN PRINCIPAL ---
# ===============================================================
# ¡¡¡IMPORTANTE!!! Modifica estos puertos según tu sistema operativo
PUERTO_CAMARA = os.getenv('PUERTO_CAMARA', '/dev/ttyUSB1') # Reemplazar por tu puerto de ESP32-CAM
PUERTO_BRAZO = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')           # Reemplazar por tu puerto de ESP32 del brazo

# --- PARÁMETROS DE COMPORTAMIENTO ---
COLOR_BASE_PASTILLERO = "azul" # Color de la base donde están las pastillas ('rojo', 'verde' o 'azul')
TIEMPO_MAX_INACTIVIDAD = 300 # Segundos (5 minutos) para regresar a HOME

# ===============================================================
# --- MÁQUINA DE ESTADOS ---
# ===============================================================
class Estado:
    INICIO = "INICIO"
    ESPERA_COMANDO = "ESPERA_COMANDO"
    MOVER_A_OBSERVACION = "MOVER_A_OBSERVACION"
    CENTRADO_PASTILLA = "CENTRADO_PASTILLA"
    RECOLECCION = "RECOLECCION"
    MOVER_A_ENTREGA = "MOVER_A_ENTREGA"
    CENTRADO_BOCA = "CENTRADO_BOCA"
    ENTREGA_FINAL = "ENTREGA_FINAL"
    REGRESO_A_HOME = "REGRESO_A_HOME"

def main():
    print("--- INICIANDO SISTEMA DE CONTROL AUTÓNOMO ---")
    
    # --- Inicialización de Hardware ---
    # Nota: Asegúrate de que los dispositivos estén conectados antes de ejecutar
    try:
        camara = CameraSerial(port=PUERTO_CAMARA, baud_rate=460800)
        brazo = ArmController(puerto=PUERTO_BRAZO, baudios=115200)
    except Exception as e:
        print(f"[ERROR CRÍTICO] No se pudo inicializar el hardware: {e}")
        print("Verifica las conexiones y los puertos en el script.")
        return

    # --- Variables de Estado y Control ---
    estado_actual = Estado.INICIO
    tiempo_ultima_actividad = time.time()
    
    print(f"\nPresiona 'n' para iniciar el ciclo.")
    print("Presiona 'q' para salir.")

    try:
        while True:
            # --- Gestión de Inactividad ---
            if time.time() - tiempo_ultima_actividad > TIEMPO_MAX_INACTIVIDAD:
                if estado_actual not in [Estado.INICIO, Estado.ESPERA_COMANDO, Estado.REGRESO_A_HOME]:
                    print("\n[INFO] Tiempo de inactividad superado. Regresando a HOME.")
                    estado_actual = Estado.REGRESO_A_HOME

            # --- Captura de Video y Teclado ---
            frame = camara.get_frame()
            if frame is None:
                print("Esperando frame de la cámara...")
                time.sleep(0.5)
                continue

            # Copia del frame para dibujar sobre él sin afectar el original
            frame_visualizacion = frame.copy()
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("Saliendo del programa...")
                break
            
            # =================================================
            # --- LÓGICA DE LA MÁQUINA DE ESTADOS ---
            # =================================================

            if estado_actual == Estado.INICIO:
                print(f"\n[ESTADO: {estado_actual}] - Moviendo a posición HOME.")
                brazo.mover_a_estado("HOME")
                estado_actual = Estado.ESPERA_COMANDO
                tiempo_ultima_actividad = time.time()

            elif estado_actual == Estado.ESPERA_COMANDO:
                cv2.putText(frame_visualizacion, "Presiona 'n' para empezar", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                if key == ord('n'):
                    estado_actual = Estado.MOVER_A_OBSERVACION
                    print(f"\n[ESTADO: {estado_actual}] - Iniciando ciclo de recolección.")

            elif estado_actual == Estado.MOVER_A_OBSERVACION:
                print(f"[ESTADO: {estado_actual}] - Yendo a la zona de observación de pastillas.")
                brazo.mover_a_estado("OBSERVACION")
                estado_actual = Estado.CENTRADO_PASTILLA
                print(f"[ESTADO: {estado_actual}] - Buscando y centrando pastilla...")
                time.sleep(1) # Pequeña pausa para estabilizar la imagen

            elif estado_actual == Estado.CENTRADO_PASTILLA:
                frame_visualizacion, error = process_pastillas_frame(frame_visualizacion, COLOR_BASE_PASTILLERO)
                
                if error:
                    # El servocontrol visual se ejecuta aquí
                    centrado = brazo.centrar_ibvs(error[0], error[1])
                    if centrado:
                        print("[INFO] ¡Objetivo centrado! Listo para recoger.")
                        estado_actual = Estado.RECOLECCION
                        tiempo_ultima_actividad = time.time()
                else:
                    cv2.putText(frame_visualizacion, "Buscando pastillero...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            elif estado_actual == Estado.RECOLECCION:
                print(f"\n[ESTADO: {estado_actual}] - Ejecutando secuencia de agarre.")
                # Secuencia de movimientos finos para el agarre
                brazo.mover_tiempo([(1, 100), (6, 80)]) # Bajar pinza (Codo Pin 6)
                time.sleep(0.5)
                brazo.mover_tiempo([(12, 0)]) # Cerrar Pinza (Pin 12)
                time.sleep(0.5)
                brazo.mover_a_estado("PRE_RECOLECCION") # Subir un poco antes de girar
                
                estado_actual = Estado.MOVER_A_ENTREGA
                tiempo_ultima_actividad = time.time()

            elif estado_actual == Estado.MOVER_A_ENTREGA:
                print(f"\n[ESTADO: {estado_actual}] - Yendo a la zona de entrega.")
                brazo.mover_a_estado("ENTREGA")
                estado_actual = Estado.CENTRADO_BOCA
                print(f"[ESTADO: {estado_actual}] - Buscando boca del maniquí...")
                time.sleep(1)

            elif estado_actual == Estado.CENTRADO_BOCA:
                frame_visualizacion, coords_boca = get_mouth_coordinates(frame_visualizacion)
                
                if coords_boca:
                    # Reutilizamos el IBVS, pero con las coordenadas de la boca
                    error_x = coords_boca[0] - (frame_visualizacion.shape[1] // 2)
                    error_y = coords_boca[1] - (frame_visualizacion.shape[0] // 2)
                    
                    centrado = brazo.centrar_ibvs(error_x, error_y)
                    if centrado:
                        print("[INFO] ¡Boca centrada! Listo para entregar.")
                        estado_actual = Estado.ENTREGA_FINAL
                        tiempo_ultima_actividad = time.time()
                else:
                    cv2.putText(frame_visualizacion, "Buscando boca...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            elif estado_actual == Estado.ENTREGA_FINAL:
                print(f"\n[ESTADO: {estado_actual}] - Soltando pastilla.")
                brazo.mover_tiempo([(12, 80)]) # Abrir pinza (Pin 12)
                time.sleep(1)
                estado_actual = Estado.REGRESO_A_HOME
                print("[INFO] Ciclo completado.")

            elif estado_actual == Estado.REGRESO_A_HOME:
                print(f"\n[ESTADO: {estado_actual}] - Regresando a posición de descanso.")
                brazo.mover_a_estado("HOME")
                estado_actual = Estado.ESPERA_COMANDO
                tiempo_ultima_actividad = time.time()
                print("\n--- Sistema en espera. Presiona 'n' para un nuevo ciclo. ---")

            # --- Mostrar siempre la ventana de visualización ---
            cv2.putText(frame_visualizacion, f"ESTADO: {estado_actual}", (10, frame_visualizacion.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow('Control Hibrido Autonomo - TT2026-A085', frame_visualizacion)

    except KeyboardInterrupt:
        print("\nEjecución detenida por el usuario.")
    finally:
        # --- Secuencia de apagado seguro ---
        print("\n[INFO] Finalizando programa. Regresando brazo a HOME...")
        if 'brazo' in locals():
            brazo.mover_a_estado("HOME")
            brazo.cerrar()
        if 'camara' in locals():
            camara.liberar()
        cv2.destroyAllWindows()
        print("[INFO] Recursos liberados correctamente.")

if __name__ == '__main__':
    main()
