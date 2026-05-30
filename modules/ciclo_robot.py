import threading
import time
import cv2
import numpy as np
import pygame

try:
    from utils.flujo_camara import CameraSerial
    from modules.arm_controller import ArmController
    from modules.pastillas_detector import process_pastillas_frame, verify_pill_in_gripper
    from modules.detectarColor import process_color_frame
    from modules.detectorBoca import get_mouth_coordinates
    from modules.auto_exposure import AutoExposureControl
    from constants.posiciones import POSICIONES
    from modules.mag_logger import log_mag_data
    from constants.config import (
        BOCA_OFFSET_X, BOCA_OFFSET_Y, BOCA_COMP_FACTOR,
        OFFSET_ALINEACION_X, OFFSET_ALINEACION_Y,
        PIN_BASE, PIN_HOMBRO, PIN_CODO, PIN_MUÑECA, PIN_ROTADOR, PIN_PINZA
    )
    _HARDWARE_DISPONIBLE = True
except ImportError:
    print("[Aviso] Módulos de hardware no encontrados. Ejecutando en modo SIMULACIÓN.")
    _HARDWARE_DISPONIBLE = False

class Estado:
    HOME = "HOME"
    OBSERVACION = "OBSERVACION"
    RECOLECCION = "RECOLECCION"
    ESPERA_CONFIRMACION_AGARRE = "ESPERA_CONFIRMACION_AGARRE"
    OBSERVACION_MANIQUI = "OBSERVACION_MANIQUI"
    SEGUIMIENTO_BOCA = "SEGUIMIENTO_BOCA"
    ESPERA_CONFIRMACION_ENTREGA = "ESPERA_CONFIRMACION_ENTREGA"
    ENTREGA = "ENTREGA"
    EMERGENCIA = "EMERGENCIA"
    FINALIZADO = "FINALIZADO"
    REINTENTO_OBJETO = "REINTENTO_OBJETO"
    CALIBRAR = "CALIBRAR"

class CicloRobot(threading.Thread):
    def __init__(self, color_objetivo="Azul", callback_datos=None):
        super().__init__()
        self.color_objetivo = color_objetivo
        self.callback_datos = callback_datos
        self._running = True
        self.daemon = True
        
        self.last_frame = None
        self.frame_lock = threading.Lock()

    def reportar(self, estado, pinza="---"):
        if self.callback_datos:
            self.callback_datos({"estado": estado, "pinza": pinza})

    def get_latest_frame(self):
        with self.frame_lock:
            return self.last_frame.copy() if self.last_frame is not None else None

    # =========================================================
    # --- FUNCIONES DE PAUSA ACTIVA ---
    # =========================================================
    def pausa_activa(self, duracion, camara):
        inicio = time.time()
        while time.time() - inicio < duracion and self._running:
            frame = camara.get_frame()
            if frame is not None:
                with self.frame_lock:
                    self.last_frame = frame.copy()
            time.sleep(0.02)

    def mover_y_esperar(self, brazo, camara, cmds=None, estado=None, forzar=False):
        if cmds:
            brazo.mover_tiempo(cmds, forzar=forzar, esperar=False)
        elif estado:
            brazo.mover_a_estado(estado, forzar=forzar, esperar=False)
        
        inicio = time.time()
        while not brazo.event_ok.is_set() and (time.time() - inicio < 8.0) and self._running:
            frame = camara.get_frame()
            if frame is not None:
                with self.frame_lock:
                    self.last_frame = frame.copy()
            time.sleep(0.02)

    def run(self):
        if not _HARDWARE_DISPONIBLE: 
            self.reportar("ERROR_HARDWARE", "DESCONOCIDO")
            return

        try:
            pygame.mixer.init()
        except:
            pass

        try:
            camara = CameraSerial(baud_rate=460800)
            brazo = ArmController(baudios=115200)
            auto_exp = AutoExposureControl(target_brightness=130)
            self.mover_y_esperar(brazo, camara, estado="HOME", forzar=True)
        except Exception as e:
            self.reportar(f"ERROR_HARDWARE: {str(e)}", "ERROR")
            return

        estado_actual = Estado.HOME
        estado_previo_caida = Estado.HOME
        macro_movimiento_hecho = False
        modo_seguro = False  
        
        camara_activa = True
        
        Z_UMBRAL_LOCKON = 135    
        Z_LIMITE_FINAL = 89  
        Z_LIMITE_ENTREGA = 185  
        TOLERANCIA_CENTRADO = 12 
        lockon_activado = False  
        lockon_activado_boca = False
        
        contador_pastilla_perdida = 0
        recuperacion_pastilla_intentada = False
        contador_sondeo = 0
        contador_sondeo_color = 0
        fase_sondeo_color = "IZQUIERDA" if self.color_objetivo.lower() == "verde" else "DERECHA"

        pastilla_en_transporte = False
        contador_caida = 0
        UMBRAL_PERSISTENCIA_CAIDA = 15 
        
        last_move_time = 0
        INTERVALO_MOVIMIENTO = 0.2 

        persistencia_deteccion = 0
        UMBRAL_PERSISTENCIA_DETECCION = 5 
        
        buffer_ex = []
        buffer_ey = []
        BUFFER_SIZE = 10
        
        last_z = 0
        last_z_time = time.time()
        velocidad_z = 0.0
        VELOCIDAD_LIMITE = 250.0 
        DISTANCIA_SEGURIDAD = 300.0 

        # Nueva variable para la cuenta regresiva
        tiempo_inicio_entrega = 0

        # =========================================================
        # --- CALIBRACIÓN INICIAL DE VACÍO ---
        # =========================================================
        self.reportar("CALIBRANDO", "INICIALIZANDO...")
        self.mover_y_esperar(brazo, camara, cmds=[(PIN_PINZA, 0)], forzar=True)
        self.pausa_activa(1.0, camara)
        
        m_vacio_home = brazo.mag1
        brazo.evaluador_agarre.registrar_vacio(m_vacio_home[0], m_vacio_home[1], m_vacio_home[2], estado="HOME")
        
        self.reportar("CALIBRANDO PINZA", "EN ALTURA...")
        self.mover_y_esperar(brazo, camara, estado="PRE_RECOLECCION")
        self.pausa_activa(1.0, camara)

        m_vacio_pre = brazo.mag1
        brazo.evaluador_agarre.registrar_vacio(m_vacio_pre[0], m_vacio_pre[1], m_vacio_pre[2], estado="PRE_RECOLECCION")
        
        self.mover_y_esperar(brazo, camara, cmds=[(PIN_PINZA, 80)], forzar=True)

        try:
            while self._running:
                ahora = time.time()

                if camara_activa:
                    frame = camara.get_frame()
                    if frame is None:
                        time.sleep(0.02)
                        continue
                    frame_vis = frame.copy()
                else:
                    frame_vis = np.zeros((360, 640, 3), dtype=np.uint8)
                    cv2.putText(frame_vis, "CAMARA APAGADA (MOVIMIENTO)", (100, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                    frame = None

                dist_actual = brazo.obtener_distancia()
                z_coord = dist_actual

                dt = ahora - last_z_time
                if dt >= 0.05: 
                    velocidad_z = (last_z - dist_actual) / dt
                    last_z = dist_actual
                    last_z_time = ahora
                
                # --- EMERGENCIAS Y COLISIONES ---
                if brazo.en_emergencia and estado_actual != Estado.EMERGENCIA:
                    estado_actual = Estado.EMERGENCIA
                    macro_movimiento_hecho = False
                    modo_seguro = True
                    self.mover_y_esperar(brazo, camara, cmds=[(PIN_PINZA, 80)], forzar=True)
                    self.mover_y_esperar(brazo, camara, estado="HOME", forzar=True)

                if estado_actual == Estado.SEGUIMIENTO_BOCA and brazo.colision_detectada and estado_actual != Estado.EMERGENCIA:
                    estado_actual = Estado.EMERGENCIA
                    macro_movimiento_hecho = False
                    modo_seguro = True
                    self.mover_y_esperar(brazo, camara, cmds=[(PIN_PINZA, 80)], forzar=True)
                    self.mover_y_esperar(brazo, camara, estado="HOME", forzar=True)

                if estado_actual in [Estado.OBSERVACION_MANIQUI, Estado.SEGUIMIENTO_BOCA, Estado.ESPERA_CONFIRMACION_ENTREGA]:
                    if brazo.estado_pinza == "VACIA" and pastilla_en_transporte and not brazo.busy:
                        contador_caida += 1
                        if contador_caida >= UMBRAL_PERSISTENCIA_CAIDA:
                            estado_previo_caida = estado_actual
                            estado_actual = Estado.REINTENTO_OBJETO
                            macro_movimiento_hecho = False
                            contador_caida = 0
                    else:
                        contador_caida = 0 

                # Reporte por defecto, puede ser sobreescrito más abajo
                self.reportar(estado_actual, brazo.estado_pinza)
                
                # =================================================
                # --- MÁQUINA DE ESTADOS AUTOMATIZADA ---
                # =================================================

                if estado_actual == Estado.HOME:
                    lockon_activado = False
                    pastilla_en_transporte = False
                    camara_activa = False 
                    brazo.evaluador_agarre.hubo_colision = False 
                    brazo.evaluador_agarre.monitoreo_activo = False 
                    
                    if not macro_movimiento_hecho:
                        self.mover_y_esperar(brazo, camara, estado="HOME", forzar=True)
                        self.pausa_activa(0.5, camara)
                        macro_movimiento_hecho = True
                    
                    if not modo_seguro:
                        estado_actual = Estado.OBSERVACION
                        macro_movimiento_hecho = False
                    else:
                        if frame_vis is not None:
                            cv2.putText(frame_vis, "HOME SEGURO - PARO / COLISION DETECTADO", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

                elif estado_actual == Estado.OBSERVACION:
                    if not macro_movimiento_hecho:
                        self.mover_y_esperar(brazo, camara, estado="OBSERVACION", forzar=True)
                        self.pausa_activa(1.0, camara)
                        camara_activa = True 
                        macro_movimiento_hecho = True
                    
                    if frame is None: continue

                    auto_exp.update(frame, camara)
                    frame_vis, colores, info_colores = process_color_frame(frame_vis)
                    
                    if self.color_objetivo in colores:
                        estado_actual = Estado.RECOLECCION
                        macro_movimiento_hecho = False
                        contador_sondeo_color = 0
                        lockon_activado = False
                        buffer_ex.clear()
                        buffer_ey.clear()
                        persistencia_deteccion = 0
                    else:
                        cv2.putText(frame_vis, f"Sondeando {self.color_objetivo} ({fase_sondeo_color})...", (10, 60), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                        
                        ang_base = brazo.estado_actual.get(PIN_BASE, 90)
                        if fase_sondeo_color == "DERECHA":
                            if ang_base > 40:
                                if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                                    brazo.mover_tiempo([(PIN_BASE, ang_base - 1)], esperar=False)
                                    last_move_time = ahora
                            else:
                                fase_sondeo_color = "IZQUIERDA"
                        elif fase_sondeo_color == "IZQUIERDA":
                            if ang_base < 140:
                                if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                                    brazo.mover_tiempo([(PIN_BASE, ang_base + 1)], esperar=False)
                                    last_move_time = ahora
                            else:
                                fase_sondeo_color = "DERECHA"

                elif estado_actual == Estado.RECOLECCION:
                    if frame is None: continue
                    
                    ex, ey = 0, 0
                    targets = {}
                    
                    auto_exp.update(frame, camara)
                    frame_vis, info = process_pastillas_frame(frame_vis, self.color_objetivo.lower())

                    colores_backup = []
                    if not info and not lockon_activado:
                        _, colores_backup, info_colores_backup = process_color_frame(frame.copy())
                    
                    ang_base = brazo.estado_actual.get(PIN_BASE, 90)
                    ang_hombro = brazo.estado_actual.get(PIN_HOMBRO, 180)
                    ang_codo = brazo.estado_actual.get(PIN_CODO, 140)
                    ang_muneca = brazo.estado_actual.get(PIN_MUÑECA, 90)

                    if info or lockon_activado:
                        if info:
                            ex_curr, ey_curr, area = info
                            buffer_ex.append(ex_curr)
                            buffer_ey.append(ey_curr)
                            persistencia_deteccion += 1
                        
                        if not lockon_activado and persistencia_deteccion < UMBRAL_PERSISTENCIA_DETECCION:
                            cv2.putText(frame_vis, f"FILTRANDO RUIDO ({persistencia_deteccion}/{UMBRAL_PERSISTENCIA_DETECCION})", (10, 60), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                        else:
                            ready_to_move = lockon_activado or len(buffer_ex) >= BUFFER_SIZE
                            
                            if ready_to_move:
                                if not lockon_activado and buffer_ex:
                                    ex = sum(buffer_ex) / len(buffer_ex)
                                    ey = sum(buffer_ey) / len(buffer_ey)
                                    buffer_ex.clear()
                                    buffer_ey.clear()
                                else:
                                    ex, ey = 0, 0 

                                if not lockon_activado:
                                    if abs(ex) > TOLERANCIA_CENTRADO:
                                        paso_x = 1 if abs(ex) > 10 else 0.5
                                        targets[PIN_BASE] = ang_base + (-1 if ex > 0 else 1)

                                    can_move_vertical = abs(ex) < (40 if z_coord < 130 else 70)
                                    
                                    if can_move_vertical:
                                        if abs(ey) > 10:
                                            if ey > 0: 
                                                if ang_muneca < 180: targets[PIN_MUÑECA] = ang_muneca + 1
                                                else: targets[PIN_CODO] = ang_codo + 1
                                            else:      
                                                if ang_muneca > 10: targets[PIN_MUÑECA] = ang_muneca - 1
                                                else: targets[PIN_CODO] = max(20, ang_codo - 1)

                                if z_coord > Z_UMBRAL_LOCKON:
                                    if abs(ex) < 85 and abs(ey) < 85:
                                        targets[PIN_HOMBRO] = max(5, ang_hombro - 1)
                                        if PIN_CODO not in targets: targets[PIN_CODO] = max(5, ang_codo - 1)
                                
                                elif z_coord > Z_LIMITE_FINAL:
                                    if abs(ex) <= TOLERANCIA_CENTRADO and abs(ey) <= TOLERANCIA_CENTRADO:
                                        if not lockon_activado:
                                            lockon_activado = True

                                    if lockon_activado:
                                        targets[PIN_HOMBRO] = max(59, ang_hombro - 1)
                                        if ang_muneca > 20:
                                            targets[PIN_MUÑECA] = ang_muneca - 1
                                        cv2.putText(frame_vis, "LOCK-ON: DESCENSO GRADUAL...", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                                if ang_hombro <= 59 or z_coord <= Z_LIMITE_FINAL:
                                    self.mover_y_esperar(brazo, camara, cmds=[
                                        (PIN_BASE, ang_base), (PIN_HOMBRO, ang_hombro),
                                        (PIN_CODO, ang_codo), (PIN_MUÑECA, ang_muneca)
                                    ], forzar=True)

                                    estado_actual = Estado.ESPERA_CONFIRMACION_AGARRE
                                    macro_movimiento_hecho = False

                                if targets:
                                    if lockon_activado:
                                        if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                                            brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                                            last_move_time = ahora
                                    else:
                                        brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                                        last_move_time = ahora

                        contador_pastilla_perdida = 0
                        recuperacion_pastilla_intentada = False
                    
                    elif self.color_objetivo in colores_backup:
                        cx, cy = info_colores_backup[self.color_objetivo]
                        ex_b = cx - (frame_vis.shape[1] // 2)
                        ey_b = cy - (frame_vis.shape[0] // 2)
                        targets = {}
                        if abs(ex_b) > 20:
                            targets[PIN_BASE] = ang_base + (-2 if ex_b > 0 else 2)
                        if abs(ey_b) > 20:
                            targets[PIN_MUÑECA] = ang_muneca + (1 if ey_b > 0 else -1)
                        if targets and (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                            brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                            last_move_time = ahora
                        cv2.putText(frame_vis, f"Aproximando a {self.color_objetivo}...", (10, 60), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
                    else:
                        persistencia_deteccion = 0
                        buffer_ex.clear()
                        buffer_ey.clear()
                        contador_pastilla_perdida += 1
                        
                        if contador_pastilla_perdida == 25 and not recuperacion_pastilla_intentada:
                            nuevo_s1 = min(110, ang_hombro + 15)
                            nuevo_s15 = max(20, ang_muneca - 15)
                            self.mover_y_esperar(brazo, camara, cmds=[(PIN_HOMBRO, nuevo_s1), (PIN_MUÑECA, nuevo_s15)])
                            recuperacion_pastilla_intentada = True
                        
                        elif contador_pastilla_perdida > 80:
                            estado_actual = Estado.OBSERVACION
                            macro_movimiento_hecho = False
                            contador_pastilla_perdida = 0
                            recuperacion_pastilla_intentada = False

                elif estado_actual == Estado.ESPERA_CONFIRMACION_AGARRE:
                    cv2.putText(frame_vis, "PREPARANDO AGARRE... ESPERE", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                    with self.frame_lock: self.last_frame = frame_vis
                    
                    self.pausa_activa(1.0, camara)
                    nuevo_s7 = max(0, brazo.estado_actual.get(PIN_MUÑECA, 90) - 0)
                    self.mover_y_esperar(brazo, camara, cmds=[(PIN_MUÑECA, nuevo_s7)])
                    
                    self.pausa_activa(2.0, camara)
                    self.mover_y_esperar(brazo, camara, cmds=[(PIN_PINZA, 0)], forzar=True)
                    self.pausa_activa(0.5, camara)
                    
                    m_init = brazo.mag1
                    brazo.evaluador_agarre.capturar_baseline(m_init[0], m_init[1], m_init[2])
                    
                    self.mover_y_esperar(brazo, camara, estado="PRE_RECOLECCION")
                    self.pausa_activa(1.0, camara)
                    
                    m1 = brazo.mag1
                    exito_real = brazo.evaluador_agarre.verificar_presencia_real(m1[0], m1[1], m1[2], estado="PRE_RECOLECCION")
                    confirmacion_visual = verify_pill_in_gripper(frame) if frame is not None else False
                    
                    if (exito_real and confirmacion_visual) or (exito_real and brazo.evaluador_agarre.verificar_presencia_real(m1[0], m1[1], m1[2], estado="PRE_RECOLECCION")):
                        norma_actual = (m1[0]**2 + m1[1]**2 + m1[2]**2)**0.5
                        ref_vacio = brazo.evaluador_agarre.baselines_vacio.get("PRE_RECOLECCION", 0)
                        delta_final = abs(norma_actual - ref_vacio)

                        if delta_final > 400:
                            if confirmacion_visual:
                                pastilla_en_transporte = True
                                estado_actual = Estado.CALIBRAR
                            else:
                                pastilla_en_transporte = False
                                self.mover_y_esperar(brazo, camara, cmds=[(PIN_PINZA, 80)])
                                estado_actual = Estado.OBSERVACION
                        elif delta_final > 60 or (delta_final > 25 and confirmacion_visual):
                            pastilla_en_transporte = True
                            estado_actual = Estado.CALIBRAR 
                            log_mag_data(m1[0], m1[1], m1[2], "CON_OBJETO")
                        else:
                            pastilla_en_transporte = False
                            self.mover_y_esperar(brazo, camara, cmds=[(PIN_PINZA, 80)])
                            estado_actual = Estado.OBSERVACION
                    else:
                        pastilla_en_transporte = False
                        self.mover_y_esperar(brazo, camara, cmds=[(PIN_PINZA, 80)])
                        estado_actual = Estado.OBSERVACION
                        log_mag_data(m1[0], m1[1], m1[2], "VACIO_CERRADO")
                    
                    macro_movimiento_hecho = False

                elif estado_actual == Estado.CALIBRAR:
                    cv2.putText(frame_vis, "CALIBRANDO MAGNETOMETRO...", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
                    with self.frame_lock: self.last_frame = frame_vis
                    
                    self.pausa_activa(1.5, camara)
                    estado_actual = Estado.OBSERVACION_MANIQUI
                    macro_movimiento_hecho = False

                elif estado_actual == Estado.OBSERVACION_MANIQUI:
                    if not macro_movimiento_hecho:
                        camara_activa = False 
                        self.mover_y_esperar(brazo, camara, estado="OBSERVACION_MANIQUI", forzar=True)
                        self.pausa_activa(0.5, camara)
                        camara_activa = True
                        macro_movimiento_hecho = True
                        lockon_activado_boca = False
                        buffer_ex.clear()
                        buffer_ey.clear()
                    
                    if frame is None: continue

                    auto_exp.update(frame, camara)
                    frame_vis = frame.copy()
                    cv_h, cv_w = frame_vis.shape[:2]
                    cv2.drawMarker(frame_vis, (cv_w // 2, cv_h // 2), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)
                    
                    frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                    if coords_boca:
                        brazo.evaluador_agarre.reset() 
                        brazo.evaluador_agarre.monitoreo_activo = True 
                        estado_actual = Estado.SEGUIMIENTO_BOCA
                        macro_movimiento_hecho = False
                    else:
                        cv2.putText(frame_vis, "Buscando boca...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

                elif estado_actual == Estado.SEGUIMIENTO_BOCA:
                    if frame is None: continue

                    targets = {}
                    frame_vis = frame.copy()
                    cv_h, cv_w = frame_vis.shape[:2]
                    cv2.drawMarker(frame_vis, (cv_w // 2, cv_h // 2), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)
                    
                    auto_exp.update(frame, camara)
                    frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                    
                    ang_base = brazo.estado_actual.get(PIN_BASE, 90)
                    ang_hombro = brazo.estado_actual.get(PIN_HOMBRO, 180)
                    ang_codo = brazo.estado_actual.get(PIN_CODO, 140)
                    ang_muneca = brazo.estado_actual.get(PIN_MUÑECA, 90)

                    if coords_boca:
                        ex_boca = coords_boca[0] - (frame_vis.shape[1] // 2) + BOCA_OFFSET_X
                        ey_raw_boca = coords_boca[1] - (frame_vis.shape[0] // 2) + BOCA_OFFSET_Y
                        
                        buffer_ex.append(ex_boca)
                        buffer_ey.append(ey_raw_boca)
                        
                        ready_to_move = lockon_activado_boca or len(buffer_ex) >= BUFFER_SIZE
                        
                        if ready_to_move:
                            contador_sondeo = 0
                            if not lockon_activado_boca and buffer_ex:
                                ex = sum(buffer_ex) / len(buffer_ex)
                                ey_raw = sum(buffer_ey) / len(buffer_ey)
                                buffer_ex.clear()
                                buffer_ey.clear()
                            else:
                                ex, ey_raw = 0, 0 

                            dist_factor = max(0, Z_UMBRAL_LOCKON - z_coord)
                            ey = ey_raw + int(dist_factor * BOCA_COMP_FACTOR) 

                            if not lockon_activado_boca:
                                if abs(ex) > 8:
                                    paso_x = 3 if abs(ex) > 60 else 2
                                    targets[PIN_BASE] = ang_base + (-paso_x if ex > 0 else paso_x)
                                
                                if abs(ey) > 10:
                                    targets[PIN_MUÑECA] = ang_muneca + (1 if ey > 0 else -1)
                                    if abs(ey) > 30:
                                        targets[PIN_CODO] = ang_codo + (1 if ey > 0 else -1)

                            if z_coord > Z_LIMITE_ENTREGA:
                                if ang_hombro > 70:
                                    targets[PIN_HOMBRO] = ang_hombro - 1
                                
                                if PIN_CODO not in targets and ang_codo > 0:
                                    targets[PIN_CODO] = ang_codo - 1
                                
                                if z_coord <= Z_UMBRAL_LOCKON and abs(ex) <= TOLERANCIA_CENTRADO:
                                    if not lockon_activado_boca:
                                        lockon_activado_boca = True

                            if z_coord <= Z_LIMITE_ENTREGA:
                                try:
                                    pygame.mixer.music.load("assets/ready.mp3")
                                    pygame.mixer.music.play()
                                except: pass
                                
                                estado_actual = Estado.ESPERA_CONFIRMACION_ENTREGA
                                macro_movimiento_hecho = False

                            if targets and (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                                brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                                last_move_time = ahora
                    else:
                        buffer_ex.clear()
                        buffer_ey.clear()
                        contador_sondeo += 1
                        
                        if contador_sondeo < 30: 
                            if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                                brazo.mover_tiempo([(PIN_MUÑECA, max(0, ang_muneca - 2))], esperar=False)
                                last_move_time = ahora
                            cv2.putText(frame_vis, "RECUPERANDO (MIRANDO ARRIBA)...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                        elif contador_sondeo < 100:
                            if (ahora - last_move_time) > INTERVALO_MOVIMIENTO:
                                offset = int(8 * np.sin(contador_sondeo * 0.15))
                                base_boca = POSICIONES["OBSERVACION_MANIQUI"][0][1]
                                brazo.mover_tiempo([(PIN_BASE, base_boca + offset)], esperar=False)
                                last_move_time = ahora
                            cv2.putText(frame_vis, "SONDEO DE BOCA...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                        else:
                            estado_actual = Estado.OBSERVACION_MANIQUI
                            macro_movimiento_hecho = False
                            contador_sondeo = 0

                # ==========================================================
                # NUEVO: CUENTA REGRESIVA DE 5 SEGUNDOS PARA ENTREGA
                # ==========================================================
                elif estado_actual == Estado.ESPERA_CONFIRMACION_ENTREGA:
                    if not macro_movimiento_hecho:
                        tiempo_inicio_entrega = ahora
                        macro_movimiento_hecho = True
                    
                    tiempo_restante = 5 - int(ahora - tiempo_inicio_entrega)
                    
                    if tiempo_restante > 0:
                        self.reportar(f"SOLTANDO EN {tiempo_restante}s", brazo.estado_pinza)
                        cv2.putText(frame_vis, f"ABRIENDO PINZA EN {tiempo_restante}s...", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    else:
                        m1 = brazo.mag1
                        try: log_mag_data(m1[0], m1[1], m1[2], "EXITO_ENTREGA")
                        except: pass
                        estado_actual = Estado.ENTREGA
                        macro_movimiento_hecho = False

                elif estado_actual == Estado.ENTREGA:
                    self.reportar("ENTREGANDO...", brazo.estado_pinza)
                    brazo.evaluador_agarre.monitoreo_activo = False 
                    self.mover_y_esperar(brazo, camara, cmds=[(PIN_PINZA, 80)])
                    self.pausa_activa(1.0, camara)
                    estado_actual = Estado.HOME
                    macro_movimiento_hecho = False

                elif estado_actual == Estado.EMERGENCIA:
                    cv2.rectangle(frame_vis, (0, 0), (frame_vis.shape[1], frame_vis.shape[0]), (0, 0, 150), 10)
                    cv2.putText(frame_vis, "!!! PARO DE EMERGENCIA !!!", (50, 150), cv2.FONT_HERSHEY_DUPLEX, 1.2, (0, 0, 255), 3)
                    
                    if not brazo.en_emergencia:
                        estado_actual = Estado.HOME
                        macro_movimiento_hecho = False

                elif estado_actual == Estado.REINTENTO_OBJETO:
                    cv2.rectangle(frame_vis, (0, 0), (frame_vis.shape[1], frame_vis.shape[0]), (0, 165, 255), 8)
                    cv2.putText(frame_vis, "ALERTA: OBJETO NO DETECTADO", (50, 150), cv2.FONT_HERSHEY_DUPLEX, 1.0, (0, 165, 255), 2)
                    with self.frame_lock: self.last_frame = frame_vis
                    
                    self.pausa_activa(2.0, camara)
                    brazo.evaluador_agarre.monitoreo_activo = False 
                    estado_actual = Estado.HOME
                    macro_movimiento_hecho = False

                # --- DIBUJAR INFORMACIÓN GLOBAL ---
                if frame_vis is not None:
                    umbral_actual = Z_LIMITE_ENTREGA if "BOCA" in estado_actual or "ENTREGA" in estado_actual or "MANIQUI" in estado_actual else Z_LIMITE_FINAL
                    color_z = (0, 255, 0) if z_coord <= umbral_actual else (0, 255, 255)
                    cv2.putText(frame_vis, f"COORD Z (ToF): {z_coord}mm", (10, 30), cv2.FONT_HERSHEY_DUPLEX, 0.8, color_z, 2)

                    v_abs = abs(velocidad_z)
                    en_riesgo = z_coord < DISTANCIA_SEGURIDAD and v_abs > VELOCIDAD_LIMITE
                    color_v = (0, 0, 255) if en_riesgo else (255, 255, 255)
                    
                    cv2.putText(frame_vis, f"VELOCIDAD: {v_abs:.1f} mm/s", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_v, 2)
                    if en_riesgo:
                        cv2.putText(frame_vis, "!!! EXCESO DE VELOCIDAD EN ZONA CRITICA !!!", (10, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                    
                    m1 = brazo.mag1
                    est_p = brazo.estado_pinza
                    col_p = (0, 255, 0) if est_p == "CON_OBJETO" else (0, 255, 255) if est_p == "ABIERTA" else (0, 0, 255)
                    
                    texto_mag_vals = f"MAG RAW -> X: {m1[0]:.1f} Y: {m1[1]:.1f} Z: {m1[2]:.1f}"
                    
                    cv2.putText(frame_vis, texto_mag_vals, (10, frame_vis.shape[0] - 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    cv2.putText(frame_vis, f"ESTADO PINZA: {est_p}", (10, frame_vis.shape[0] - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col_p, 2)
                    cv2.putText(frame_vis, f"ESTADO CICLO: {estado_actual}", (10, frame_vis.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    
                    with self.frame_lock:
                        self.last_frame = frame_vis

                time.sleep(0.01)

        finally:
            # FIX DE PYTHON: Evaluamos correctamente la existencia de 'brazo' en la memoria local
            if 'brazo' in locals() and brazo is not None:
                try:
                    brazo.mover_a_estado("HOME", forzar=True, esperar=True) 
                    time.sleep(1.0)
                    brazo.cerrar()
                except Exception as e: pass
            
            if 'camara' in locals() and camara is not None:
                try: camara.liberar()
                except: pass

    def stop(self):
        self._running = False