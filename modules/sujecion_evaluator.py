# modules/sujecion_evaluator.py

class SujecionEvaluator:
    def __init__(self, umbral_tolerancia=35, umbral_colision=10):
        self.baseline_recoleccion = None
        self.norma_vacio_cerrado = None # Firma del magnetómetro cuando la pinza está realmente vacía
        self.en_transporte = False
        self.umbral_tolerancia = umbral_tolerancia
        self.umbral_colision = umbral_colision
        self.umbral_presencia_minima = 15 # Delta mínimo respecto a "vacío" para considerar que hay algo
        
        self.historial_normas = []
        self.hubo_colision = False
        self.monitoreo_activo = True
        self.ultimo_delta = 0.0

        self.compensacion_estado = {
            "HOME": 0, "OBSERVACION": 15, "PRE_RECOLECCION": 20,
            "OBSERVACION_MANIQUI": 15, "ENTREGA": 15
        }

    def registrar_vacio(self, mag_x, mag_y, mag_z):
        """Registra la firma magnética de la pinza cerrada y VACÍA."""
        self.norma_vacio_cerrado = (mag_x**2 + mag_y**2 + mag_z**2)**0.5
        print(f"[EVALUADOR] Firma de VACÍO registrada: {self.norma_vacio_cerrado:.1f} uT")

    def capturar_baseline(self, mag_x, mag_y, mag_z):
        self.baseline_recoleccion = (mag_x**2 + mag_y**2 + mag_z**2)**0.5
        self.en_transporte = True
        self.hubo_colision = False
        self.historial_normas = [self.baseline_recoleccion] * 3
        print(f"[EVALUADOR] Success Baseline: {self.baseline_recoleccion:.1f} uT")

    def verificar_presencia_real(self, mag_x, mag_y, mag_z):
        """
        Compara la lectura actual con la firma de 'VACÍO'.
        Si la diferencia es muy pequeña, es un FALSO POSITIVO (la pinza cerró de más).
        """
        if self.norma_vacio_cerrado is None:
            return True # No podemos verificar, asumimos éxito
            
        norma_actual = (mag_x**2 + mag_y**2 + mag_z**2)**0.5
        delta_vacio = abs(norma_actual - self.norma_vacio_cerrado)
        
        # Si el delta es menor a 15 uT, es muy probable que esté vacía
        if delta_vacio < self.umbral_presencia_minima:
            print(f"[EVALUADOR] ¡ALERTA! Lectura muy similar a VACÍO (Delta: {delta_vacio:.1f} uT).")
            return False
        
        print(f"[EVALUADOR] Verificación OK (Delta vs Vacío: {delta_vacio:.1f} uT).")
        return True

    def evaluar_agarre(self, mag_x, mag_y, mag_z, estado_actual="HOME"):
        """
        Retorna el estado de PRESENCIA del objeto. 
        """
        norma_actual = (mag_x**2 + mag_y**2 + mag_z**2)**0.5
        
        # --- 1. DETECCIÓN DE COLISIÓN ---
        if self.monitoreo_activo:
            if len(self.historial_normas) >= 3:
                norma_promedio = sum(self.historial_normas) / len(self.historial_normas)
                self.ultimo_delta = abs(norma_actual - norma_promedio)
                
                if self.ultimo_delta > self.umbral_colision:
                    self.hubo_colision = True
                    
            self.historial_normas.append(norma_actual)
            if len(self.historial_normas) > 3: self.historial_normas.pop(0)

        # --- 2. DETECCIÓN DE PRESENCIA ---
        if self.baseline_recoleccion is None: 
            return "ABIERTA"
        
        offset = self.compensacion_estado.get(estado_actual, 0)
        desviacion = abs(norma_actual - (self.baseline_recoleccion + offset))
        
        # Histeresis: Si ya estamos en transporte, permitimos una desviación mayor antes de dar por perdido
        umbral = self.umbral_tolerancia if not self.en_transporte else (self.umbral_tolerancia + 10)
        
        if desviacion < umbral: 
            return "CON_OBJETO"
        else: 
            return "VACIA"

    def reset(self):
        self.hubo_colision = False
        self.ultimo_delta = 0.0
        self.en_transporte = False
        self.baseline_recoleccion = None
