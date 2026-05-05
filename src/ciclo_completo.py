# src/ciclo_completo.py
import sys
import os
import cv2
import time
import numpy as np
from dotenv import load_dotenv

# Corrección de ruta para importar módulos desde la raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.flujo_camara import CameraSerial
from modules.arm_controller import ArmController
from modules.pastillas_detector import (
    process_pastillas_frame,
    iniciar_deteccion as iniciar_deteccion_pastillas,
    finalizar_deteccion as finalizar_deteccion_pastillas
)
from modules.detectarColor import process_color_frame
from modules.detectorBoca import get_mouth_coordinates, iniciar_deteccion, finalizar_deteccion

# Cargar variables de entorno
load_dotenv()

# ===============================================================
# --- CONFIGURACIÓN PRINCIPAL ---
# ===============================================================
PUERTO_CAMARA = os.getenv('PUERTO_CAMARA', '/dev/ttyUSB1')
PUERTO_BRAZO = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
COLOR_OBJETIVO = "Azul" 

from constants.config import OFFSET_X, OFFSET_Y

class Estado:
    HOME = "HOME"
    OBSERVACION = "OBSERVACION"
    SEGUIMIENTO_PASTILLA = "SEGUIMIENTO_PASTILLA"
    RECOLECCION = "RECOLECCION"
    ESPERA_CONFIRMACION_AGARRE = "ESPERA_CONFIRMACION_AGARRE"
    OBSERVACION_MANIQUI = "OBSERVACION_MANIQUI"
    SEGUIMIENTO_BOCA = "SEGUIMIENTO_BOCA"
    ENTREGA = "ENTREGA"
    EMERGENCIA = "EMERGENCIA"

def main():
    print("--- INICIANDO CICLO COMPLETO (PASTILLAS) ---")
    
    try:
        camara = CameraSerial(port=PUERTO_CAMARA, baud_rate=460800)
        brazo = ArmController(puerto=PUERTO_BRAZO, baudios=115200)
    except Exception as e:
        print(f"[ERROR] No se pudo inicializar el hardware: {e}")
        return

    estado_actual = Estado.HOME
    macro_movimiento_hecho = False
    
    # --- CONFIGURACIÓN DE RECOLECCIÓN ---
    Z_UMBRAL_LOCKON = 115    
    Z_LIMITE_FINAL = 75      
    TOLERANCIA_CENTRADO = 12 
    lockon_activado = False  
    lockon_activado_boca = False
    
    print("Presiona 'n' para iniciar el ciclo, 'q' para salir.")

    try:
        while True:
            frame = camara.get_frame()
            if frame is None: continue

            frame_vis = frame.copy()
            
            # --- ROTACIÓN DINÁMICA DE IMAGEN REMOVIDA ---
            # Ya no invertimos la imagen aunque el brazo rote para la entrega

            dist_actual = brazo.obtener_distancia() 
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break

            # --- DETECCIÓN DE EMERGENCIA ---
            if brazo.en_emergencia and estado_actual != Estado.EMERGENCIA:
                print("[SISTEMA] Entrando en modo EMERGENCIA...")
                estado_anterior = estado_actual # Guardar para posible reanudación
                estado_actual = Estado.EMERGENCIA
                macro_movimiento_hecho = False

            # Dibujar info
            z_coord = dist_actual
            color_z = (0, 255, 0) if z_coord <= Z_LIMITE_FINAL else (0, 255, 255)
            cv2.putText(frame_vis, f"COORD Z (ToF): {z_coord}mm", (10, 30), cv2.FONT_HERSHEY_DUPLEX, 0.8, color_z, 2)
            
            # =================================================
            # --- MÁQUINA DE ESTADOS ---
            # =================================================

            if estado_actual == Estado.HOME:
                lockon_activado = False
                if not macro_movimiento_hecho:
                    brazo.mover_a_estado("HOME", forzar=True)
                    macro_movimiento_hecho = True
                
                cv2.putText(frame_vis, "HOME - Esperando 'n'", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                if key == ord('n'):
                    estado_actual = Estado.OBSERVACION
                    macro_movimiento_hecho = False

            elif estado_actual == Estado.OBSERVACION:
                if not macro_movimiento_hecho:
                    iniciar_deteccion_pastillas(camara) # Luz 48
                    brazo.mover_a_estado("OBSERVACION")
                    time.sleep(2) 
                    macro_movimiento_hecho = True
                
                frame_vis, colores = process_color_frame(frame_vis)
                if COLOR_OBJETIVO in colores:
                    estado_actual = Estado.RECOLECCION
                    macro_movimiento_hecho = False

            elif estado_actual == Estado.RECOLECCION:
                frame_vis, info = process_pastillas_frame(frame_vis, COLOR_OBJETIVO.lower(), dist_actual=dist_actual)
                
                if info or lockon_activado:
                    ex, ey, area = info if info else (0, 0, 0)
                    targets = {} 
                    
                    if not lockon_activado:
                        # Centrado Horizontal (S0)
                        if abs(ex) > 8:
                            paso_x = 2 if abs(ex) > 60 else 1
                            targets[0] = brazo.estado_actual[0] + (paso_x if ex > 0 else -paso_x)
                        
                        # Centrado Vertical Inteligente (S15 + S6)
                        angulo_15 = brazo.estado_actual[15]
                        angulo_6 = brazo.estado_actual[6]
                        if abs(ey) > 10:
                            if ey > 0: # Abajo -> Extender
                                if angulo_15 < 180: angulo_15 += 1
                                else: targets[6] = angulo_6 + 1
                            else:      # Arriba -> Retraer
                                if angulo_15 > 10: angulo_15 -= 1
                                else: targets[6] = max(20, angulo_6 - 1)
                        if angulo_15 != brazo.estado_actual[15]: targets[15] = angulo_15

                    # Lógica de Descenso
                    if z_coord > Z_UMBRAL_LOCKON:
                        # Freno si la pastilla está en los bordes
                        if abs(ex) < 50 and abs(ey) < 50:
                            targets[1] = max(5, brazo.estado_actual[1] - 1)
                            if 6 not in targets: targets[6] = max(20, brazo.estado_actual[6] - 1)
                    
                    elif z_coord > Z_LIMITE_FINAL:
                        if abs(ex) <= TOLERANCIA_CENTRADO and abs(ey) <= TOLERANCIA_CENTRADO:
                            if not lockon_activado:
                                print("[CONTROL] Centrado OK. Lock-On ACTIVADO.")
                                lockon_activado = True

                        if lockon_activado:
                            # Fase 3: Bajada vertical (Solo S1) con compensación de inclinación
                            targets[1] = max(5, brazo.estado_actual[1] - 1)

                            # COMPENSACIÓN DE INCLINACIÓN REFORZADA:
                            # A medida que bajamos S1, subimos S15 para que la pinza no se incline hacia adelante
                            if brazo.estado_actual[15] > 20:
                                targets[15] = brazo.estado_actual[15] - 1 # Ajuste de 1:1 con S1

                            cv2.putText(frame_vis, "LOCK-ON: BAJANDO...", (10, 80), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        else:
                            cv2.putText(frame_vis, "CENTRANDO FINAL...", (10, 80), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                    # 3. Condición de Parada Final (75mm)
                    if z_coord <= Z_LIMITE_FINAL:
                        print(f"[ToF] POSICION DE AGARRE ALCANZADA ({z_coord}mm).")

                        # --- AJUSTE FINO CIEGO (Compensación Final de Parallax) ---
                        # Si a 75mm la pinza queda un poco desfasada, ajustamos aquí:
                        FINAL_CORRECTION_S0 = -4  # Grados extra para centrar X
                        FINAL_CORRECTION_S15 = -5 # Grados extra para centrar Y (hacia arriba)

                        print(f"[INFO] Aplicando corrección final: S0+{FINAL_CORRECTION_S0}, S15+{FINAL_CORRECTION_S15}")
                        brazo.mover_tiempo([
                            (0, brazo.estado_actual[0] + FINAL_CORRECTION_S0),
                            (15, brazo.estado_actual[15] + FINAL_CORRECTION_S15)
                        ])

                        estado_actual = Estado.ESPERA_CONFIRMACION_AGARRE
                        finalizar_deteccion_pastillas(camara)
                        macro_movimiento_hecho = False

                    
                    if targets:
                        brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)

            elif estado_actual == Estado.ESPERA_CONFIRMACION_AGARRE:
                cv2.putText(frame_vis, "CONFIRMAR - Presiona 'c'", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                if key == ord('c'):
                    print("[CONTROL] Agarre confirmado. Levantando...")
                    brazo.mover_tiempo([(12, 10)], esperar=True) 
                    time.sleep(0.5)
                    brazo.mover_a_estado("PRE_RECOLECCION", esperar=True) 
                    estado_actual = Estado.OBSERVACION_MANIQUI
                    macro_movimiento_hecho = False

            elif estado_actual == Estado.OBSERVACION_MANIQUI:
                if not macro_movimiento_hecho:
                    print("[CONTROL] Yendo a posición de entrega (Maniquí)...")
                    iniciar_deteccion(camara)
                    camara.set_led_brightness(255) 
                    # Forzar movimiento completo con espera
                    brazo.mover_a_estado("OBSERVACION_MANIQUI", forzar=True, esperar=True)
                    time.sleep(0.5)
                    macro_movimiento_hecho = True
                    lockon_activado_boca = False
                
                # Rotar frame para el maniquí
                frame_rotated = cv2.rotate(frame, cv2.ROTATE_180)
                frame_vis = frame_rotated.copy()
                
                frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                if coords_boca:
                    estado_actual = Estado.SEGUIMIENTO_BOCA
                    macro_movimiento_hecho = False
                else:
                    cv2.putText(frame_vis, "Buscando boca (Frame Rotado)...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

            elif estado_actual == Estado.SEGUIMIENTO_BOCA:
                # Rotar frame para el maniquí
                frame_rotated = cv2.rotate(frame, cv2.ROTATE_180)
                frame_vis = frame_rotated.copy()
                
                frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                
                if coords_boca or lockon_activado_boca:
                    ex, ey = 0, 0
                    if coords_boca:
                        # Error con frame rotado
                        ex_raw = coords_boca[0] - (frame_vis.shape[1] // 2)
                        ey_raw = coords_boca[1] - (frame_vis.shape[0] // 2)
                        
                        # Invertir ejes por rotación de 180 grados
                        ex = -ex_raw
                        ey = -ey_raw
                    
                    targets = {} 
                    
                    if not lockon_activado_boca:
                        # Centrado Horizontal (S0)
                        if abs(ex) > 8:
                            paso_x = 2 if abs(ex) > 60 else 1
                            targets[0] = brazo.estado_actual[0] + (paso_x if ex > 0 else -paso_x)
                        
                        # Centrado Vertical Inteligente (S15 + S6)
                        angulo_15 = brazo.estado_actual[15]
                        angulo_6 = brazo.estado_actual[6]
                        if abs(ey) > 10:
                            if ey > 0: # Abajo -> Extender
                                if angulo_15 < 180: angulo_15 += 1
                                else: targets[6] = angulo_6 + 1
                            else:      # Arriba -> Retraer
                                if angulo_15 > 10: angulo_15 -= 1
                                else: targets[6] = max(20, angulo_6 - 1)
                        if angulo_15 != brazo.estado_actual[15]: targets[15] = angulo_15

                    # Lógica de Descenso (Acercamiento al maniquí)
                    if z_coord > Z_UMBRAL_LOCKON:
                        # Freno si la boca está en los bordes
                        if abs(ex) < 50 and abs(ey) < 50:
                            targets[1] = max(5, brazo.estado_actual[1] - 1)
                            if 6 not in targets: targets[6] = max(20, brazo.estado_actual[6] - 1)
                    
                    elif z_coord > Z_LIMITE_FINAL:
                        if abs(ex) <= TOLERANCIA_CENTRADO and abs(ey) <= TOLERANCIA_CENTRADO:
                            if not lockon_activado_boca:
                                print("[CONTROL] Centrado Boca OK. Lock-On ACTIVADO.")
                                lockon_activado_boca = True

                        if lockon_activado_boca:
                            # Fase 3: Bajada vertical (Solo S1) con compensación de inclinación
                            targets[1] = max(5, brazo.estado_actual[1] - 1)

                            # COMPENSACIÓN DE INCLINACIÓN REFORZADA:
                            if brazo.estado_actual[15] > 20:
                                targets[15] = brazo.estado_actual[15] - 1 

                            cv2.putText(frame_vis, "LOCK-ON BOCA: ACERCANDO...", (10, 80), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        else:
                            cv2.putText(frame_vis, "CENTRANDO BOCA FINAL...", (10, 80), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                    # 3. Condición de Parada Final
                    if z_coord <= Z_LIMITE_FINAL:
                        print(f"[ToF] POSICION DE ENTREGA ALCANZADA ({z_coord}mm).")
                        finalizar_deteccion(camara)
                        estado_actual = Estado.ENTREGA
                        macro_movimiento_hecho = False

                    if targets:
                        brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                else:
                    estado_actual = Estado.OBSERVACION_MANIQUI
                    macro_movimiento_hecho = False

            elif estado_actual == Estado.ENTREGA:
                brazo.mover_tiempo([(12, 90)])
                time.sleep(1)
                estado_actual = Estado.HOME
                macro_movimiento_hecho = False

            elif estado_actual == Estado.EMERGENCIA:
                cv2.rectangle(frame_vis, (0, 0), (frame_vis.shape[1], frame_vis.shape[0]), (0, 0, 150), 10)
                cv2.putText(frame_vis, "!!! PARO DE EMERGENCIA !!!", (50, 150), cv2.FONT_HERSHEY_DUPLEX, 1.2, (0, 0, 255), 3)
                cv2.putText(frame_vis, "LIBERA EL BOTON PARA REINICIAR", (80, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                if not brazo.en_emergencia:
                    print("[SISTEMA] Emergencia liberada. Regresando a HOME.")
                    estado_actual = Estado.HOME
                    macro_movimiento_hecho = False

            cv2.putText(frame_vis, f"ESTADO: {estado_actual}", (10, frame_vis.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow('Ciclo Autonomo Inteligente', frame_vis)

    except KeyboardInterrupt:
        print("\nEjecución cancelada.")
    finally:
        print("\nApagando...")
        try:
            if camara: camara.set_led_brightness(0)
            # Agregamos esperar=True para que el movimiento suave se complete antes de cerrar
            brazo.mover_a_estado("HOME", forzar=True, esperar=True)
            brazo.cerrar()
            camara.liberar()
        except: pass
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
