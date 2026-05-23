# modules/sujecion_evaluator.py

class SujecionEvaluator:
    def __init__(self, umbral_tolerancia=35, umbral_colision=10):
        self.baseline_recoleccion = None
        self.en_transporte = False
        self.umbral_tolerancia = umbral_tolerancia
        self.umbral_colision = umbral_colision
        
        self.historial_normas = []
        self.hubo_colision = False
        self.monitoreo_activo = True
        self.ultimo_delta = 0.0

        self.compensacion_estado = {
            "HOME": 0, "OBSERVACION": 15, "PRE_RECOLECCION": 20,
            "OBSERVACION_MANIQUI": 15, "ENTREGA": 15
        }

    def capturar_baseline(self, mag_x, mag_y, mag_z):
        self.baseline_recoleccion = (mag_x**2 + mag_y**2 + mag_z**2)**0.5
        self.en_transporte = True
        self.hubo_colision = False
        self.historial_normas = [self.baseline_recoleccion] * 3
        print(f"[EVALUADOR] Baseline: {self.baseline_recoleccion:.1f} uT")

    def evaluar_agarre(self, mag_x, mag_y, mag_z, estado_actual="HOME"):
        """
        Retorna el estado de PRESENCIA del objeto. 
        La colisión se gestiona como una bandera interna (self.hubo_colision).
        """
        norma_actual = (mag_x**2 + mag_y**2 + mag_z**2)**0.5
        
        # --- 1. DETECCIÓN DE COLISIÓN (Flag persistente) ---
        if self.monitoreo_activo:
            if len(self.historial_normas) >= 3:
                norma_promedio = sum(self.historial_normas) / len(self.historial_normas)
                self.ultimo_delta = abs(norma_actual - norma_promedio)
                
                if self.ultimo_delta > self.umbral_colision:
                    # Registramos el evento pero permitimos que la función siga
                    self.hubo_colision = True
                    
            self.historial_normas.append(norma_actual)
            if len(self.historial_normas) > 3: self.historial_normas.pop(0)

        # --- 2. DETECCIÓN DE PRESENCIA (Lógica Original) ---
        if self.baseline_recoleccion is None: 
            return "ABIERTA"
        
        offset = self.compensacion_estado.get(estado_actual, 0)
        desviacion = abs(norma_actual - (self.baseline_recoleccion + offset))
        
        if desviacion < self.umbral_tolerancia: 
            return "CON_OBJETO"
        else: 
            return "VACIA"

    def reset(self):
        self.hubo_colision = False
        self.ultimo_delta = 0.0
