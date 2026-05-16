# src/calibrar_agarre.py
import sys
import os
import cv2
import time
import numpy as np
import dlib
from scipy.spatial import distance as dist
from imutils import face_utils
import imutils
from dotenv import load_dotenv

#------definir función para calcular el EAR-----------#
def calculate_EAR(eye):
    y1 = dist.euclidean(eye[1], eye[5])
    y2 = dist.euclidean(eye[2], eye[4])
    x1 = dist.euclidean(eye[0], eye[3])
    EAR = (y1 + y2) / x1
    return EAR

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
from modules.auto_exposure import AutoExposureControl
from modules.blinkDetector import BlinkDetector
from constants.posiciones import POSICIONES
from modules.mag_logger import log_mag_data, ask_user_success # LOGGER INTEGRADO

# Cargar variables de entorno
load_dotenv()

# ===============================================================
# --- CONFIGURACIÓN PRINCIPAL ---
# ===============================================================
PUERTO_CAMARA = os.getenv('PUERTO_CAMARA', '/dev/ttyUSB1')
PUERTO_BRAZO = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
COLOR_OBJETIVO = "Verde" 

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
    ESPERA_CONFIRMACION_ENTREGA = "ESPERA_CONFIRMACION_ENTREGA"
    EMERGENCIA = "EMERGENCIA"

def main():
    print("--- INICIANDO CALIBRACION DE AGARRE (COPIA DE CICLO COMPLETO) ---")
    
    try:
        camara = CameraSerial(port=PUERTO_CAMARA, baud_rate=460800)
        brazo = ArmController(puerto=PUERTO_BRAZO, baudios=115200)
    except Exception as e:
        print(f"[ERROR] No se pudo inicializar el hardware: {e}")
        return

    auto_exp = AutoExposureControl(target_brightness=130)

    # --- CONFIGURACIÓN DE PARPADEO (Cámara Laptop) ---
    detector_parpadeo = BlinkDetector(target_blinks=2, window_time=3.0)

    estado_actual = Estado.HOME
    macro_movimiento_hecho = False
    
    # --- CONFIGURACIÓN DE RECOLECCIÓN ---
    Z_UMBRAL_LOCKON = 120    
    Z_LIMITE_FINAL = 98   
    Z_LIMITE_ENTREGA = 250
    TOLERANCIA_CENTRADO = 12 
    lockon_activado = False  
    lockon_activado_boca = False
    
    # --- VARIABLES DE RECUPERACIÓN Y SONDEO ---
    contador_pastilla_perdida = 0
    recuperacion_pastilla_intentada = False
    contador_sondeo = 0
    contador_sondeo_color = 0
    fase_sondeo_color = "IZQUIERDA" 
    
    print("Sistema listo. Parpadea 2 veces para iniciar el ciclo.")

    try:
        while True:
            frame = camara.get_frame()
            if frame is None: continue

            dist_actual = brazo.obtener_distancia()
            z_coord = dist_actual
            frame_vis = frame.copy()
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break

            if brazo.en_emergencia and estado_actual != Estado.EMERGENCIA:
                print("[SISTEMA] Entrando en modo EMERGENCIA...")
                estado_actual = Estado.EMERGENCIA
                macro_movimiento_hecho = False

            if estado_actual in [Estado.OBSERVACION_MANIQUI, Estado.SEGUIMIENTO_BOCA, Estado.ESPERA_CONFIRMACION_ENTREGA]:
                if brazo.estado_pinza == "VACIA":
                    print("\n!!! OBJETO PERDIDO !!!")
                    estado_actual = Estado.HOME
                    macro_movimiento_hecho = False
            
            # =================================================
            # --- MÁQUINA DE ESTADOS ---
            # =================================================

            if estado_actual == Estado.HOME:
                lockon_activado = False
                if not macro_movimiento_hecho:
                    brazo.mover_a_estado("HOME", forzar=True)
                    detector_parpadeo.start_cam() 
                    macro_movimiento_hecho = True
                
                cv2.putText(frame_vis, "HOME - Parpadea 2 veces", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                if detector_parpadeo.check_for_trigger() or key == ord('n'):
                    print("[SISTEMA] Iniciando ciclo...")
                    detector_parpadeo.stop_cam() 
                    estado_actual = Estado.OBSERVACION
                    macro_movimiento_hecho = False

            elif estado_actual == Estado.OBSERVACION:
                if not macro_movimiento_hecho:
                    iniciar_deteccion_pastillas(camara) 
                    brazo.mover_a_estado("OBSERVACION")
                    time.sleep(2) 
                    macro_movimiento_hecho = True
                
                auto_exp.update(frame, camara)
                frame_vis, colores, info_colores = process_color_frame(frame_vis)
                
                if COLOR_OBJETIVO in colores:
                    print(f"[CONTROL] Color {COLOR_OBJETIVO} detectado.")
                    estado_actual = Estado.RECOLECCION
                    macro_movimiento_hecho = False
                else:
                    cv2.putText(frame_vis, f"Sondeando {COLOR_OBJETIVO} ({fase_sondeo_color})...", (10, 60), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    if fase_sondeo_color == "DERECHA":
                        if brazo.estado_actual[0] < 140:
                            brazo.mover_tiempo([(0, brazo.estado_actual[0] + 1)], esperar=False)
                        else: fase_sondeo_color = "IZQUIERDA"
                    elif fase_sondeo_color == "IZQUIERDA":
                        if brazo.estado_actual[0] > 40:
                            brazo.mover_tiempo([(0, brazo.estado_actual[0] - 1)], esperar=False)
                        else: fase_sondeo_color = "DERECHA"

            elif estado_actual == Estado.RECOLECCION:
                auto_exp.update(frame, camara)
                frame_vis, info = process_pastillas_frame(frame_vis, COLOR_OBJETIVO.lower())
                _, colores_backup, info_colores_backup = process_color_frame(frame.copy())
                
                if info or lockon_activado:
                    ex, ey, area = info if info else (0, 0, 0)
                    targets = {} 
                    
                    if not lockon_activado:
                        if abs(ex) > TOLERANCIA_CENTRADO:
                            paso_x = 1 if abs(ex) > 10 else 0.5
                            targets[0] = brazo.estado_actual[0] + (paso_x if ex > 0 else -paso_x)
                        
                        angulo_15 = brazo.estado_actual[15]
                        angulo_6 = brazo.estado_actual[6]
                        if abs(ey) > 10:
                            if ey > 0: 
                                if angulo_15 < 180: angulo_15 += 1
                                else: targets[6] = angulo_6 + 1
                            else:      
                                if angulo_15 > 10: angulo_15 -= 1
                                else: targets[6] = max(20, angulo_6 - 1)
                        if angulo_15 != brazo.estado_actual[15]: targets[15] = angulo_15

                    if z_coord > Z_UMBRAL_LOCKON:
                        if abs(ex) < 50 and abs(ey) < 50:
                            targets[1] = max(5, brazo.estado_actual[1] - 1)
                            if 6 not in targets: targets[6] = max(20, brazo.estado_actual[6] - 1)
                    
                    elif z_coord > Z_LIMITE_FINAL:
                        if abs(ex) <= TOLERANCIA_CENTRADO and abs(ey) <= TOLERANCIA_CENTRADO:
                            if not lockon_activado:
                                print("[CONTROL] Centrado OK. Lock-On ACTIVADO.")
                                lockon_activado = True

                        if lockon_activado:
                            targets[1] = max(5, brazo.estado_actual[1] - 1)
                            if brazo.estado_actual[15] > 20:
                                targets[15] = brazo.estado_actual[15] - 1 
                            cv2.putText(frame_vis, "LOCK-ON: BAJANDO...", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        else:
                            cv2.putText(frame_vis, "CENTRANDO FINAL...", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                    if z_coord <= Z_LIMITE_FINAL:
                        print(f"[ToF] POSICION DE AGARRE ALCANZADA.")
                        FINAL_CORRECTION_S0 = -2  
                        FINAL_CORRECTION_S15 = 0 
                        brazo.mover_tiempo([
                            (0, brazo.estado_actual[0] + FINAL_CORRECTION_S0),
                            (15, brazo.estado_actual[15] + FINAL_CORRECTION_S15)
                        ])
                        estado_actual = Estado.ESPERA_CONFIRMACION_AGARRE
                        finalizar_deteccion_pastillas(camara)
                        macro_movimiento_hecho = False

                    if targets:
                        brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                    contador_pastilla_perdida = 0
                    recuperacion_pastilla_intentada = False
                
                elif COLOR_OBJETIVO in colores_backup:
                    cx, cy = info_colores_backup[COLOR_OBJETIVO]
                    ex_b = cx - (frame_vis.shape[1] // 2)
                    ey_b = cy - (frame_vis.shape[0] // 2)
                    targets = {}
                    if abs(ex_b) > 20: targets[0] = brazo.estado_actual[0] + (1 if ex_b > 0 else -1)
                    if abs(ey_b) > 20: targets[15] = brazo.estado_actual[15] + (1 if ey_b > 0 else -1)
                    if targets: brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                
                else:
                    contador_pastilla_perdida += 1
                    if contador_pastilla_perdida == 30 and not recuperacion_pastilla_intentada:
                        nuevo_s15 = max(0, brazo.estado_actual[15] - 10)
                        brazo.mover_tiempo([(15, nuevo_s15)], esperar=True)
                        recuperacion_pastilla_intentada = True
                    elif contador_pastilla_perdida > 80:
                        estado_actual = Estado.OBSERVACION
                        macro_movimiento_hecho = False
                        contador_pastilla_perdida = 0

            elif estado_actual == Estado.ESPERA_CONFIRMACION_AGARRE:
                cv2.putText(frame_vis, "CALIBRAR: Presiona 'c' para LOGUEAR y cerrar", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                if key == ord('c'):
                    print("[CONTROL] Agarre de calibracion. Cerrando pinza...")
                    brazo.mover_tiempo([(12, 0)], esperar=True) # Cerrar a 0
                    print("[CALIBRACION] Esperando estabilizacion (1.5s)...")
                    time.sleep(1.5)
                    
                    # CAPTURAR Y LOGUEAR
                    m1 = brazo.mag1
                    resultado = ask_user_success()
                    
                    # Loguear siempre para calibración
                    etiqueta = "HOLDING_TRACK" if resultado == 'y' else "EMPTY_OR_FAIL"
                    log_mag_data(m1[0], m1[1], m1[2], etiqueta)
                    
                    if resultado == 'y':
                        print("[CONTROL] Levantando...")
                        brazo.mover_a_estado("PRE_RECOLECCION", esperar=True) 
                        estado_actual = Estado.OBSERVACION_MANIQUI
                    else:
                        print("[CONTROL] Fallo registrado. Reintentando...")
                        brazo.mover_tiempo([(12, 80)], esperar=True) # Abrir a 80
                        estado_actual = Estado.OBSERVACION
                    macro_movimiento_hecho = False

            elif estado_actual == Estado.OBSERVACION_MANIQUI:
                if not macro_movimiento_hecho:
                    iniciar_deteccion(camara)
                    brazo.mover_a_estado("OBSERVACION_MANIQUI", forzar=True, esperar=True)
                    macro_movimiento_hecho = True
                    lockon_activado_boca = False
                
                auto_exp.update(frame, camara)
                frame_rotated = cv2.rotate(frame, cv2.ROTATE_180)
                frame_vis = frame_rotated.copy()
                frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                if coords_boca:
                    estado_actual = Estado.SEGUIMIENTO_BOCA
                    macro_movimiento_hecho = False
                else:
                    cv2.putText(frame_vis, "Buscando boca...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

            elif estado_actual == Estado.SEGUIMIENTO_BOCA:
                auto_exp.update(frame, camara)
                frame_rotated = cv2.rotate(frame, cv2.ROTATE_180)
                frame_vis = frame_rotated.copy()
                frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                
                if coords_boca:
                    contador_sondeo = 0
                    ex = coords_boca[0] - (frame_vis.shape[1] // 2)
                    ey = coords_boca[1] - (frame_vis.shape[0] // 2)
                    targets = {} 
                    
                    if not lockon_activado_boca:
                        if abs(ex) > 8:
                            paso_x = 2 if abs(ex) > 60 else 1
                            targets[0] = brazo.estado_actual[0] + (paso_x if ex > 0 else -paso_x)
                        if abs(ey) > 10:
                            targets[15] = brazo.estado_actual[15] + (1 if ey > 0 else -1)
                            if abs(ey) > 30:
                                targets[6] = brazo.estado_actual[6] + (1 if ey > 0 else -1)

                    if z_coord > Z_LIMITE_ENTREGA:
                        if brazo.estado_actual[1] > 70: targets[1] = brazo.estado_actual[1] - 1
                        if 6 not in targets and brazo.estado_actual[6] > 0:
                            targets[6] = brazo.estado_actual[6] - 1
                        if z_coord <= Z_UMBRAL_LOCKON and abs(ex) <= TOLERANCIA_CENTRADO:
                            lockon_activado_boca = True

                    if z_coord <= Z_LIMITE_ENTREGA:
                        finalizar_deteccion(camara)
                        estado_actual = Estado.ESPERA_CONFIRMACION_ENTREGA
                        macro_movimiento_hecho = False

                    if targets: brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                else:
                    contador_sondeo += 1
                    if contador_sondeo < 100:
                        offset = 8 * np.sin(contador_sondeo * 0.15)
                        brazo.mover_tiempo([(0, POSICIONES["OBSERVACION_MANIQUI"][0][1] + offset)], esperar=False)
                    else:
                        estado_actual = Estado.OBSERVACION_MANIQUI
                        macro_movimiento_hecho = False

            elif estado_actual == Estado.ESPERA_CONFIRMACION_ENTREGA:
                frame_rotated = cv2.rotate(frame, cv2.ROTATE_180)
                frame_vis = frame_rotated.copy()
                cv2.putText(frame_vis, "ENTREGA LISTA - Confirma con 'c'", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                if key == ord('c'):
                    estado_actual = Estado.ENTREGA
                    macro_movimiento_hecho = False

            elif estado_actual == Estado.ENTREGA:
                brazo.mover_tiempo([(12, 80)]) # Abrir a 80
                time.sleep(1)
                estado_actual = Estado.HOME
                macro_movimiento_hecho = False

            elif estado_actual == Estado.EMERGENCIA:
                cv2.putText(frame_vis, "!!! PARO DE EMERGENCIA !!!", (50, 150), cv2.FONT_HERSHEY_DUPLEX, 1.2, (0, 0, 255), 3)
                if not brazo.en_emergencia:
                    estado_actual = Estado.HOME
                    macro_movimiento_hecho = False

            # UI Final
            m1 = brazo.mag1
            est_p = brazo.estado_pinza
            col_p = (0, 255, 0) if est_p == "CON_OBJETO" else (0, 255, 255) if est_p == "ABIERTA" else (0, 0, 255)
            texto_mag = f"M1: X:{m1[0]:.0f} Y:{m1[1]:.0f} Z:{m1[2]:.0f} | PINZA: {est_p}"
            cv2.putText(frame_vis, texto_mag, (10, frame_vis.shape[0] - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col_p, 1)
            cv2.putText(frame_vis, f"ESTADO: {estado_actual}", (10, frame_vis.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow('Calibracion Inteligente', frame_vis)

    except KeyboardInterrupt: pass
    finally:
        brazo.mover_a_estado("HOME", forzar=True, esperar=True)
        brazo.cerrar(); camara.liberar(); cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
