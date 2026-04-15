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
    # time.sleep(2) # Comentado para agilizar la prueba manual

def enviar_comando_pinza(accion):
    print(f"[ROBOT] Pinza: {accion.upper()}")
    # time.sleep(1)
# -----------------------------------------------------------------------

def main():
    # Estados posibles: READY, OBSERVACION, RECOLECCION, ENTREGA, HOME
    estado_actual = "OBSERVACION"
    color_objetivo = "Rojo" # Hardcodeado según regla de negocio
    
    # Diccionario de posiciones harcodeadas del espacio de trabajo
    # TODO: Reemplazar con las coordenadas reales de tu robot (X, Y)
    posiciones_espacio = {
        0: {"x": 150, "y": 200}, # Izquierda
        1: {"x": 300, "y": 200}, # Centro
        2: {"x": 450, "y": 200}  # Derecha
    }

    # Coordenadas dummy de entrega para evitar errores
    X_ENTREGA = 500
    Y_ENTREGA = 500

    camara = CameraSerial(port='/dev/cu.usbserial-210', baud_rate=460800)

    print("\n================ INICIANDO HAPPY PATH MANUAL ================")
    print("Presiona la tecla 'n' o 'N' en la ventana de video para avanzar al siguiente estado.")
    print("Presiona 'q' para salir del programa.")
    print("=============================================================\n")
    print(f"ESTADO ACTUAL: {estado_actual} - Buscando color {color_objetivo}")

    try:
        while True:
            frame = camara.get_frame()
            if frame is None:
                continue

            # --- Captura de teclado centralizada ---
            key = cv2.waitKey(1) & 0xFF
            avanzar_estado = False
            
            if key == ord('q'):
                break
            elif key == ord('n') or key == ord('N'):
                avanzar_estado = True

            # ==========================================
            # PASO 1: POSICIÓN DE OBSERVACIÓN (COLORES)
            # ==========================================
            if estado_actual == "OBSERVACION":
                frame_procesado, arreglo_colores = process_color_frame(frame)
                cv2.imshow('PROYECTO VISION - Happy Path', frame_procesado)

                if avanzar_estado:
                    # Imprimir el arreglo final exacto en consola
                    print("\n" + "="*50)
                    print(f"[ESTADO FINAL DE COLORES]")
                    print(f"Izquierda (0): {arreglo_colores[0]}")
                    print(f"Centro    (1): {arreglo_colores[1]}")
                    print(f"Derecha   (2): {arreglo_colores[2]}")
                    print("="*50)

                    if color_objetivo in arreglo_colores:
                        indice_posicion = arreglo_colores.index(color_objetivo)
                        coordenadas_reales = posiciones_espacio.get(indice_posicion)
                        
                        print(f"\n--- [VISION] {color_objetivo} confirmado en posición {indice_posicion} ---")
                        enviar_coordenadas_brazo(coordenadas_reales["x"], coordenadas_reales["y"])
                        estado_actual = "RECOLECCION"
                        print(f"\n---> AVANZANDO A ESTADO: {estado_actual}")
                    else:
                        print(f"\n--- [ALERTA] No se detectó el color {color_objetivo}. No se puede avanzar. Intenta de nuevo. ---")
            
            # ==========================================
            # PASO 2: POSICIÓN DE RECOLECCIÓN (BAJADA)
            # ==========================================
            elif estado_actual == "RECOLECCION":
                cv2.imshow('PROYECTO VISION - Happy Path', frame)

                if avanzar_estado:
                    print("\n--- [CONTROL] Simulación de llegada a 10cm de la mesa ---")
                    print("Iniciando extracción...")
                    enviar_comando_pinza("cerrar")
                    enviar_coordenadas_brazo(X_ENTREGA, Y_ENTREGA)
                    estado_actual = "ENTREGA"
                    print(f"\n---> AVANZANDO A ESTADO: {estado_actual}")

            # ==========================================
            # PASO 3: POSICIÓN DE ENTREGA (LANDMARKS BOCA)
            # ==========================================
            elif estado_actual == "ENTREGA":
                frame_procesado, coords_boca = get_mouth_coordinates(frame)
                cv2.imshow('PROYECTO VISION - Happy Path', frame_procesado)

                if avanzar_estado:
                    if coords_boca is not None:
                        print(f"\n--- [VISION] Boca detectada y confirmada en X:{coords_boca[0]}, Y:{coords_boca[1]} ---")
                        enviar_coordenadas_brazo(coords_boca[0], coords_boca[1])
                    else:
                        print("\n--- [ALERTA] Avanzando sin detectar boca (A ciegas) ---")
                    
                    enviar_comando_pinza("abrir")
                    print("--- [EXITO] Pastilla entregada ---")
                    estado_actual = "HOME"
                    print(f"\n---> AVANZANDO A ESTADO: {estado_actual}")

            # ==========================================
            # PASO 4: REGRESO A HOME
            # ==========================================
            elif estado_actual == "HOME":
                cv2.imshow('PROYECTO VISION - Happy Path', frame)
                
                if avanzar_estado:
                    print("\n--- [CONTROL] Regresando a posición inicial ---")
                    enviar_coordenadas_brazo(0, 0, 0)
                    estado_actual = "OBSERVACION"
                    print("\n================ LISTO PARA NUEVA ORDEN ================")
                    print(f"ESTADO ACTUAL: {estado_actual} - Buscando color {color_objetivo}")

    except KeyboardInterrupt:
        print("\nEjecución detenida por el usuario.")
    finally:
        camara.liberar()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()