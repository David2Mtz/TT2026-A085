# modules/sujecion_evaluator.py

class SujecionEvaluator:
    def __init__(self, umbral_tolerancia=45, umbral_colision=8):
        self.baseline_recoleccion = None
        self.baselines_vacio = {} # Diccionario para firmas de vacío por estado
        self.norma_vacio_cerrado = None # Firma genérica (legacy)
        
        self.en_transporte = False
        self.umbral_tolerancia = umbral_tolerancia
        self.umbral_colision = umbral_colision
        self.umbral_presencia_minima = 25 # Aumentado de 12 a 25 para evitar falsos positivos por ruido
        
        self.historial_normas = []
        self.hubo_colision = False
        self.monitoreo_activo = False # Iniciar desactivado
        self.ultimo_delta = 0.0

        # Offsets empíricos de compensación por movimiento (uT)
        self.compensacion_estado = {
            "HOME": 0, "OBSERVACION": 15, "PRE_RECOLECCION": 25,
            "OBSERVACION_MANIQUI": 15, "ENTREGA": 15
        }

    def registrar_vacio(self, mag_x, mag_y, mag_z, estado="HOME"):
        """Registra la firma magnética de la pinza cerrada y VACÍA para un estado específico."""
        norma = (mag_x**2 + mag_y**2 + mag_z**2)**0.5
        self.baselines_vacio[estado] = norma
        self.norma_vacio_cerrado = norma # Mantener legacy
        print(f"[EVALUADOR] Firma de VACÍO registrada en '{estado}': {norma:.1f} uT")

    def capturar_baseline(self, mag_x, mag_y, mag_z):
        """Captura la firma del objeto recién agarrado (en el suelo)."""
        self.baseline_recoleccion = (mag_x**2 + mag_y**2 + mag_z**2)**0.5
        self.en_transporte = True
        self.hubo_colision = False
        self.historial_normas = [self.baseline_recoleccion] * 3
        print(f"[EVALUADOR] Baseline Recolección (Ground): {self.baseline_recoleccion:.1f} uT")

    def verificar_presencia_real(self, mag_x, mag_y, mag_z, estado="PRE_RECOLECCION"):
        """
        Compara la lectura actual con la firma de 'VACÍO' del estado actual.
        Si la diferencia es significativa, hay algo en la pinza.
        """
        referencia_vacio = self.baselines_vacio.get(estado, self.norma_vacio_cerrado)
        
        if referencia_vacio is None:
            print("[EVALUADOR] Advertencia: No hay referencia de VACÍO para verificar.")
            return True 
            
        norma_actual = (mag_x**2 + mag_y**2 + mag_z**2)**0.5
        delta_vacio = abs(norma_actual - referencia_vacio)
        
        # --- FILTRO DE SENSATEZ (Sanity Check) ---
        # Si el delta es EXTREMADAMENTE alto (ej. > 400 uT), es probable que sea una 
        # lectura errónea o interferencia electromagnética de un motor.
        if delta_vacio > 400:
            print(f"[EVALUADOR] ¡ERROR! Delta anómalo detectado ({delta_vacio:.1f} uT). Ignorando por seguridad.")
            return False

        if delta_vacio < self.umbral_presencia_minima:
            print(f"[EVALUADOR] ¡ALERTA! Lectura idéntica a VACÍO en {estado} (Delta: {delta_vacio:.1f} uT).")
            return False
        
        print(f"[EVALUADOR] Verificación OK (Delta vs Vacío en {estado}: {delta_vacio:.1f} uT).")
        
        # --- NUEVO: RE-ESTABLECER BASELINE SI HAY ÉXITO EN EL AIRE ---
        # Si estamos seguros de que hay algo (Delta grande vs Vacío), pero el baseline del suelo
        # falló, actualizamos el baseline para que el monitoreo continuo funcione.
        if self.baseline_recoleccion is not None:
            offset = self.compensacion_estado.get(estado, 0)
            desviacion = abs(norma_actual - (self.baseline_recoleccion + offset))
            
            if desviacion > self.umbral_tolerancia:
                print(f"[EVALUADOR] Re-calibrando baseline dinámicamente en {estado}...")
                self.baseline_recoleccion = norma_actual - offset
        
        return True

    def evaluar_agarre(self, mag_x, mag_y, mag_z, estado_actual="HOME"):
        """
        Monitoreo continuo durante el transporte.
        """
        norma_actual = (mag_x**2 + mag_y**2 + mag_z**2)**0.5
        
        # --- 1. DETECCIÓN DE COLISIÓN (Basado en cambio brusco) ---
        if self.monitoreo_activo:
            if len(self.historial_normas) >= 10:
                norma_promedio = sum(self.historial_normas) / len(self.historial_normas)
                self.ultimo_delta = abs(norma_actual - norma_promedio)
                
                # Debug de ruido/sensibilidad
                if self.ultimo_delta > 0.5:
                    print(f"[MAG DEBUG] Delta: {self.ultimo_delta:.2f} | Norma: {norma_actual:.2f} | Prom: {norma_promedio:.2f}")

                if self.ultimo_delta > self.umbral_colision:
                    self.hubo_colision = True
                    print(f"[EVALUADOR] !!! COLISIÓN DETECTADA !!! Delta: {self.ultimo_delta:.2f} (Umbral: {self.umbral_colision})")
                    
            self.historial_normas.append(norma_actual)
            if len(self.historial_normas) > 10: self.historial_normas.pop(0)

        # --- 2. DETECCIÓN DE PRESENCIA (Basado en baseline + compensación) ---
        if self.baseline_recoleccion is None: 
            return "ABIERTA"
        
        offset = self.compensacion_estado.get(estado_actual, 0)
        # La desviación es respecto a lo que capturamos en el suelo + el cambio esperado por mover el brazo
        desviacion = abs(norma_actual - (self.baseline_recoleccion + offset))
        
        # Histeresis: Si ya estamos en transporte, permitimos una desviación mayor
        umbral = self.umbral_tolerancia if not self.en_transporte else (self.umbral_tolerancia + 20)
        
        if desviacion < umbral: 
            return "CON_OBJETO"
        else: 
            # Si se pierde el objeto, imprimimos info para debug
            if self.en_transporte:
                print(f"[DEBUG AGARRE] OBJETO PERDIDO? Desv: {desviacion:.1f} | Norma: {norma_actual:.1f} | Exp: {self.baseline_recoleccion + offset:.1f}")
            return "VACIA"

    def reset(self):
        self.hubo_colision = False
        self.ultimo_delta = 0.0
        self.en_transporte = False
        self.baseline_recoleccion = None
