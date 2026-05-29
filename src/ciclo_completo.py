# src/ciclo_completo.py
import sys
import os
import subprocess
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
from modules.pastillas_detector import process_pastillas_frame, verify_pill_in_gripper
from modules.detectarColor import process_color_frame
from modules.detectorBoca import get_mouth_coordinates
from modules.auto_exposure import AutoExposureControl
from modules.blinkDetector import BlinkDetector
from constants.posiciones import POSICIONES
from modules.mag_logger import log_mag_data, ask_user_success # Importar logger
from constants.config import (
    BOCA_OFFSET_X, BOCA_OFFSET_Y, BOCA_COMP_FACTOR,
    OFFSET_ALINEACION_X, OFFSET_ALINEACION_Y,
    PIN_BASE, PIN_HOMBRO, PIN_CODO, PIN_MUÑECA, PIN_ROTADOR, PIN_PINZA
)

# Cargar variables de entorno
load_dotenv()

PUERTO_CAMARA = os.getenv('PUERTO_CAMARA', '/dev/ttyACM0')
PUERTO_BRAZO = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
COLOR_OBJETIVO = os.getenv('COLOR_OBJETIVO', 'Rojo')

class Estado:
    HOME = "HOME"
    OBSERVACION = "OBSERVACION"
    SEGUIMIENTO_PASTILLA = "SEGUIMIENTO_PASTILLA"
    RECOLECCION = "RECOLECCION"
    ALINEACION_FINA = "ALINEACION_FINA"
    ESPERA_CONFIRMACION_AGARRE = "ESPERA_CONFIRMACION_AGARRE"
    OBSERVACION_MANIQUI = "OBSERVACION_MANIQUI"
    SEGUIMIENTO_BOCA = "SEGUIMIENTO_BOCA"
    ENTREGA = "ENTREGA"
    ESPERA_CONFIRMACION_ENTREGA = "ESPERA_CONFIRMACION_ENTREGA"
    EMERGENCIA = "EMERGENCIA"
    REINTENTO_OBJETO = "REINTENTO_OBJETO"
    CALIBRAR = "CALIBRAR"

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
    Z_UMBRAL_LOCKON = 135    
    Z_LIMITE_FINAL = 95  
    Z_LIMITE_ENTREGA = 180
    TOLERANCIA_CENTRADO = 12 
    lockon_activado = False  
    lockon_activado_boca = False
    
    # --- VARIABLES DE RECUPERACIÓN Y SONDEO ---
    contador_pastilla_perdida = 0
    recuperacion_pastilla_intentada = False
    contador_sondeo = 0
    contador_sondeo_color = 0
    # Prioridad: Verde a la derecha, Rojo a la izquierda
    fase_sondeo_color = "IZQUIERDA" if COLOR_OBJETIVO.lower() == "verde" else "DERECHA"

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
    contador_segmentacion_fallida = 0 # Timeout si vemos color pero no pastilla
    
    # --- BUFFERS DE ERROR PARA MOVIMIENTO SUAVE ---
    buffer_ex = []
    buffer_ey = []
    BUFFER_SIZE = 10
    
    # --- VARIABLES DE VELOCIDAD Y SEGURIDAD ---
    last_z = 0
    last_z_time = time.time()
    velocidad_z = 0.0
    VELOCIDAD_LIMITE = 250.0 # mm/s
    DISTANCIA_SEGURIDAD = 300.0 # mm (30 cm)

    print("Sistema listo. Parpadea 2 veces para iniciar el ciclo.")

    # --- NUEVO: CALIBRACIÓN INICIAL DE VACÍO ---
    print("\n[CALIBRACIÓN] Calibrando sensor de sujeción (vacío)...")
    brazo.mover_tiempo([(PIN_PINZA, 0)], forzar=True, esperar=True)
    time.sleep(1.0)
    
    # Registrar vacío en HOME
    m_vacio_home = brazo.mag1
    brazo.evaluador_agarre.registrar_vacio(m_vacio_home[0], m_vacio_home[1], m_vacio_home[2], estado="HOME")
    
    # Registrar vacío en PRE_RECOLECCION (donde se hace la verificación crítica)
    print("[CALIBRACIÓN] Moviendo a PRE_RECOLECCION para firma de vacío en altura...")
    brazo.mover_a_estado("PRE_RECOLECCION", esperar=True)
    time.sleep(1.0)
    m_vacio_pre = brazo.mag1
    brazo.evaluador_agarre.registrar_vacio(m_vacio_pre[0], m_vacio_pre[1], m_vacio_pre[2], estado="PRE_RECOLECCION")
    
    brazo.mover_tiempo([(PIN_PINZA, 80)], forzar=True, esperar=True)
    print("[CALIBRACIÓN] Listo.\n")

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

            # --- CÁLCULO DE VELOCIDAD (mm/s) ---
            dt = ahora - last_z_time
            if dt >= 0.05: # Calcular cada 50ms mínimo para estabilidad
                # Velocidad positiva = acercándose al objetivo
                velocidad_z = (last_z - dist_actual) / dt
                # Suavizado básico (Promedio ponderado opcional si es muy ruidoso)
                # velocidad_z = (velocidad_z * 0.7) + (((last_z - dist_actual) / dt) * 0.3)
                last_z = dist_actual
                last_z_time = ahora
            
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
                    # Resetear control de movimiento
                    lockon_activado = False
                    buffer_ex.clear()
                    buffer_ey.clear()
                    persistencia_deteccion = 0
                else:
                    # LÓGICA DE SONDEO SECUENCIAL (derecha -> izquierda)
                    cv2.putText(frame_vis, f"Sondeando {COLOR_OBJETIVO} ({fase_sondeo_color})...", (10, 60), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
                    if fase_sondeo_color == "DERECHA":
                        # Mover hacia la derecha (ahora restando ángulo)
                        if brazo.estado_actual[PIN_BASE] > 40:
                            if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                                nuevo_s0 = brazo.estado_actual[PIN_BASE] - 1
                                brazo.mover_tiempo([(PIN_BASE, nuevo_s0)], esperar=False)
                                last_move_time = ahora
                        else:
                            print("[SONDEO] Límite derecho alcanzado. Cambiando a izquierda.")
                            fase_sondeo_color = "IZQUIERDA"
                    
                    elif fase_sondeo_color == "IZQUIERDA":
                        # Mover hacia la izquierda (ahora sumando ángulo)
                        if brazo.estado_actual[PIN_BASE] < 120:
                            if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                                nuevo_s0 = brazo.estado_actual[PIN_BASE] + 1
                                brazo.mover_tiempo([(PIN_BASE, nuevo_s0)], esperar=False)
                                last_move_time = ahora
                        else:
                            print(f"[SONDEO] Límite izquierdo (160) alcanzado. Cambiando a derecha.")
                            fase_sondeo_color = "DERECHA"


            elif estado_actual == Estado.RECOLECCION:
                if frame is None: continue
                
                # Inicializar variables de error y targets
                ex, ey = 0, 0
                targets = {}
                
                # Intentar segmentación fina de la pastilla
                frame_vis, info = process_pastillas_frame(frame_vis, COLOR_OBJETIVO.lower())

                # Obtener detección de color como respaldo (solo si no hay segmentación fina)
                colores_backup = []
                if not info and not lockon_activado:
                    _, colores_backup, info_colores_backup = process_color_frame(frame.copy())
                
                if info or lockon_activado:
                    # Acumular en buffer si hay detección fina
                    if info:
                        ex_curr, ey_curr, area = info
                        buffer_ex.append(ex_curr)
                        buffer_ey.append(ey_curr)
                        persistencia_deteccion += 1
                    
                    # Filtro de persistencia inicial
                    if not lockon_activado and persistencia_deteccion < UMBRAL_PERSISTENCIA_DETECCION:
                        cv2.putText(frame_vis, f"FILTRANDO RUIDO ({persistencia_deteccion}/{UMBRAL_PERSISTENCIA_DETECCION})", (10, 60), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    else:
                        # Decidir si procesamos movimiento: Cada 10 frames o si estamos en Lock-On
                        ready_to_move = lockon_activado or len(buffer_ex) >= BUFFER_SIZE
                        
                        if ready_to_move:
                            esperar_movimiento = False # Default: No bloquear para centrado fluido
                            
                            if not lockon_activado and buffer_ex:
                                ex = sum(buffer_ex) / len(buffer_ex)
                                ey = sum(buffer_ey) / len(buffer_ey)
                                buffer_ex.clear()
                                buffer_ey.clear()
                            else:
                                ex, ey = 0, 0 # En lockon bajamos verticalmente sin mirar X

                            # --- LÓGICA DE CENTRADO (Solo si NO estamos en Lock-On) ---
                            if not lockon_activado:
                                # Centrado Eje X (PIN_BASE)
                                if abs(ex) > TOLERANCIA_CENTRADO:
                                    targets[PIN_BASE] = brazo.estado_actual[PIN_BASE] + (-1 if ex > 0 else 1)

                                # Centrado Eje Y (PIN_MUÑECA + PIN_CODO) - MÁS LIBERTAD
                                # Permitir bajar si el error X es razonable (40 si está cerca, 70 si está lejos)
                                can_move_vertical = abs(ex) < (40 if z_coord < 130 else 70)
                                
                                if can_move_vertical:
                                    angulo_15 = brazo.estado_actual[PIN_MUÑECA]
                                    angulo_6 = brazo.estado_actual[PIN_CODO]
                                    if abs(ey) > 10:
                                        if ey > 0: # Abajo -> Extender
                                            if angulo_15 < 180: angulo_15 += 1
                                            else: targets[PIN_CODO] = angulo_6 + 1
                                        else:      # Arriba -> Retraer
                                            if angulo_15 > 10: angulo_15 -= 1
                                            else: targets[PIN_CODO] = max(20, angulo_6 - 1)
                                    if angulo_15 != brazo.estado_actual[PIN_MUÑECA]: targets[PIN_MUÑECA] = angulo_15

                            # --- LÓGICA DE DESCENSO (S1 - PIN_HOMBRO) ---
                            if z_coord > Z_UMBRAL_LOCKON:
                                # Descenso suave si la pastilla está razonablemente centrada
                                if abs(ex) < 85 and abs(ey) < 85:
                                    targets[PIN_HOMBRO] = max(5, brazo.estado_actual[PIN_HOMBRO] - 1)
                                    if PIN_CODO not in targets: targets[PIN_CODO] = max(5, brazo.estado_actual[PIN_CODO] - 1)
                            
                            elif z_coord > Z_LIMITE_FINAL:
                                # Transición a LOCK-ON si estamos bien centrados
                                if abs(ex) <= TOLERANCIA_CENTRADO and abs(ey) <= TOLERANCIA_CENTRADO:
                                    if not lockon_activado:
                                        print("[CONTROL] Centrado OK. Lock-On ACTIVADO.")
                                        lockon_activado = True

                                if lockon_activado:
                                    # Bajada vertical directa al límite físico S1=69
                                    targets[PIN_HOMBRO] = 67
                                    if brazo.estado_actual[PIN_MUÑECA] > 20:
                                        targets[PIN_MUÑECA] = brazo.estado_actual[PIN_MUÑECA] - 1
                                    cv2.putText(frame_vis, "LOCK-ON: DESCENSO DIRECTO...", (10, 80), 
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                                else:
                                    cv2.putText(frame_vis, "CENTRANDO FINAL...", (10, 80), 
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                            # --- CONDICIÓN DE PARADA FINAL ---
                            if brazo.estado_actual[PIN_HOMBRO] <= 67 or z_coord <= Z_LIMITE_FINAL:
                                print(f"[ToF] POSICION DE AGARRE ALCANZADA ({z_coord}mm).")
                                
                                # --- COMANDO DE FRENO ACTIVO ---
                                brazo.mover_tiempo([
                                    (PIN_BASE, brazo.estado_actual[PIN_BASE]),
                                    (PIN_HOMBRO, brazo.estado_actual[PIN_HOMBRO]),
                                    (PIN_CODO, brazo.estado_actual[PIN_CODO]),
                                    (PIN_MUÑECA, brazo.estado_actual[PIN_MUÑECA])
                                ], forzar=True, esperar=True)

                                estado_actual = Estado.ESPERA_CONFIRMACION_AGARRE
                                macro_movimiento_hecho = False

                            # --- EJECUCIÓN DE MOVIMIENTOS ---
                            if targets:
                                brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                                last_move_time = ahora

                    # Resetear contadores de pérdida si hay detección o lock-on
                    contador_pastilla_perdida = 0
                    recuperacion_pastilla_intentada = False
                
                elif COLOR_OBJETIVO in colores_backup:
                    # RESPALDO: Detección de color si la segmentación fina falla
                    cx, cy = info_colores_backup[COLOR_OBJETIVO]
                    ex_b = cx - (frame_vis.shape[1] // 2)
                    ey_b = cy - (frame_vis.shape[0] // 2)
                    
                    targets_b = {}
                    if abs(ex_b) > 20:
                        targets_b[PIN_BASE] = brazo.estado_actual[PIN_BASE] + (-2 if ex_b > 0 else 2)
                    
                    if abs(ex_b) < 30 and abs(ey_b) > 10:
                        targets_b[PIN_MUÑECA] = brazo.estado_actual[PIN_MUÑECA] + (1 if ey_b > 0 else -1)
                    
                    if targets_b and (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                        brazo.mover_tiempo([(p, a) for p, a in targets_b.items()], esperar=False)
                        last_move_time = ahora
                    
                    contador_pastilla_perdida = 0
                    recuperacion_pastilla_intentada = False
                    cv2.putText(frame_vis, f"Aproximando a {COLOR_OBJETIVO}...", (10, 60), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                else:
                    # LÓGICA DE RECUPERACIÓN: Si perdemos la pastilla
                    persistencia_deteccion = 0
                    buffer_ex.clear()
                    buffer_ey.clear()
                    contador_pastilla_perdida += 1
                    
                    if contador_pastilla_perdida == 25 and not recuperacion_pastilla_intentada:
                        print("[CONTROL] Pastilla perdida. Subiendo brazo para recuperar vista...")
                        # Subir Hombro y ajustar Muñeca para ver más área (Movimiento hacia arriba en Y visual)
                        nuevo_s1 = min(110, brazo.estado_actual[PIN_HOMBRO] + 15)
                        nuevo_s15 = max(20, brazo.estado_actual[PIN_MUÑECA] - 15)
                        brazo.mover_tiempo([(PIN_HOMBRO, nuevo_s1), (PIN_MUÑECA, nuevo_s15)], esperar=True)
                        recuperacion_pastilla_intentada = True
                    
                    elif contador_pastilla_perdida > 70:
                        print("[CONTROL] Pastilla no encontrada. Regresando a OBSERVACION.")
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
                print("[CONTROL] Compensando altura y cerrando pinza...")
                
                # Desplazamiento forzado manual: Subir muñeca 15 grados antes de cerrar
                nuevo_s7 = max(0, brazo.estado_actual[PIN_MUÑECA] - 14)
                brazo.mover_tiempo([(PIN_MUÑECA, nuevo_s7)], esperar=True)
                time.sleep(1.0)
                
                brazo.mover_tiempo([(PIN_PINZA, 0)], forzar=True, esperar=True) 
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
                
                # --- REFINAMIENTO: Verificación contra firma de VACÍO en PRE_RECOLECCION ---
                exito_real = brazo.evaluador_agarre.verificar_presencia_real(m1[0], m1[1], m1[2], estado="PRE_RECOLECCION")
                
                # --- NUEVO: Verificación Visual con la ESP32-CAM ---
                confirmacion_visual = False
                if frame is not None:
                    confirmacion_visual = verify_pill_in_gripper(frame)
                    print(f"[VERIFICACIÓN] Visual (Pill Pink/White): {'OK' if confirmacion_visual else 'NO DETECTADA'}")
                
                print(f"\n[VERIFICACIÓN] Magnética (Continua): {est_p} | Magnética (Relativa): {'OK' if exito_real else 'FALLO'}")
                print(f"[DATOS MAG] X:{m1[0]:.1f}, Y:{m1[1]:.1f}, Z:{m1[2]:.1f}")
                
                # Prioridad: Si la verificación relativa (exito_real) es OK y confirmación visual también,
                # o si una de ellas es extremadamente sólida.
                if (exito_real and confirmacion_visual) or (exito_real and brazo.evaluador_agarre.verificar_presencia_real(m1[0], m1[1], m1[2], estado="PRE_RECOLECCION")):
                    # Re-evaluamos para ver si el delta es muy alto (indicativo de objeto real vs ruido)
                    norma_actual = (m1[0]**2 + m1[1]**2 + m1[2]**2)**0.5
                    ref_vacio = brazo.evaluador_agarre.baselines_vacio.get("PRE_RECOLECCION", 0)
                    delta_final = abs(norma_actual - ref_vacio)

                    if delta_final > 400:
                        if confirmacion_visual:
                            print(f"[¡ÉXITO!] Pastilla confirmada por VISIÓN (Delta MAG anómalo: {delta_final:.1f}).")
                            pastilla_en_transporte = True
                            estado_actual = Estado.CALIBRAR
                        else:
                            print(f"[AVISO] Falso positivo evitado. Delta MAG anómalo ({delta_final:.1f}) sin confirmación visual.")
                            pastilla_en_transporte = False
                            brazo.mover_tiempo([(PIN_PINZA, 80)], esperar=True)
                            estado_actual = Estado.OBSERVACION
                    elif delta_final > 60 or (delta_final > 25 and confirmacion_visual):
                        print(f"[¡ÉXITO!] Pastilla confirmada (Delta: {delta_final:.1f}). Procediendo a CALIBRACIÓN.")
                        pastilla_en_transporte = True
                        estado_actual = Estado.CALIBRAR # Cambiado de OBSERVACION_MANIQUI a CALIBRAR
                        log_mag_data(m1[0], m1[1], m1[2], "CON_OBJETO")
                    else:
                        print(f"[AVISO] Falso positivo evitado. Delta ({delta_final:.1f}) insuficiente o sin confirmación visual.")
                        pastilla_en_transporte = False
                        brazo.mover_tiempo([(PIN_PINZA, 80)], esperar=True)
                        estado_actual = Estado.OBSERVACION
                else:
                    if not exito_real:
                        print("[FALLO CRÍTICO] La pinza parece estar VACÍA (Falso Positivo evitado).")
                    else:
                        print("[FALLO] No se detectó la pastilla.")
                    
                    pastilla_en_transporte = False
                    brazo.mover_tiempo([(PIN_PINZA, 80)], esperar=True) # Abrir
                    estado_actual = Estado.OBSERVACION
                    log_mag_data(m1[0], m1[1], m1[2], "VACIO_CERRADO")
                
                macro_movimiento_hecho = False

            elif estado_actual == Estado.CALIBRAR:
                print("\n[MODO CALIBRAR] Estabilizando para medición de Magnetómetro (1.5s)...")
                cv2.putText(frame_vis, "CALIBRANDO MAGNETOMETRO...", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
                cv2.imshow('Ciclo Autonomo Inteligente', frame_vis)
                cv2.waitKey(1)

                lecturas_mag = []
                inicio_cal = time.time()
                while time.time() - inicio_cal < 1.5:
                    lecturas_mag.append((brazo.mag1[0]**2 + brazo.mag1[1]**2 + brazo.mag1[2]**2)**0.5)
                    time.sleep(0.05)
                
                norma_promedio = sum(lecturas_mag) / len(lecturas_mag)
                ref_vacio = brazo.evaluador_agarre.baselines_vacio.get("PRE_RECOLECCION", 0)
                delta_calibrado = abs(norma_promedio - ref_vacio)

                print("="*40)
                print(f" RESULTADO CALIBRACIÓN (en PRE_RECOLECCION)")
                print(f" Norma Promedio con Objeto: {norma_promedio:.1f} uT")
                print(f" Referencia Vacío: {ref_vacio:.1f} uT")
                print(f" DELTA DETECTADO: {delta_calibrado:.1f} uT")
                print("="*40)
                print("[SISTEMA] Continuando a observación de maniquí...\n")
                
                estado_actual = Estado.OBSERVACION_MANIQUI
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
                    buffer_ex.clear()
                    buffer_ey.clear()
                else:
                    cv2.putText(frame_vis, "Buscando boca...", (10, 60), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

            elif estado_actual == Estado.SEGUIMIENTO_BOCA:
                if frame is None: continue

                # Inicializar variables de error y targets
                ex, ey = 0, 0
                targets = {}
                
                # Ya no rotamos el frame
                frame_vis = frame.copy()
                
                # Centro objetivo visual (Punto azul)
                cv_h, cv_w = frame_vis.shape[:2]
                cv2.drawMarker(frame_vis, (cv_w // 2, cv_h // 2), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)
                
                frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                
                if coords_boca:
                    # Acumular en buffer
                    ex_boca = coords_boca[0] - (frame_vis.shape[1] // 2) + BOCA_OFFSET_X
                    ey_raw_boca = coords_boca[1] - (frame_vis.shape[0] // 2) + BOCA_OFFSET_Y
                    
                    buffer_ex.append(ex_boca)
                    buffer_ey.append(ey_raw_boca)
                    
                    # Decidir si procesamos movimiento: Cada 10 frames o si estamos en Lock-On
                    ready_to_move = lockon_activado_boca or len(buffer_ex) >= BUFFER_SIZE
                    
                    if ready_to_move:
                        # Resetear contador de sondeo si vemos la boca
                        contador_sondeo = 0
                        
                        if not lockon_activado_boca and buffer_ex:
                            ex = sum(buffer_ex) / len(buffer_ex)
                            ey_raw = sum(buffer_ey) / len(buffer_ey)
                            buffer_ex.clear()
                            buffer_ey.clear()
                        else:
                            ex, ey_raw = 0, 0 # En lockon bajamos verticalmente sin mirar X

                        # --- COMPENSACIÓN DINÁMICA DE ALTURA (Y) ---
                        dist_factor = max(0, Z_UMBRAL_LOCKON - z_coord)
                        offset_y_compensacion = int(dist_factor * BOCA_COMP_FACTOR) 
                        ey = ey_raw + offset_y_compensacion 

                        # --- LÓGICA DE CENTRADO (Solo si NO hay Lock-On) ---
                        if not lockon_activado_boca:
                            # Centrado Horizontal (S0 - PIN_BASE)
                            if abs(ex) > 8:
                                paso_x = 3 if abs(ex) > 60 else 2
                                targets[PIN_BASE] = brazo.estado_actual[PIN_BASE] + (-paso_x if ex > 0 else paso_x)
                            
                            # Centrado Vertical Dinámico (S7 + S6)
                            if abs(ey) > 10:
                                targets[PIN_MUÑECA] = brazo.estado_actual[PIN_MUÑECA] + (1 if ey > 0 else -1)
                                if abs(ey) > 30:
                                    targets[PIN_CODO] = brazo.estado_actual[PIN_CODO] + (1 if ey > 0 else -1)

                        # --- LÓGICA DE ACERCAMIENTO COORDINADO ---
                        if z_coord > Z_LIMITE_ENTREGA:
                            # Progresión constante hacia adelante (S1)
                            if brazo.estado_actual[PIN_HOMBRO] > 70:
                                targets[PIN_HOMBRO] = brazo.estado_actual[PIN_HOMBRO] - 1
                            
                            # Ayuda a la extensión (S6) solo si está centrado verticalmente
                            if PIN_CODO not in targets and brazo.estado_actual[PIN_CODO] > 0:
                                targets[PIN_CODO] = brazo.estado_actual[PIN_CODO] - 1
                            
                            # Activar Lock-On Boca
                            if z_coord <= Z_UMBRAL_LOCKON and abs(ex) <= TOLERANCIA_CENTRADO:
                                if not lockon_activado_boca:
                                    print("[CONTROL] Lock-On Boca ACTIVADO.")
                                    lockon_activado_boca = True

                        # --- CONDICIÓN DE PARADA FINAL ---
                        if z_coord <= Z_LIMITE_ENTREGA:
                            print(f"[ToF] POSICION DE ENTREGA ALCANZADA ({z_coord}mm).")
                            # Sonido de listo (macOS)
                            try:
                                subprocess.Popen(["afplay", "assets/ready.mp3"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            except:
                                pass
                            estado_actual = Estado.ESPERA_CONFIRMACION_ENTREGA
                            macro_movimiento_hecho = False

                        # --- EJECUCIÓN DE MOVIMIENTOS ---
                        if targets:
                            brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                            last_move_time = ahora
                
                else:
                    # LÓGICA DE SONDEO / RECUPERACIÓN (Si perdemos la boca)
                    buffer_ex.clear()
                    buffer_ey.clear()
                    contador_sondeo += 1
                    
                    if contador_sondeo < 30: 
                        # --- RECUPERACIÓN HACIA ARRIBA ---
                        if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                            nuevo_s7 = max(0, brazo.estado_actual[PIN_MUÑECA] - 2)
                            brazo.mover_tiempo([(PIN_MUÑECA, nuevo_s7)], esperar=False)
                            last_move_time = ahora
                        cv2.putText(frame_vis, "RECUPERANDO (MIRANDO ARRIBA)...", (10, 60), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
                    elif contador_sondeo < 100:
                        # Sondeo lateral oscilante (S0)
                        if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                            offset = int(8 * np.sin(contador_sondeo * 0.15))
                            brazo.mover_tiempo([(PIN_BASE, POSICIONES["OBSERVACION_MANIQUI"][0][1] + offset)], esperar=False)
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
                brazo.mover_tiempo([(PIN_PINZA, 80)]) # Abrir a 80
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

            # Visualización de Velocidad y Alerta de Seguridad
            v_abs = abs(velocidad_z)
            en_riesgo = z_coord < DISTANCIA_SEGURIDAD and v_abs > VELOCIDAD_LIMITE
            color_v = (0, 0, 255) if en_riesgo else (255, 255, 255)
            
            cv2.putText(frame_vis, f"VELOCIDAD: {v_abs:.1f} mm/s", (10, 60), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_v, 2)
            
            if en_riesgo:
                cv2.putText(frame_vis, "!!! EXCESO DE VELOCIDAD EN ZONA CRITICA !!!", (10, 85), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            
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
