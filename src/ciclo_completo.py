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

# ... (rest of imports)

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
from modules.mag_logger import log_mag_data, ask_user_success # Importar logger

# Cargar variables de entorno
load_dotenv()

# ===============================================================
# --- CONFIGURACIÓN PRINCIPAL ---
# ===============================================================
PUERTO_CAMARA = os.getenv('PUERTO_CAMARA', '/dev/ttyUSB1')
PUERTO_BRAZO = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
COLOR_OBJETIVO = "Azul" 

from constants.config import OFFSET_X, OFFSET_Y

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
    print("--- INICIANDO CICLO COMPLETO (AUTOMÁTICO) ---")
    
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
    
    print("Sistema listo. Parpadea 2 veces para iniciar el ciclo.")

    try:
        while True:
            frame = camara.get_frame()
            if frame is None: continue

            # Actualizar z_coord al inicio
            dist_actual = brazo.obtener_distancia()
            z_coord = dist_actual

            frame_vis = frame.copy()
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break

            # --- DETECCIÓN DE EMERGENCIA ---
            if brazo.en_emergencia and estado_actual != Estado.EMERGENCIA:
                print("[SISTEMA] Entrando en modo EMERGENCIA...")
                estado_actual = Estado.EMERGENCIA
                macro_movimiento_hecho = False

            # --- MONITOREO DE CAÍDA (Con filtro de persistencia) ---
            if pastilla_en_transporte:
                # Debug discreto cada 0.5s para monitorear el sensor en movimiento
                if time.time() % 0.5 < 0.05:
                    m = brazo.mag1
                    print(f"[DEBUG MAG] X:{m[0]:.1f} Y:{m[1]:.1f} | Pinza: {brazo.estado_pinza} | Filtro: {contador_caida}/{UMBRAL_PERSISTENCIA_CAIDA}")

                if brazo.estado_pinza == "VACIA":
                    contador_caida += 1
                    if contador_caida >= UMBRAL_PERSISTENCIA_CAIDA:
                        print("\n" + "!"*50)
                        print("!!! CONFIRMADO: LA PASTILLA SE HA CAÍDO !!!")
                        print("!"*50 + "\n")
                        pastilla_en_transporte = False
                        estado_actual = Estado.HOME
                        macro_movimiento_hecho = False
                        contador_caida = 0
                else:
                    contador_caida = 0 # Resetear si el sensor vuelve a detectar el objeto
            
            # =================================================
            # --- MÁQUINA DE ESTADOS ---
            # =================================================

            if estado_actual == Estado.HOME:
                lockon_activado = False
                pastilla_en_transporte = False
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
                    iniciar_deteccion_pastillas(camara) # Luz inicial
                    brazo.mover_a_estado("OBSERVACION")
                    time.sleep(2) 
                    macro_movimiento_hecho = True
                
                # Ajuste autónomo de luz
                auto_exp.update(frame, camara)
                
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
                        # Mover hacia la derecha hasta el límite (140 grados)
                        if brazo.estado_actual[0] < 140:
                            nuevo_s0 = brazo.estado_actual[0] + 1
                            brazo.mover_tiempo([(0, nuevo_s0)], esperar=False)
                        else:
                            # Límite izquierdo alcanzado, cambiar a derecha
                            print("[SONDEO] Límite derecho alcanzado. Cambiando a izquierda.")
                            fase_sondeo_color = "IZQUIERDA"
                    
                    elif fase_sondeo_color == "IZQUIERDA":
                        # Mover hacia la izquierda hasta el límite (40 grados)
                        if brazo.estado_actual[0] > 40:
                            nuevo_s0 = brazo.estado_actual[0] - 1
                            brazo.mover_tiempo([(0, nuevo_s0)], esperar=False)
                        else:
                            # Límite derecho alcanzado, reiniciar a izquierda
                            print("[SONDEO] Límite izquierdo alcanzado. Reiniciando sondeo.")
                            fase_sondeo_color = "DERECHA"

            elif estado_actual == Estado.RECOLECCION:
                # Ajuste autónomo constante durante la recolección
                auto_exp.update(frame, camara)
                
                # Intentar segmentación fina de la pastilla
                frame_vis, info = process_pastillas_frame(frame_vis, COLOR_OBJETIVO.lower())
                
                # Obtener detección de color como respaldo
                _, colores_backup, info_colores_backup = process_color_frame(frame.copy())
                
                if info or lockon_activado:
                    ex, ey, area = info if info else (0, 0, 0)
                    targets = {} 
                    
                    if not lockon_activado:
                        # --- PRIORIDAD X (Eje S0) ---
                        if abs(ex) > TOLERANCIA_CENTRADO:
                            # Paso agresivo si el error es grande (>40px)
                            paso_x = 1 if abs(ex) > 10 else 0.5
                            targets[0] = brazo.estado_actual[0] + (paso_x if ex > 0 else -paso_x)
                        
                        # --- EJE Y (S15 + S6) ---
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
                        FINAL_CORRECTION_S15 = 3 # Grados extra para centrar Y (hacia arriba)

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
                        targets[0] = brazo.estado_actual[0] + (1 if ex_b > 0 else -1)
                    if abs(ey_b) > 20:
                        targets[15] = brazo.estado_actual[15] + (1 if ey_b > 0 else -1)
                    
                    if targets:
                        brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                    
                    cv2.putText(frame_vis, f"Aproximando a {COLOR_OBJETIVO}...", (10, 60), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                else:
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
                cv2.putText(frame_vis, "VERIFICANDO AGARRE AUTOMATICO...", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                
                # Ejecutar maniobra de cierre y levantamiento
                print("\n[CONTROL] Cerrando pinza...")
                brazo.mover_tiempo([(12, 0)], forzar=True, esperar=True) 
                time.sleep(1.0)
                
                print("[CONTROL] Levantando para validar con magnetometro...")
                brazo.mover_a_estado("PRE_RECOLECCION", esperar=True)
                time.sleep(1.2) # Tiempo extra para estabilizar lectura
                
                # DECISIÓN AUTÓNOMA BASADA EN MAGNETÓMETRO
                m1 = brazo.mag1
                if brazo.estado_pinza == "CON_OBJETO":
                    print(f"[¡ÉXITO!] Pastilla detectada (X: {m1[0]}). Guardando log y procediendo a entrega.")
                    log_mag_data(m1[0], m1[1], m1[2], "HOLDING_TRACK")
                    pastilla_en_transporte = True
                    estado_actual = Estado.OBSERVACION_MANIQUI
                else:
                    print(f"[FALLO] Pinza vacia o agarre debil (X: {m1[0]}). Reintentando ciclo...")
                    log_mag_data(m1[0], m1[1], m1[2], "AUTO_RETRY_EMPTY")
                    pastilla_en_transporte = False
                    brazo.mover_tiempo([(12, 80)], esperar=True) # Abrir
                    estado_actual = Estado.OBSERVACION
                
                macro_movimiento_hecho = False

            elif estado_actual == Estado.OBSERVACION_MANIQUI:
                if not macro_movimiento_hecho:
                    print("[CONTROL] Yendo a posición de entrega (Maniquí)...")
                    iniciar_deteccion(camara)
                    # Forzar movimiento completo con espera
                    brazo.mover_a_estado("OBSERVACION_MANIQUI", forzar=True, esperar=True)
                    time.sleep(0.5)
                    macro_movimiento_hecho = True
                    lockon_activado_boca = False
                
                # Ajuste autónomo de luz para la boca
                auto_exp.update(frame, camara)

                # Rotar frame para el maniquí
                frame_rotated = cv2.rotate(frame, cv2.ROTATE_180)
                frame_vis = frame_rotated.copy()
                
                # Centro objetivo visual (Punto azul)
                cv_h, cv_w = frame_vis.shape[:2]
                cv2.drawMarker(frame_vis, (cv_w // 2, cv_h // 2), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)
                
                frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                if coords_boca:
                    estado_actual = Estado.SEGUIMIENTO_BOCA
                    macro_movimiento_hecho = False
                else:
                    cv2.putText(frame_vis, "Buscando boca (Frame Rotado)...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

            elif estado_actual == Estado.SEGUIMIENTO_BOCA:
                # Ajuste autónomo continuo para la boca
                auto_exp.update(frame, camara)

                # Rotar frame para el maniquí
                frame_rotated = cv2.rotate(frame, cv2.ROTATE_180)
                frame_vis = frame_rotated.copy()
                
                # Centro objetivo visual (Punto azul)
                cv_h, cv_w = frame_vis.shape[:2]
                cv2.drawMarker(frame_vis, (cv_w // 2, cv_h // 2), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)
                
                frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                
                if coords_boca:
                    # Resetear contador de sondeo si vemos la boca
                    contador_sondeo = 0
                    
                    # Error con frame rotado
                    ex_raw = coords_boca[0] - (frame_vis.shape[1] // 2)
                    ey_raw = coords_boca[1] - (frame_vis.shape[0] // 2)
                    
                    # En OBSERVACION_MANIQUI S0 está cerca de 5. 
                    # Si el frame está rotado 180, la izquierda física es la derecha del frame.
                    # Para centrar, si ex_raw es positivo (derecha del frame/izquierda física), 
                    # debemos aumentar S0 para ir hacia la izquierda (asumiendo que S0 crece hacia la izquierda).
                    ex = ex_raw 
                    # S15: 0 mira hacia arriba, 180 hacia abajo.
                    # Si la boca está debajo del centro (ey_raw > 0), queremos bajar la cámara,
                    # por lo que S15 debe aumentar. Usamos ey_raw directo.
                    ey = ey_raw 
                    
                    targets = {} 
                    
                    if not lockon_activado_boca:
                        # Centrado Horizontal (S0)
                        if abs(ex) > 8:
                            paso_x = 2 if abs(ex) > 60 else 1
                            targets[0] = brazo.estado_actual[0] + (paso_x if ex > 0 else -paso_x)
                        
                        # Centrado Vertical Dinámico (S15 + S6)
                        if abs(ey) > 10:
                            # S15: Ajuste fino de inclinación
                            paso_y = 1
                            targets[15] = brazo.estado_actual[15] + (paso_y if ey > 0 else -paso_y)
                            
                            # S6: Compensación de altura del antebrazo (S6 aumenta para bajar)
                            # Solo corregimos con S6 si el error es significativo para no oscilar
                            if abs(ey) > 30:
                                targets[6] = brazo.estado_actual[6] + (1 if ey > 0 else -1)

                    # Lógica de ACERCAMIENTO COORDINADO (Extensión S1 + S6)
                    if z_coord > Z_LIMITE_ENTREGA:
                        # S1: Progresión constante hacia adelante
                        if brazo.estado_actual[1] > 70:
                            targets[1] = brazo.estado_actual[1] - 1
                        
                        # S6: Ayuda a la extensión solo si la boca está centrada verticalmente
                        # Si ey > 0 (boca abajo), detenemos la extensión de S6 para que el hombro S1 baje más
                        if 6 not in targets and brazo.estado_actual[6] > 0:
                            targets[6] = brazo.estado_actual[6] - 1
                        
                        if z_coord <= Z_UMBRAL_LOCKON and abs(ex) <= TOLERANCIA_CENTRADO:
                            if not lockon_activado_boca:
                                print("[CONTROL] Lock-On Boca ACTIVADO.")
                                lockon_activado_boca = True

                    # 3. Condición de Parada Final (150mm)
                    if z_coord <= Z_LIMITE_ENTREGA:
                        print(f"[ToF] POSICION DE ENTREGA ALCANZADA ({z_coord}mm).")
                        finalizar_deteccion(camara)
                        estado_actual = Estado.ESPERA_CONFIRMACION_ENTREGA
                        macro_movimiento_hecho = False

                    if targets:
                        brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                
                else:
                    # LÓGICA DE SONDEO (Si perdemos la boca)
                    contador_sondeo += 1
                    
                    if contador_sondeo < 100: # Dar más tiempo al sondeo lento
                        # Sondeo lateral oscilante (S0) más lento para evitar desenfoque
                        offset = 8 * np.sin(contador_sondeo * 0.15)
                        brazo.mover_tiempo([(0, POSICIONES["OBSERVACION_MANIQUI"][0][1] + offset)], esperar=False)
                        cv2.putText(frame_vis, "SONDEO DE BOCA...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    else:
                        print("[CONTROL] Boca perdida tras sondeo. Regresando a Observación.")
                        estado_actual = Estado.OBSERVACION_MANIQUI
                        macro_movimiento_hecho = False
                        contador_sondeo = 0

            elif estado_actual == Estado.ESPERA_CONFIRMACION_ENTREGA:
                # Mantener el frame rotado para consistencia visual
                frame_rotated = cv2.rotate(frame, cv2.ROTATE_180)
                frame_vis = frame_rotated.copy()
                
                cv2.putText(frame_vis, "ENTREGA LISTA - Confirma con 'c'", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                if key == ord('c'):
                    print("[CONTROL] Entrega confirmada. Soltando...")
                    estado_actual = Estado.ENTREGA
                    macro_movimiento_hecho = False

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
            if camara: camara.set_led_brightness(0)
            # Agregamos esperar=True para que el movimiento suave se complete antes de cerrar
            brazo.mover_a_estado("HOME", forzar=True, esperar=True)
            brazo.cerrar()
            camara.liberar()
        except: pass
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
