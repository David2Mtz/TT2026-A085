import threading
import time
import cv2
import numpy as np

try:
    from utils.flujo_camara import CameraSerial
    from modules.arm_controller import ArmController
    from modules.pastillas_detector import process_pastillas_frame, iniciar_deteccion as iniciar_det_pastilla, finalizar_deteccion as finalizar_det_pastilla
    from modules.detectarColor import process_color_frame
    from modules.detectorBoca import get_mouth_coordinates, iniciar_deteccion as iniciar_det_boca, finalizar_deteccion as finalizar_det_boca
    from modules.auto_exposure import AutoExposureControl
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

class CicloRobot(threading.Thread):
    def __init__(self, color_objetivo="Azul", callback_estado=None):
        super().__init__()
        self.color_objetivo = color_objetivo
        self.callback_estado = callback_estado
        self._running = True
        self.daemon = True
        
        self.last_frame = None
        self.frame_lock = threading.Lock()

    def reportar(self, estado):
        if self.callback_estado:
            self.callback_estado(estado)

    def get_latest_frame(self):
        with self.frame_lock:
            return self.last_frame.copy() if self.last_frame is not None else None

    def run(self):
        self.reportar("INICIANDO_SISTEMA")
        if not _HARDWARE_DISPONIBLE: return

        try:
            camara = CameraSerial(baud_rate=460800)
            brazo = ArmController(baudios=115200)
            auto_exp = AutoExposureControl(target_brightness=130)
            brazo.mover_a_estado("HOME", forzar=True, esperar=True)
        except Exception as e:
            self.reportar(f"ERROR_HARDWARE: {str(e)}")
            return

        estado_actual = Estado.OBSERVACION
        macro_movimiento_hecho = False
        
        Z_UMBRAL_LOCKON = 120    
        Z_LIMITE_FINAL = 90   
        Z_LIMITE_ENTREGA = 250
        TOLERANCIA_CENTRADO = 12 
        lockon_activado = False  
        lockon_activado_boca = False
        
        contador_pastilla_perdida = 0
        recuperacion_pastilla_intentada = False
        contador_sondeo = 0
        fase_sondeo_color = "IZQUIERDA"

        pastilla_en_transporte = False
        contador_caida = 0
        UMBRAL_PERSISTENCIA_CAIDA = 15

        try:
            while self._running:
                frame = camara.get_frame()
                if frame is None:
                    time.sleep(0.05)
                    continue

                dist_actual = brazo.obtener_distancia()
                z_coord = dist_actual
                frame_vis = frame.copy()

                # =========================================================
                # --- DETECCIÓN DE EMERGENCIA FÍSICA (PIN 34 ESP32) ---
                # =========================================================
                if brazo.en_emergencia:
                    if estado_actual != Estado.EMERGENCIA:
                        self.reportar("EMERGENCIA_ACTIVA")
                        # 1. Por seguridad: soltar carga abriendo pinza inmediatamente
                        brazo.mover_tiempo([(12, 80)], forzar=True, esperar=True)
                        # 2. Retirar brazo a HOME
                        brazo.mover_a_estado("HOME", forzar=True, esperar=True)
                        
                        estado_actual = Estado.EMERGENCIA
                        pastilla_en_transporte = False
                        lockon_activado = False
                        lockon_activado_boca = False

                    # Feedback visual en cámara de bloqueo
                    cv2.rectangle(frame_vis, (0, 0), (frame_vis.shape[1], frame_vis.shape[0]), (0, 0, 150), 10)
                    cv2.putText(frame_vis, "!!! PARO DE EMERGENCIA FÍSICO !!!", (20, 150), cv2.FONT_HERSHEY_DUPLEX, 1.0, (0, 0, 255), 3)
                    cv2.putText(frame_vis, "BOTON ENCLAVADO (LIBERAR PARA CONTINUAR)", (30, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    
                    with self.frame_lock:
                        self.last_frame = frame_vis
                    
                    time.sleep(0.05)
                    # CONTINUE evita que el robot pase a la máquina de estados. 
                    # Se queda "atrapado" aquí hasta que el botón se libere.
                    continue 
                else:
                    if estado_actual == Estado.EMERGENCIA:
                        print("[SISTEMA] Emergencia liberada por hardware. Reiniciando ciclo.")
                        estado_actual = Estado.HOME
                        macro_movimiento_hecho = False

                # --- MONITOREO DE CAÍDA ---
                if pastilla_en_transporte:
                    if brazo.estado_pinza == "VACIA":
                        contador_caida += 1
                        if contador_caida >= UMBRAL_PERSISTENCIA_CAIDA:
                            pastilla_en_transporte = False
                            estado_actual = Estado.HOME
                            macro_movimiento_hecho = False
                            contador_caida = 0
                    else:
                        contador_caida = 0 

                self.reportar(estado_actual)

                # =================================================
                # MÁQUINA DE ESTADOS 
                # =================================================

                if estado_actual == Estado.HOME:
                    lockon_activado = False
                    pastilla_en_transporte = False
                    if not macro_movimiento_hecho:
                        brazo.mover_a_estado("HOME", forzar=True)
                        macro_movimiento_hecho = True
                    estado_actual = Estado.OBSERVACION
                    macro_movimiento_hecho = False

                elif estado_actual == Estado.OBSERVACION:
                    if not macro_movimiento_hecho:
                        iniciar_det_pastilla(camara)
                        brazo.mover_a_estado("OBSERVACION")
                        time.sleep(2) 
                        macro_movimiento_hecho = True
                    
                    auto_exp.update(frame, camara)
                    frame_vis, colores, info_colores = process_color_frame(frame_vis)
                    
                    if self.color_objetivo in colores:
                        estado_actual = Estado.RECOLECCION
                        macro_movimiento_hecho = False
                    else:
                        cv2.putText(frame_vis, f"Sondeando {self.color_objetivo} ({fase_sondeo_color})...", (10, 60), 
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
                    frame_vis, info = process_pastillas_frame(frame_vis, self.color_objetivo.lower())
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
                                lockon_activado = True
                            if lockon_activado:
                                targets[1] = max(5, brazo.estado_actual[1] - 1)
                                if brazo.estado_actual[15] > 20: targets[15] = brazo.estado_actual[15] - 1
                                cv2.putText(frame_vis, "LOCK-ON: BAJANDO...", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                            else:
                                cv2.putText(frame_vis, "CENTRANDO FINAL...", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                        if z_coord <= Z_LIMITE_FINAL:
                            brazo.mover_tiempo([(0, brazo.estado_actual[0] + 4), (15, brazo.estado_actual[15] + 2)])
                            estado_actual = Estado.ESPERA_CONFIRMACION_AGARRE
                            finalizar_det_pastilla(camara)
                            macro_movimiento_hecho = False
                        
                        if targets:
                            brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                        
                        contador_pastilla_perdida = 0
                        recuperacion_pastilla_intentada = False
                    
                    elif self.color_objetivo in colores_backup:
                        cx, cy = info_colores_backup[self.color_objetivo]
                        ex_b = cx - (frame_vis.shape[1] // 2)
                        ey_b = cy - (frame_vis.shape[0] // 2)
                        targets = {}
                        if abs(ex_b) > 20: targets[0] = brazo.estado_actual[0] + (1 if ex_b > 0 else -1)
                        if abs(ey_b) > 20: targets[15] = brazo.estado_actual[15] + (1 if ey_b > 0 else -1)
                        if targets: brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                        cv2.putText(frame_vis, f"Aproximando a {self.color_objetivo}...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
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
                            recuperacion_pastilla_intentada = False

                elif estado_actual == Estado.ESPERA_CONFIRMACION_AGARRE:
                    cv2.putText(frame_vis, "ALINEACION OK - CERRANDO...", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    with self.frame_lock: self.last_frame = frame_vis
                    time.sleep(1.5)
                    
                    brazo.mover_tiempo([(12, 0)], forzar=True, esperar=True) 
                    time.sleep(1.0)
                    brazo.mover_a_estado("PRE_RECOLECCION", esperar=True)
                    time.sleep(1.5) 
                    
                    if brazo.estado_pinza == "CON_OBJETO":
                        pastilla_en_transporte = True
                        estado_actual = Estado.OBSERVACION_MANIQUI
                    else:
                        pastilla_en_transporte = False
                        brazo.mover_tiempo([(12, 80)], esperar=True)
                        estado_actual = Estado.OBSERVACION
                    macro_movimiento_hecho = False

                elif estado_actual == Estado.OBSERVACION_MANIQUI:
                    if not macro_movimiento_hecho:
                        iniciar_det_boca(camara)
                        brazo.mover_a_estado("OBSERVACION_MANIQUI", forzar=True, esperar=True)
                        time.sleep(0.5)
                        macro_movimiento_hecho = True
                        lockon_activado_boca = False
                    
                    auto_exp.update(frame, camara)
                    frame_rotated = cv2.rotate(frame, cv2.ROTATE_180)
                    frame_vis = frame_rotated.copy()
                    
                    cv_h, cv_w = frame_vis.shape[:2]
                    cv2.drawMarker(frame_vis, (cv_w // 2, cv_h // 2), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)
                    
                    frame_vis, coords_boca = get_mouth_coordinates(frame_vis)
                    if coords_boca:
                        estado_actual = Estado.SEGUIMIENTO_BOCA
                        macro_movimiento_hecho = False
                    else:
                        cv2.putText(frame_vis, "Buscando boca (Frame Rotado)...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

                elif estado_actual == Estado.SEGUIMIENTO_BOCA:
                    auto_exp.update(frame, camara)
                    frame_rotated = cv2.rotate(frame, cv2.ROTATE_180)
                    frame_vis = frame_rotated.copy()
                    
                    cv_h, cv_w = frame_vis.shape[:2]
                    cv2.drawMarker(frame_vis, (cv_w // 2, cv_h // 2), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)
                    
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
                                if abs(ey) > 30: targets[6] = brazo.estado_actual[6] + (1 if ey > 0 else -1)

                        if z_coord > Z_LIMITE_ENTREGA:
                            if brazo.estado_actual[1] > 70: targets[1] = brazo.estado_actual[1] - 1
                            if 6 not in targets and brazo.estado_actual[6] > 0:
                                targets[6] = brazo.estado_actual[6] - 1
                            if z_coord <= Z_UMBRAL_LOCKON and abs(ex) <= TOLERANCIA_CENTRADO:
                                lockon_activado_boca = True

                        if z_coord <= Z_LIMITE_ENTREGA:
                            finalizar_det_boca(camara)
                            estado_actual = Estado.ESPERA_CONFIRMACION_ENTREGA
                            macro_movimiento_hecho = False

                        if targets: brazo.mover_tiempo([(p, a) for p, a in targets.items()], esperar=False)
                    
                    else:
                        contador_sondeo += 1
                        if contador_sondeo < 100:
                            from constants.posiciones import POSICIONES
                            offset = 8 * np.sin(contador_sondeo * 0.15)
                            brazo.mover_tiempo([(0, POSICIONES["OBSERVACION_MANIQUI"][0][1] + offset)], esperar=False)
                            cv2.putText(frame_vis, "SONDEO DE BOCA...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                        else:
                            estado_actual = Estado.OBSERVACION_MANIQUI
                            macro_movimiento_hecho = False
                            contador_sondeo = 0

                elif estado_actual == Estado.ESPERA_CONFIRMACION_ENTREGA:
                    frame_rotated = cv2.rotate(frame, cv2.ROTATE_180)
                    frame_vis = frame_rotated.copy()
                    cv2.putText(frame_vis, "ENTREGA LISTA - ENTREGANDO...", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
                    with self.frame_lock: self.last_frame = frame_vis
                    time.sleep(1.5)
                    
                    estado_actual = Estado.ENTREGA
                    macro_movimiento_hecho = False

                elif estado_actual == Estado.ENTREGA:
                    brazo.mover_tiempo([(12, 80)])
                    time.sleep(1.0)
                    estado_actual = Estado.HOME
                    macro_movimiento_hecho = False
                    self.reportar("FINALIZADO")
                    break 

                # --- DIBUJADO DE ESTADOS SOBRE LA IMAGEN ---
                umbral_actual = Z_LIMITE_ENTREGA if "BOCA" in estado_actual or "ENTREGA" in estado_actual or "MANIQUI" in estado_actual else Z_LIMITE_FINAL
                color_z = (0, 255, 0) if z_coord <= umbral_actual else (0, 255, 255)
                cv2.putText(frame_vis, f"COORD Z (ToF): {z_coord}mm", (10, 30), cv2.FONT_HERSHEY_DUPLEX, 0.8, color_z, 2)
                
                m1 = brazo.mag1
                est_p = brazo.estado_pinza
                col_p = (0, 255, 0) if est_p == "CON_OBJETO" else (0, 255, 255) if est_p == "ABIERTA" else (0, 0, 255)
                texto_mag_status = f"ESTADO PINZA: {est_p}"
                
                cv2.putText(frame_vis, texto_mag_status, (10, frame_vis.shape[0] - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col_p, 2)
                cv2.putText(frame_vis, f"ESTADO CICLO: {estado_actual}", (10, frame_vis.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                with self.frame_lock:
                    self.last_frame = frame_vis

                time.sleep(0.01)

        finally:
            if hasattr(locals(), 'brazo'):
                brazo.mover_a_estado("HOME", forzar=True, esperar=True)
                brazo.cerrar()

    def stop(self):
        self._running = False