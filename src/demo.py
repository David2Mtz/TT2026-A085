# app/happyPath.py
import os
import cv2
import time
from dotenv import load_dotenv
from utils.flujo_camara import CameraSerial
from modules.arm_controller import ArmController

# Cargar variables de entorno
load_dotenv()

def main():
    # Inicialización
    puerto_camara = os.getenv('PUERTO_CAMARA', '/dev/cu.usbserial-210')
    puerto_brazo = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
    
    camara = CameraSerial(port=puerto_camara, baud_rate=460800)
    brazo = ArmController(puerto=puerto_brazo, baudios=9600)
    
    # El bucle SIEMPRE inicia en HOME
    estado_actual = "INICIO_HOME"
    color_base = "azul"

    try:
        while True:
            frame = camara.get_frame()
            if frame is None: continue

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break
            
            # --- MÁQUINA DE ESTADOS ---
            
            if estado_actual == "INICIO_HOME":
                brazo.mover_a_estado("HOME")
                print("Esperando comando 'n' para iniciar ciclo...")
                estado_actual = "ESPERA_INICIO"

            elif estado_actual == "ESPERA_INICIO":
                cv2.imshow('CONTROL HIBRIDO', frame)
                if key == ord('n'): estado_actual = "OBSERVACION"

            elif estado_actual == "OBSERVACION":
                frame_v, colores = process_color_frame(frame)
                cv2.imshow('CONTROL HIBRIDO', frame_v)
                if key == ord('n'):
                    brazo.mover_a_estado("OBSERVACION")
                    estado_actual = "CENTRADO_VISUAL"

            elif estado_actual == "CENTRADO_VISUAL":
                frame_v, error = process_pastillas_frame(frame, color_base)
                cv2.imshow('CONTROL HIBRIDO', frame_v)
                
                if error:
                    centrado = brazo.centrar_ibvs(error[0], error[1])
                    if centrado:
                        print("¡Objetivo centrado!")
                        estado_actual = "RECOLECCION"

            elif estado_actual == "RECOLECCION":
                # Secuencia de agarre
                brazo.mover_tiempo([(1, 100), (3, 80)], "Bajando pinza")
                brazo.mover_tiempo([(6, 110)], "Cerrando Pinza") # Agarre fuerte
                brazo.mover_a_estado("HOME") # Subir antes de girar
                estado_actual = "ENTREGA"

            elif estado_actual == "ENTREGA":
                brazo.mover_a_estado("ENTREGA")
                cv2.imshow('CONTROL HIBRIDO', frame)
                if key == ord('n'):
                    brazo.mover_tiempo([(6, 0)], "Soltando pastilla")
                    print("Ciclo completado. Regresando a Home...")
                    estado_actual = "INICIO_HOME" # El bucle se cierra aquí

    finally:
        camara.liberar()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()