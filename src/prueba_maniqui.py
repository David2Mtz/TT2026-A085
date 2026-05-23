# src/prueba_maniqui.py
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
from modules.detectorBoca import get_mouth_coordinates
from constants.posiciones import POSICIONES
from modules.mag_logger import log_mag_data, ask_user_success
from constants.config import BOCA_OFFSET_X, BOCA_OFFSET_Y, BOCA_COMP_FACTOR

# Cargar variables de entorno
load_dotenv()

# ===============================================================
# --- CONFIGURACIÓN PRINCIPAL ---
# ===============================================================
PUERTO_CAMARA = os.getenv('PUERTO_CAMARA', '/dev/ttyUSB1')
PUERTO_BRAZO = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')

class Estado:
    HOME = "HOME"
    OBSERVACION_MANIQUI = "OBSERVACION_MANIQUI"
    SEGUIMIENTO_BOCA = "SEGUIMIENTO_BOCA"
    ENTREGA = "ENTREGA"
    ESPERA_CONFIRMACION_ENTREGA = "ESPERA_CONFIRMACION_ENTREGA"
    EMERGENCIA = "EMERGENCIA"

def main():
    print("\n" + "="*60)
    print("--- DEMO PRUEBA MANIQUÍ (DEBUG ACTIVADO) ---")
    print("Objetivo: Testear aproximación a boca sin recolección previa.")
    print("="*60 + "\n")
    
    try:
        print(f"[DEBUG] Inicializando Cámara en {PUERTO_CAMARA}...")
        camara = CameraSerial(port=PUERTO_CAMARA, baud_rate=460800)
        print(f"[DEBUG] Inicializando Brazo en {PUERTO_BRAZO}...")
        brazo = ArmController(puerto=PUERTO_BRAZO, baudios=115200)
    except Exception as e:
        print(f"[ERROR CRÍTICO] No se pudo inicializar el hardware: {e}")
        return

    estado_actual = Estado.HOME
    macro_movimiento_hecho = False
    camara_activa = True # En este demo la dejamos activa para ver qué pasa
    
    # Parámetros de aproximación
    Z_LIMITE_ENTREGA = 160
    Z_UMBRAL_LOCKON = 200
    TOLERANCIA_CENTRADO = 14
    lockon_activado_boca = False
    
    # Variables de control
    contador_sondeo = 0
    last_move_time = 0
    INTERVALO_MOVIMIENTO = 0.2
    
    pastilla_en_transporte = False # Se activa al presionar 'P'

    print("\n[INSTRUCCIONES]")
    print(" 1. Coloca la pastilla MANUALMENTE en la pinza.")
    print(" 2. Presiona 'P' para CERRAR pinza e IR al maniquí.")
    print(" 3. 'Q' para salir, 'E' para forzar Emergencia.")
    print("-" * 30)

    try:
        while True:
            ahora = time.time()
            
            # --- POLLING DE TECLADO SIEMPRE ACTIVO ---
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): 
                print("[DEBUG] 'Q' presionada. Saliendo...")
                break
            if key == ord('e'): 
                print("[DEBUG] 'E' presionada. Emergencia forzada.")
                brazo.en_emergencia = True

            frame = camara.get_frame()
            
            if frame is None:
                # Mostrar un frame vacío si no hay cámara para mantener la ventana viva
                frame_placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame_placeholder, "ESPERANDO CAMARA...", (150, 240), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                cv2.imshow('Prueba Maniqui DEBUG', frame_placeholder)
                continue
            
            dist_actual = brazo.obtener_distancia()
            z_coord = dist_actual
            
            # --- DETECCIÓN DE EMERGENCIA ---
            if brazo.en_emergencia and estado_actual != Estado.EMERGENCIA:
                print("[SISTEMA] !!! EMERGENCIA DETECTADA !!!")
                estado_actual = Estado.EMERGENCIA
                macro_movimiento_hecho = False

            # =================================================
            # --- MÁQUINA DE ESTADOS (MODIFICADA) ---
            # =================================================

            if estado_actual == Estado.HOME:
                frame_vis = frame.copy()
                if not macro_movimiento_hecho:
                    print("[DEBUG] Moviendo a HOME...")
                    brazo.mover_a_estado("HOME", forzar=True, esperar=True)
                    macro_movimiento_hecho = True
                    pastilla_en_transporte = False
                
                cv2.putText(frame_vis, "HOME - Pon pastilla y pulsa 'P'", (10, 100), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                if key == ord('p'):
                    print("[DEBUG] 'P' presionada. Cerrando pinza...")
                    brazo.mover_tiempo([(12, 0)], forzar=True, esperar=True)
                    time.sleep(0.5)
                    m_init = brazo.mag1
                    brazo.evaluador_agarre.capturar_baseline(m_init[0], m_init[1], m_init[2])
                    pastilla_en_transporte = True
                    estado_actual = Estado.OBSERVACION_MANIQUI
                    macro_movimiento_hecho = False

            elif estado_actual == Estado.OBSERVACION_MANIQUI:
                if not macro_movimiento_hecho:
                    brazo.mover_a_estado("OBSERVACION_MANIQUI", forzar=True, esperar=True)
                    macro_movimiento_hecho = True
                    lockon_activado_boca = False
                
                # ROTAR FRAME 180 (Pin 8 a 180)
                frame_rotated = cv2.rotate(frame, cv2.ROTATE_180)
                frame_vis = frame_rotated.copy()
                cv_h, cv_w = frame_vis.shape[:2]
                cv2.drawMarker(frame_vis, (cv_w // 2, cv_h // 2), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)
                
                frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                if coords_boca:
                    print(f"[DEBUG] Boca detectada en {coords_boca}. Pasando a SEGUIMIENTO.")
                    estado_actual = Estado.SEGUIMIENTO_BOCA
                    macro_movimiento_hecho = False
                else:
                    cv2.putText(frame_vis, "Buscando boca (Rotado)...", (10, 60), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

            elif estado_actual == Estado.SEGUIMIENTO_BOCA:
                # --- MONITOREO DE COLISIÓN ---
                if brazo.evaluador_agarre.hubo_colision:
                    print(f"!!! COLISIÓN DETECTADA !!! Delta: {brazo.evaluador_agarre.ultimo_delta:.1f}")

                # ROTAR FRAME
                frame_rotated = frame
                frame_vis = frame_rotated.copy()
                cv_h, cv_w = frame_vis.shape[:2]
                cv2.drawMarker(frame_vis, (cv_w // 2, cv_h // 2), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)
                
                frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                
                if coords_boca:
                    contador_sondeo = 0
                    # Con rotación 180, los errores se calculan en el frame corregido
                    ex = coords_boca[0] - (cv_w // 2) + BOCA_OFFSET_X
                    ey_raw = coords_boca[1] - (cv_h // 2) + BOCA_OFFSET_Y
                    
                    dist_factor = max(0, Z_UMBRAL_LOCKON - z_coord)
                    offset_y_compensacion = int(dist_factor * BOCA_COMP_FACTOR) 
                    ey = ey_raw + offset_y_compensacion 

                    if int(time.time()*10) % 5 == 0:
                        print(f"[DEBUG] Seguimiento -> ErrX: {ex}, ErrY: {ey} (RawY: {ey_raw}), Z: {z_coord}mm")

                    targets = {}
                    
                    if not lockon_activado_boca:
                        # Centrado Horizontal (S0)
                        if abs(ex) > 8:
                            paso_x = 3 if abs(ex) > 60 else 1
                            targets[0] = brazo.estado_actual[0] + (paso_x if ex > 0 else -paso_x)
                        
                        # Centrado Vertical (S15 + S6)
                        if abs(ey) > 10:
                            targets[15] = brazo.estado_actual[15] + (1 if ey > 0 else -1)
                            if abs(ey) > 40:
                                targets[6] = brazo.estado_actual[6] + (1 if ey > 0 else -1)

                    # Acercamiento
                    if z_coord > Z_LIMITE_ENTREGA:
                        if brazo.estado_actual[1] > 70:
                            targets[1] = brazo.estado_actual[1] - 1
                        
                        if 6 not in targets and brazo.estado_actual[6] > 0:
                            targets[6] = brazo.estado_actual[6] - 1
                        
                        if z_coord <= Z_UMBRAL_LOCKON and abs(ex) <= TOLERANCIA_CENTRADO:
                            if not lockon_activado_boca:
                                print("[DEBUG] !!! LOCK-ON BOCA ACTIVADO !!!")
                                lockon_activado_boca = True
                    else:
                        print(f"[DEBUG] Meta de distancia alcanzada: {z_coord}mm")
                        estado_actual = Estado.ESPERA_CONFIRMACION_ENTREGA
                        macro_movimiento_hecho = False

                    if targets and (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                        brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                        last_move_time = ahora
                else:
                    contador_sondeo += 1
                    
                    # --- LÓGICA DE RECUPERACIÓN HACIA ARRIBA ---
                    if contador_sondeo < 30:
                        if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                            # Intentar subir la mirada (S15 disminuye para subir)
                            nuevo_s15 = max(0, brazo.estado_actual[15] - 2)
                            brazo.mover_tiempo([(15, nuevo_s15)], esperar=False)
                            last_move_time = ahora
                        cv2.putText(frame_vis, "RECUPERANDO (ARRIBA)...", (10, 60), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
                    elif contador_sondeo > 60:
                        print("[DEBUG] Boca no recuperada tras mirar arriba. Regresando a OBSERVACION.")
                        estado_actual = Estado.OBSERVACION_MANIQUI
                        macro_movimiento_hecho = False
                        contador_sondeo = 0

            elif estado_actual == Estado.ESPERA_CONFIRMACION_ENTREGA:
                frame_rotated = cv2.rotate(frame, cv2.ROTATE_180)
                frame_vis = frame_rotated.copy()
                cv2.putText(frame_vis, "ENTREGA LISTA - 'C' confirma, 'R' reintenta", (10, 90), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                if key == ord('c'):
                    print("[DEBUG] Entrega confirmada por usuario.")
                    estado_actual = Estado.ENTREGA
                    macro_movimiento_hecho = False
                elif key == ord('r'):
                    print("[DEBUG] Reintento solicitado.")
                    estado_actual = Estado.OBSERVACION_MANIQUI
                    macro_movimiento_hecho = False

            elif estado_actual == Estado.ENTREGA:
                print("[DEBUG] Soltando pastilla...")
                brazo.mover_tiempo([(12, 80)], esperar=True)
                time.sleep(1)
                estado_actual = Estado.HOME
                macro_movimiento_hecho = False

            elif estado_actual == Estado.EMERGENCIA:
                frame_vis = frame.copy()
                cv2.rectangle(frame_vis, (0, 0), (frame_vis.shape[1], frame_vis.shape[0]), (0, 0, 150), 10)
                cv2.putText(frame_vis, "!!! EMERGENCIA !!!", (50, 150), cv2.FONT_HERSHEY_DUPLEX, 1.2, (0, 0, 255), 3)
                if not brazo.en_emergencia:
                    estado_actual = Estado.HOME
                    macro_movimiento_hecho = False

            # --- INFO PANTALLA ---
            # Si frame_vis no existe (aunque siempre debería en este punto)
            try:
                cv2.putText(frame_vis, f"Estado: {estado_actual}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.putText(frame_vis, f"Z: {z_coord}mm", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow('Prueba Maniqui DEBUG', frame_vis)
            except: pass

    except KeyboardInterrupt: pass
    finally:
        try:
            brazo.mover_a_estado("HOME", forzar=True, esperar=True)
            brazo.cerrar()
            camara.liberar()
        except: pass
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
