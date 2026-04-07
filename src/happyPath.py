# app/app.py
import sys
import os
import cv2
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.flujo_camara import CameraSerial
from modules.detectarColor import process_color_frame
from modules.mouth_detector import get_mouth_coordinates

# --- MOCKS DEL ROBOT (Reemplazar con tu lógica de comunicación real) ---
def enviar_coordenadas_brazo(x, y, z=None):
    print(f"[ROBOT] Moviendo a coordenadas X:{x}, Y:{y} " + (f"Z:{z}" if z else ""))
    time.sleep(2) # Simulamos el tiempo que tarda el brazo en llegar

def enviar_comando_pinza(accion):
    print(f"[ROBOT] Pinza: {accion.upper()}")
    time.sleep(1)

def simular_lectura_distancia_z(distancia_actual):
    # Simula que el brazo va bajando poco a poco
    return max(10.0, distancia_actual - 5.5) 
# -----------------------------------------------------------------------

def main():
    # Estados posibles: OBSERVACION, RECOLECCION, ENTREGA, HOME
    estado_actual = "OBSERVACION"
    color_objetivo = "Rojo" # Hardcodeado según regla de negocio
    
    # Diccionario de posiciones harcodeadas del espacio de trabajo
    # TODO: Reemplazar con las coordenadas reales de tu robot (X, Y)
    posiciones_espacio = {
        0: {"x": 150, "y": 200}, # Izquierda
        1: {"x": 300, "y": 200}, # Centro
        2: {"x": 450, "y": 200}  # Derecha
    }

    camara = CameraSerial(port='/dev/cu.usbserial-210', baud_rate=460800)
    distancia_z_simulada = 40.0 # Iniciamos a 40cm de la mesa

    try:
        while True:
            frame = camara.get_frame()
            if frame is None:
                continue

            # ==========================================
            # PASO 1: POSICIÓN DE OBSERVACIÓN (COLORES)
            # ==========================================
            if estado_actual == "OBSERVACION":
                frame_procesado, arreglo_colores = process_color_frame(frame)
                cv2.imshow('PROYECTO VISION - Happy Path', frame_procesado)

                if color_objetivo in arreglo_colores:
                    indice_posicion = arreglo_colores.index(color_objetivo)
                    coordenadas_reales = posiciones_espacio.get(indice_posicion)
                    
                    print(f"\n--- [VISION] {color_objetivo} detectado en posición {indice_posicion} ---")
                    
                    # Mandamos coordenadas y cambiamos de estado
                    enviar_coordenadas_brazo(coordenadas_reales["x"], coordenadas_reales["y"])
                    estado_actual = "RECOLECCION"
            
            # ==========================================
            # PASO 2: POSICIÓN DE RECOLECCIÓN (BAJADA)
            # ==========================================
            elif estado_actual == "RECOLECCION":
                # Mostramos la cámara normal mientras baja
                cv2.imshow('PROYECTO VISION - Happy Path', frame)
                
                # Leemos la distancia (aquí simulo que un sensor te da el valor)
                distancia_z_simulada = simular_lectura_distancia_z(distancia_z_simulada)
                print(f"[SENSOR] Distancia a la mesa: {distancia_z_simulada} cm")

                if distancia_z_simulada <= 10.0:
                    print("\n--- [CONTROL] Distancia óptima alcanzada (10cm). Iniciando extracción ---")
                    enviar_comando_pinza("cerrar")
                    
                    # Simulamos que sube y va a la zona del maniquí
                    enviar_coordenadas_brazo(X_ENTREGA, Y_ENTREGA) # TODO: Tus coords de seguridad
                    estado_actual = "ENTREGA"
                else:
                    # Pequeño delay simulando la bajada constante
                    time.sleep(0.5)

            # ==========================================
            # PASO 3: POSICIÓN DE ENTREGA (LANDMARKS BOCA)
            # ==========================================
            elif estado_actual == "ENTREGA":
                frame_procesado, coords_boca = get_mouth_coordinates(frame)
                cv2.imshow('PROYECTO VISION - Happy Path', frame_procesado)

                if coords_boca is not None:
                    print(f"\n--- [VISION] Boca detectada en X:{coords_boca[0]}, Y:{coords_boca[1]} ---")
                    
                    # TODO: Mapear coordenadas de pixeles a cinemática del robot
                    enviar_coordenadas_brazo(coords_boca[0], coords_boca[1])
                    enviar_comando_pinza("abrir")
                    
                    print("\n--- [EXITO] Pastilla entregada. Regresando a HOME ---")
                    estado_actual = "HOME"

            # ==========================================
            # PASO 4: REGRESO A HOME
            # ==========================================
            elif estado_actual == "HOME":
                cv2.imshow('PROYECTO VISION - Happy Path', frame)
                # TODO: Coordenadas de HOME
                enviar_coordenadas_brazo(0, 0, 0)
                
                # Reiniciamos el ciclo para la siguiente prueba
                distancia_z_simulada = 40.0
                estado_actual = "OBSERVACION"
                print("\n================ LISTO PARA NUEVA ORDEN ================\n")
                time.sleep(3) # Pausa antes de reiniciar el ciclo visual

            # --- Salida de emergencia ---
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("\nEjecución detenida por el usuario.")
    finally:
        camara.liberar()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()