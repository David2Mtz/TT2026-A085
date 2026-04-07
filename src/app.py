# app/app.py
import sys
import os
import cv2

# Agregar la ruta raíz del proyecto para habilitar las importaciones
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.flujo_camara import CameraSerial
from modules.detectarColor import process_color_frame

def main():
    
    #TODO: PREGUNTAR PRIMERO SI YA SE ENCUENTRA EN LA POSICION DE OBSERVACION DE COLORES
    #TODO: Realizar diccionario de posiciones.
    posicion = True
    
    if (posicion):
        camara = CameraSerial(port='/dev/cu.usbserial-210', baud_rate=460800)

        try:
            while True:
                # 2. Pedir el frame
                frame = camara.get_frame()
                
                if frame is not None:
                    # 3. Pasar el frame por el módulo y recibir la tupla
                    frame_procesado, arreglo_colores = process_color_frame(frame)
                    
                    # Aquí tienes tu arreglo: 
                    # arreglo_colores[0] -> Izquierda
                    # arreglo_colores[1] -> Centro
                    # arreglo_colores[2] -> Derecha
                    
                    # Imprimimos el resultado en consola para verificar
                    print(f"Posiciones de colores: {arreglo_colores}")
                    
                    # 4. Mostrar el resultado
                    cv2.imshow('PROYECTO VISION - Modulo Color', frame_procesado)
                else:
                    print("Esperando frame válido...")
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        except KeyboardInterrupt:
            print("\nEjecución detenida.")
        finally:
            camara.liberar()
            cv2.destroyAllWindows()

if __name__ == '__main__':
    main()