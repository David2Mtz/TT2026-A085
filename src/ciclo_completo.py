# src/ciclo_completo.py
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

# Corrección de ruta para importar módulos desde la raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.flujo_camara import CameraSerial
from modules.arm_controller import ArmController
from modules.pastillas_detector import process_pastillas_frame
from modules.detectarColor import process_color_frame
from modules.detectorBoca import get_mouth_coordinates
from modules.auto_exposure import AutoExposureControl
from modules.blinkDetector import BlinkDetector
from constants.posiciones import POSICIONES
from modules.mag_logger import log_mag_data, ask_user_success # Importar logger
from constants.config import BOCA_OFFSET_X, BOCA_OFFSET_Y, BOCA_COMP_FACTOR

# Cargar variables de entorno
load_dotenv()

PUERTO_CAMARA = os.getenv('PUERTO_CAMARA', '/dev/ttyUSB1')
PUERTO_BRAZO = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
COLOR_OBJETIVO = os.getenv('COLOR_OBJETIVO', 'Azul')

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
    REINTENTO_OBJETO = "REINTENTO_OBJETO"

def main():
    print("--- INICIANDO CICLO COMPLETO (AUTOMÁTICO) ---")
    
    try:
        camara = CameraSerial(port=PUERTO_CAMARA, baud_rate=460800)
        brazo = ArmController(puerto=PUERTO_BRAZO, baudios=115200)
    except Exception as e:
        print(f"[ERROR] No se pudo inicializar el hardware: {e}")
        return

    # --- CONFIGURACIÓN DE PARPADEO (Cámara Laptop) ---
    detector_parpadeo = BlinkDetector(target_blinks=2, window_time=3.0)

    estado_actual = Estado.HOME
    estado_previo_caida = Estado.HOME
    macro_movimiento_hecho = False
    
    # --- CONTROL DE CÁMARA (SIEMPRE ACTIVA) ---
    camara_activa = True
    
    # --- CONFIGURACIÓN DE RECOLECCIÓN ---
    Z_UMBRAL_LOCKON = 120    
    Z_LIMITE_FINAL = 90   
    Z_LIMITE_ENTREGA = 160
    TOLERANCIA_CENTRADO = 12 
    lockon_activado = False  
    lockon_activado_boca = False
    
    # --- VARIABLES DE RECUPERACIÓN Y SONDEO ---
    contador_pastilla_perdida = 0
    recuperacion_pastilla_intentada = False
    contador_sondeo = 0
    contador_sondeo_color = 0
    fase_sondeo_color = "IZQUIERDA" # Inicia buscando a la izquierda

    # --- VARIABLES DE MONITOREO AUTOMÁTICO ---
    pastilla_en_transporte = False
    contador_caida = 0
    UMBRAL_PERSISTENCIA_CAIDA = 15 # Requiere ~1.5 segundos de "VACIA" para confirmar caída
    
    # --- VARIABLES DE TIEMPO PARA MOVIMIENTO ---
    last_move_time = 0
    INTERVALO_MOVIMIENTO = 0.2 # Mínimo 100ms entre comandos de movimiento suave

    # --- FILTRO DE PERSISTENCIA (DETECCIÓN) ---
    persistencia_deteccion = 0
    UMBRAL_PERSISTENCIA_DETECCION = 5 # Frames seguidos viendo la pastilla para confiar
    
    print("Sistema listo. Parpadea 2 veces para iniciar el ciclo.")


    try:
        while True:
            ahora = time.time()
            
            # --- POLLING DE TECLADO SIEMPRE ACTIVO ---
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): 
                print("[SISTEMA] 'Q' presionada. Saliendo...")
                break

            # Control de Encendido/Apagado lógico de la cámara
            if camara_activa:
                frame = camara.get_frame()
                if frame is None:
                    # Mantener ventana viva si no hay frame
                    frame_placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(frame_placeholder, "ESPERANDO CAMARA...", (150, 240), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                    cv2.imshow('Ciclo Autonomo Inteligente', frame_placeholder)
                    continue
                frame_vis = frame.copy()
            else:
                # Mostrar frame de pausa si la cámara está apagada
                frame_vis = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame_vis, "CAMARA APAGADA", (150, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
                frame = None

            # Actualizar z_coord al inicio (siempre leer ToF)
            dist_actual = brazo.obtener_distancia()
            z_coord = dist_actual
            
            # --- DETECCIÓN DE EMERGENCIA FÍSICA ---
            if brazo.en_emergencia and estado_actual != Estado.EMERGENCIA:
                print("[SISTEMA] Entrando en modo EMERGENCIA...")
                estado_actual = Estado.EMERGENCIA
                macro_movimiento_hecho = False

            # --- DETECCIÓN DE COLISIÓN (RF-08) ---
            if brazo.estado_pinza == "COLISION" and estado_actual != Estado.EMERGENCIA:
                print("\n!!! ALERTA: COLISIÓN / IMPACTO DETECTADO EN LA PINZA !!!")
                estado_actual = Estado.EMERGENCIA
                macro_movimiento_hecho = False

            # --- DETECCIÓN DE CAÍDA ---
            if estado_actual in [Estado.OBSERVACION_MANIQUI, Estado.SEGUIMIENTO_BOCA, Estado.ESPERA_CONFIRMACION_ENTREGA]:
                # Ignorar si el brazo está en movimiento o si la pinza está abierta
                if brazo.estado_pinza == "VACIA" and pastilla_en_transporte and not brazo.busy:
                    contador_caida += 1
                    if contador_caida >= UMBRAL_PERSISTENCIA_CAIDA:
                        print("\n!!! POSIBLE OBJETO PERDIDO (Confirmado tras múltiples lecturas) !!!")
                        estado_previo_caida = estado_actual
                        estado_actual = Estado.REINTENTO_OBJETO
                        macro_movimiento_hecho = False
                        contador_caida = 0
                else:
                    contador_caida = 0 # Reset si recuperamos la lectura o si está busy
            
            # =================================================
            # --- MÁQUINA DE ESTADOS ---
            # =================================================

            if estado_actual == Estado.HOME:
                lockon_activado = False
                pastilla_en_transporte = False
                camara_activa = False # APAGAR cámara al volver a casa
                
                if not macro_movimiento_hecho:
                    brazo.mover_a_estado("HOME", forzar=True)
                    detector_parpadeo.start_cam() # Iniciar cámara de laptop en HOME
                    macro_movimiento_hecho = True
                
                cv2.putText(frame_vis, "HOME - Parpadea 2 veces", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                # Activar ciclo por parpadeo o tecla 'n'
                if detector_parpadeo.check_for_trigger() or key == ord('n'):
                    print("[SISTEMA] Intención detectada. Iniciando ciclo...")
                    detector_parpadeo.stop_cam() # Detener cámara de laptop al iniciar
                    estado_actual = Estado.OBSERVACION
                    macro_movimiento_hecho = False

            elif estado_actual == Estado.OBSERVACION:
                if not macro_movimiento_hecho:
                    brazo.mover_a_estado("OBSERVACION") # Mover a posición de pastillas
                    time.sleep(2) 
                    # LLEGAMOS: Ahora sí prendemos cámara
                    camara_activa = True 
                    macro_movimiento_hecho = True
                
                # Evitar crash si camara no dio frame aún
                if frame is None: continue

                # Obtener colores y sus centros
                frame_vis, colores, info_colores = process_color_frame(frame_vis)
                
                if COLOR_OBJETIVO in colores:
                    print(f"[CONTROL] Color {COLOR_OBJETIVO} detectado. Iniciando segmentación de pastilla...")
                    estado_actual = Estado.RECOLECCION
                    macro_movimiento_hecho = False
                    contador_sondeo_color = 0
                else:
                    # LÓGICA DE SONDEO SECUENCIAL (derecha -> izquierda)
                    cv2.putText(frame_vis, f"Sondeando {COLOR_OBJETIVO} ({fase_sondeo_color})...", (10, 60), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
                    if fase_sondeo_color == "DERECHA":
                        # Mover hacia la derecha (ahora restando ángulo)
                        if brazo.estado_actual[4] > 40:
                            if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                                nuevo_s0 = brazo.estado_actual[4] - 1
                                brazo.mover_tiempo([(4, nuevo_s0)], esperar=False)
                                last_move_time = ahora
                        else:
                            print("[SONDEO] Límite derecho alcanzado. Cambiando a izquierda.")
                            fase_sondeo_color = "IZQUIERDA"
                    
                    elif fase_sondeo_color == "IZQUIERDA":
                        # Mover hacia la izquierda (ahora sumando ángulo)
                        if brazo.estado_actual[4] < 140:
                            if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                                nuevo_s0 = brazo.estado_actual[4] + 1
                                brazo.mover_tiempo([(4, nuevo_s0)], esperar=False)
                                last_move_time = ahora
                        else:
                            print("[SONDEO] Límite izquierdo alcanzado. Reiniciando sondeo.")
                            fase_sondeo_color = "DERECHA"

            elif estado_actual == Estado.RECOLECCION:
                if frame is None: continue
                
                # Inicializar variables de error y targets para evitar UnboundLocalError
                ex, ey = 0, 0
                targets = {}
                
                # Intentar segmentación fina de la pastilla
                frame_vis, info = process_pastillas_frame(frame_vis, COLOR_OBJETIVO.lower())

                
                # Obtener detección de color como respaldo
                _, colores_backup, info_colores_backup = process_color_frame(frame.copy())
                
                if info or lockon_activado:
                    # Aplicar filtro de persistencia temporal
                    if not lockon_activado:
                        persistencia_deteccion += 1
                        if persistencia_deteccion < UMBRAL_PERSISTENCIA_DETECCION:
                            cv2.putText(frame_vis, f"FILTRANDO RUIDO ({persistencia_deteccion}/{UMBRAL_PERSISTENCIA_DETECCION})", (10, 60), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                            info = None # Ignorar detección hasta que sea estable
                    
                    if info or lockon_activado:
                        ex, ey, area = info if info else (0, 0, 0)
                        targets = {} 
                        
                        if not lockon_activado:
                            # --- CENTRADO EJE X (S4) ---
                            s4_needs_move = abs(ex) > TOLERANCIA_CENTRADO
                            if s4_needs_move:
                                # INVERTIDO: si ex > 0 (objetivo a la derecha), restamos ángulo
                                targets[4] = brazo.estado_actual[4] + (-1 if ex > 0 else 1)

                            # --- EJE Y (S15 + S6) ---
                            # Condición de movimiento vertical:
                            # 1. Si Z < 130 (centrado final), NO bajar si la base se está moviendo (Exclusión mutua)
                            # 2. Si Z > 130, permitir bajar si el error X es razonable (< 40)
                            if z_coord < 130:
                                can_move_vertical = not s4_needs_move
                            else:
                                can_move_vertical = abs(ex) < 40
                            
                            if can_move_vertical:
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
                        FINAL_CORRECTION_S0 = 0  # Grados extra para centrar X
                        FINAL_CORRECTION_S15 = 5 # Grados extra para centrar Y (hacia arriba)

                        print(f"[INFO] Aplicando corrección final: S0+{FINAL_CORRECTION_S0}, S15+{FINAL_CORRECTION_S15}")
                        brazo.mover_tiempo([
                            (4, brazo.estado_actual[4] + FINAL_CORRECTION_S0),
                            (15, brazo.estado_actual[15] + FINAL_CORRECTION_S15)
                        ])

                        estado_actual = Estado.ESPERA_CONFIRMACION_AGARRE
                        macro_movimiento_hecho = False

                    
                    if targets:
                        # Preparamos los movimientos para enviar en un solo comando serial si es posible
                        movimientos_finales = []
                        
                        # Manejo de S0 (Pulsado)
                        if 4 in targets:
                            movimientos_finales.append((4, targets[4]))
                        
                        # Manejo del resto de servos (S15, S6, S1)
                        otros_targets = [(p, a) for p, a in targets.items() if p != 4]
                        
                        if movimientos_finales or (otros_targets and (ahora - last_move_time) > INTERVALO_MOVIMIENTO):
                            # Combinamos todo en un envío para reducir latencia serial
                            # solo si ha pasado el tiempo para los servos secundarios
                            if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                                movimientos_finales.extend(otros_targets)
                                last_move_time = ahora
                            
                            if movimientos_finales:
                                brazo.mover_tiempo(movimientos_finales, esperar=False)
                    
                    # Resetear contadores si hay detección o lock-on
                    contador_pastilla_perdida = 0
                    recuperacion_pastilla_intentada = False
                
                elif COLOR_OBJETIVO in colores_backup:
                    # RESPALDO: Si no hay segmentación fina pero sí vemos el color
                    cx, cy = info_colores_backup[COLOR_OBJETIVO]
                    ex_b = cx - (frame_vis.shape[1] // 2)
                    ey_b = cy - (frame_vis.shape[0] // 2)
                    
                    targets = {}
                    # Movimiento suave hacia el color detectado
                    if abs(ex_b) > 20:
                        # INVERTIDO: si ex_b > 0, restamos ángulo. Paso aumentado a 2.
                        targets[4] = brazo.estado_actual[4] + (-2 if ex_b > 0 else 2)
                    
                    # PRIORIDAD: Solo bajar si estamos relativamente centrados horizontalmente
                    if abs(ex_b) < 30 and abs(ey_b) > 10:
                        targets[15] = brazo.estado_actual[15] + (1 if ey_b > 0 else -1)
                    
                    if targets and (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                        brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                        last_move_time = ahora
                    
                    # RESETEAR contadores de pérdida si el respaldo ve el color
                    contador_pastilla_perdida = 0
                    recuperacion_pastilla_intentada = False
                    
                    cv2.putText(frame_vis, f"Aproximando a {COLOR_OBJETIVO}...", (10, 60), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                else:
                    persistencia_deteccion = 0
                    # LÓGICA DE RECUPERACIÓN (Si perdemos la pastilla)
                    contador_pastilla_perdida += 1
                    
                    if contador_pastilla_perdida == 30 and not recuperacion_pastilla_intentada:
                        print("[CONTROL] Pastilla perdida. Intentando recuperación con S15 (+10°)...")
                        # Subir S15 (restar ángulo para apuntar más hacia arriba)
                        nuevo_s15 = max(0, brazo.estado_actual[15] - 10)
                        brazo.mover_tiempo([(15, nuevo_s15)], esperar=True)
                        recuperacion_pastilla_intentada = True
                    
                    elif contador_pastilla_perdida > 80:
                        print("[CONTROL] Pastilla no encontrada tras recuperación. Regresando a OBSERVACION.")
                        estado_actual = Estado.OBSERVACION
                        macro_movimiento_hecho = False
                        contador_pastilla_perdida = 0
                        recuperacion_pastilla_intentada = False

            elif estado_actual == Estado.ESPERA_CONFIRMACION_AGARRE:
                cv2.putText(frame_vis, "PREPARANDO AGARRE... ESPERE", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                cv2.imshow('Ciclo Autonomo Inteligente', frame_vis)
                cv2.waitKey(1)
                
                # 1. Esperar 1 segundo antes de cerrar
                print("\n[CONTROL] Pausa de 1s antes de cerrar...")
                time.sleep(1.0)
                
                # 2. Cerrar pinza
                print("[CONTROL] Cerrando pinza...")
                brazo.mover_tiempo([(12, 0)], forzar=True, esperar=True) 
                time.sleep(0.5)
                
                # --- NUEVO: CAPTURAR BASELINE INMEDIATAMENTE ---
                m_init = brazo.mag1
                brazo.evaluador_agarre.capturar_baseline(m_init[0], m_init[1], m_init[2])
                
                # 3. Levantar brazo
                print("[CONTROL] Levantando brazo para verificación...")
                brazo.mover_a_estado("PRE_RECOLECCION", esperar=True)
                time.sleep(1.0)
                
                # 4. Verificación Automática (Magnetómetro con SujecionEvaluator)
                m1 = brazo.mag1
                est_p = brazo.estado_pinza
                print(f"\n[VERIFICACIÓN] Estado Pinza: {est_p} | Datos: X:{m1[0]:.1f}, Y:{m1[1]:.1f}, Z:{m1[2]:.1f}")
                
                if est_p == "CON_OBJETO":
                    print("[¡ÉXITO!] Pastilla detectada automáticamente. Procediendo a búsqueda de maniquí.")
                    pastilla_en_transporte = True
                    estado_actual = Estado.OBSERVACION_MANIQUI
                    # Loguear éxito para calibración continua si se desea
                    log_mag_data(m1[0], m1[1], m1[2], "CON_OBJETO")
                else:
                    print("[FALLO] No se detectó la pastilla. Abriendo pinza y reintentando...")
                    pastilla_en_transporte = False
                    brazo.mover_tiempo([(12, 80)], esperar=True) # Abrir
                    estado_actual = Estado.OBSERVACION
                    # Loguear fallo para calibración continua si se desea
                    log_mag_data(m1[0], m1[1], m1[2], "VACIO_CERRADO")
                
                macro_movimiento_hecho = False

            elif estado_actual == Estado.OBSERVACION_MANIQUI:
                # Inicializar variables de error
                ex, ey = 0, 0
                
                if not macro_movimiento_hecho:
                    camara_activa = False # APAGAR CAMARA MIENTRAS VIAJA
                    print("[CONTROL] Yendo a posición de entrega (Maniquí)...")
                    # Forzar movimiento completo con espera
                    brazo.mover_a_estado("OBSERVACION_MANIQUI", forzar=True, esperar=True)
                    time.sleep(0.5)
                    # LLEGAMOS AL MANIQUÍ: Prender
                    camara_activa = True
                    macro_movimiento_hecho = True
                    lockon_activado_boca = False
                
                if frame is None: continue

                # Ya no rotamos el frame para el maniquí
                frame_vis = frame.copy()
                
                # Centro objetivo visual (Punto azul)
                cv_h, cv_w = frame_vis.shape[:2]
                cv2.drawMarker(frame_vis, (cv_w // 2, cv_h // 2), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)
                
                frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                if coords_boca:
                    estado_actual = Estado.SEGUIMIENTO_BOCA
                    macro_movimiento_hecho = False
                else:
                    cv2.putText(frame_vis, "Buscando boca...", (10, 60), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

            elif estado_actual == Estado.SEGUIMIENTO_BOCA:
                if frame is None: continue

                # Inicializar variables de error para evitar UnboundLocalError
                ex, ey = 0, 0
                
                # Ya no rotamos el frame
                frame_vis = frame.copy()
                
                # Centro objetivo visual (Punto azul)
                cv_h, cv_w = frame_vis.shape[:2]
                cv2.drawMarker(frame_vis, (cv_w // 2, cv_h // 2), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)
                
                frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                
                if coords_boca:
                    # Resetear contador de sondeo si vemos la boca
                    contador_sondeo = 0
                    
                    # Errores en frame corregido + Offsets
                    ex = coords_boca[0] - (frame_vis.shape[1] // 2) + BOCA_OFFSET_X
                    ey_raw = coords_boca[1] - (frame_vis.shape[0] // 2) + BOCA_OFFSET_Y
                    
                    # --- COMPENSACIÓN DINÁMICA DE ALTURA (Y) ---
                    dist_factor = max(0, Z_UMBRAL_LOCKON - z_coord)
                    offset_y_compensacion = int(dist_factor * BOCA_COMP_FACTOR) 
                    ey = ey_raw + offset_y_compensacion 

                    targets = {} 
                    
                    if not lockon_activado_boca:
                        # Centrado Horizontal (S0)
                        if abs(ex) > 8:
                            paso_x = 3 if abs(ex) > 60 else 2
                            # INVERTIDO: si ex > 0 (objetivo a la derecha visual), restamos ángulo
                            targets[4] = brazo.estado_actual[4] + (-paso_x if ex > 0 else paso_x)
                        
                        # Centrado Vertical Dinámico (S15 + S6)
                        if abs(ey) > 10:
                            # S15: 0 arriba, 180 abajo. Si ey > 0 (objetivo abajo), sumamos.
                            targets[15] = brazo.estado_actual[15] + (1 if ey > 0 else -1)
                            if abs(ey) > 30:
                                targets[6] = brazo.estado_actual[6] + (1 if ey > 0 else -1)

                    # Lógica de ACERCAMIENTO COORDINADO (Extensión S1 + S6)
                    if z_coord > Z_LIMITE_ENTREGA:
                        # S1: Progresión constante hacia adelante
                        if brazo.estado_actual[1] > 70:
                            targets[1] = brazo.estado_actual[1] - 1
                        
                        # S6: Ayuda a la extensión solo si la boca está centrada verticalmente
                        if 6 not in targets and brazo.estado_actual[6] > 0:
                            targets[6] = brazo.estado_actual[6] - 1
                        
                        if z_coord <= Z_UMBRAL_LOCKON and abs(ex) <= TOLERANCIA_CENTRADO:
                            if not lockon_activado_boca:
                                print("[CONTROL] Lock-On Boca ACTIVADO.")
                                lockon_activado_boca = True

                    # 3. Condición de Parada Final
                    if z_coord <= Z_LIMITE_ENTREGA:
                        print(f"[ToF] POSICION DE ENTREGA ALCANZADA ({z_coord}mm).")
                        estado_actual = Estado.ESPERA_CONFIRMACION_ENTREGA
                        macro_movimiento_hecho = False

                    if targets and (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                        brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                        last_move_time = ahora
                
                else:
                    # LÓGICA DE SONDEO / RECUPERACIÓN (Si perdemos la boca)
                    contador_sondeo += 1
                    
                    if contador_sondeo < 30: 
                        # --- RECUPERACIÓN HACIA ARRIBA ---
                        if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                            nuevo_s15 = max(0, brazo.estado_actual[15] - 2)
                            brazo.mover_tiempo([(15, nuevo_s15)], esperar=False)
                            last_move_time = ahora
                        cv2.putText(frame_vis, "RECUPERANDO (MIRANDO ARRIBA)...", (10, 60), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
                    elif contador_sondeo < 100:
                        # Sondeo lateral oscilante (S0)
                        if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                            offset = int(8 * np.sin(contador_sondeo * 0.15))
                            brazo.mover_tiempo([(4, POSICIONES["OBSERVACION_MANIQUI"][0][1] + offset)], esperar=False)
                            last_move_time = ahora
                        cv2.putText(frame_vis, "SONDEO DE BOCA...", (10, 60), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
                    else:
                        print("[CONTROL] Boca perdida tras sondeo. Regresando a Observación.")
                        estado_actual = Estado.OBSERVACION_MANIQUI
                        macro_movimiento_hecho = False
                        contador_sondeo = 0

            elif estado_actual == Estado.ESPERA_CONFIRMACION_ENTREGA:
                # Ya no rotamos el frame para consistencia visual
                frame_vis = frame.copy()
                
                cv2.putText(frame_vis, "ENTREGA LISTA - Confirma con 'c'", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                if key == ord('c'):
                    print("\n" + "="*50)
                    print("[VALIDACIÓN FINAL] ¿La pastilla llegó correctamente sujeta? (y/n)")
                    m1 = brazo.mag1
                    print(f"[DATOS EN BOCA] X: {m1[0]:.1f}, Y: {m1[1]:.1f}, Z: {m1[2]:.1f}")
                    
                    resultado = ask_user_success()
                    
                    # Guardar en log con etiqueta de posición final
                    etiqueta = "EXITO_ENTREGA" if resultado == 'y' else "FALLO_DURANTE_VIAJE"
                    log_mag_data(m1[0], m1[1], m1[2], etiqueta)
                    
                    if resultado == 'y':
                        print("[CONTROL] Entrega confirmada. Soltando pastilla...")
                        estado_actual = Estado.ENTREGA
                    else:
                        print("[AVISO] La entrega falló (se cayó o se movió). Regresando a HOME.")
                        estado_actual = Estado.HOME
                    
                    macro_movimiento_hecho = False
                    print("="*50 + "\n")

            elif estado_actual == Estado.ENTREGA:
                sosteniendo_y_logueando = False # Detener logueo al soltar
                brazo.mover_tiempo([(12, 80)]) # Abrir a 80
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

            elif estado_actual == Estado.REINTENTO_OBJETO:
                cv2.rectangle(frame_vis, (0, 0), (frame_vis.shape[1], frame_vis.shape[0]), (0, 165, 255), 8)
                cv2.putText(frame_vis, "ALERTA: OBJETO NO DETECTADO", (50, 150), cv2.FONT_HERSHEY_DUPLEX, 1.0, (0, 165, 255), 2)
                cv2.putText(frame_vis, "'R' RE-CALIBRAR | 'Q' ABORTAR (HOME)", (70, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                if key == ord('r'):
                    print("[RECUPERACIÓN] Re-calibrando sujeción con valores actuales...")
                    m1 = brazo.mag1
                    brazo.evaluador_agarre.capturar_baseline(m1[0], m1[1], m1[2])
                    estado_actual = estado_previo_caida
                    # Forzamos False para que repita el movimiento macro si estaba en OBSERVACION_MANIQUI
                    macro_movimiento_hecho = False 
                elif key == ord('q'):
                    print("[SISTEMA] Abortando ciclo por pérdida de objeto.")
                    estado_actual = Estado.HOME
                    macro_movimiento_hecho = False

            # --- DIBUJAR INFORMACIÓN GLOBAL (Al final para que no se pierda al rotar) ---
            z_coord = dist_actual
            # Umbral dinámico para el color según el estado
            umbral_actual = Z_LIMITE_ENTREGA if "BOCA" in estado_actual or "ENTREGA" in estado_actual or "MANIQUI" in estado_actual else Z_LIMITE_FINAL
            color_z = (0, 255, 0) if z_coord <= umbral_actual else (0, 255, 255)
            cv2.putText(frame_vis, f"COORD Z (ToF): {z_coord}mm", (10, 30), cv2.FONT_HERSHEY_DUPLEX, 0.8, color_z, 2)
            
            # --- VISUALIZACIÓN DE MAGNETÓMETRO (Solo M1 - Inferior Derecha) ---
            m1 = brazo.mag1
            est_p = brazo.estado_pinza
            # Colores: Verde para objeto, Amarillo para abierta, Rojo para vacía
            col_p = (0, 255, 0) if est_p == "CON_OBJETO" else (0, 255, 255) if est_p == "ABIERTA" else (0, 0, 255)
            
            # Mostrar valores crudos para calibración manual
            texto_mag_vals = f"MAG RAW -> X: {m1[0]:.1f} Y: {m1[1]:.1f} Z: {m1[2]:.1f}"
            texto_mag_status = f"ESTADO PINZA: {est_p}"
            
            cv2.putText(frame_vis, texto_mag_vals, (10, frame_vis.shape[0] - 70), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame_vis, texto_mag_status, (10, frame_vis.shape[0] - 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, col_p, 2)
            
            cv2.putText(frame_vis, f"ESTADO CICLO: {estado_actual}", (10, frame_vis.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow('Ciclo Autonomo Inteligente', frame_vis)

    except KeyboardInterrupt:
        print("\nEjecución cancelada.")
    finally:
        print("\nApagando...")
        try:
            # Agregamos esperar=True para que el movimiento suave se complete antes de cerrar
            brazo.mover_a_estado("HOME", forzar=True, esperar=True)
            brazo.cerrar()
            camara.liberar()
        except: pass
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
