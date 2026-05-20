# modules/sujecion_evaluator.py

class SujecionEvaluator:
    def __init__(self, umbral_tolerancia=35):
        """
        Versión 4: Basada en Desviación Dinámica.
        Compara la lectura actual contra una base capturada al cerrar la pinza.
        """
        self.baseline_recoleccion = None
        self.en_transporte = False
        self.umbral_tolerancia = umbral_tolerancia # Cuánto puede desviarse antes de marcar caída
        
        # Compensación por movimiento (basado en tus datos de calibración)
        # Cuánta "Norma" suma o resta el brazo naturalmente al ir a cada estado
        self.compensacion_estado = {
            "HOME": 0,
            "OBSERVACION": 15,
            "PRE_RECOLECCION": 20,
            "OBSERVACION_MANIQUI": 120, # Sube mucho al girar a 170 grados
            "ENTREGA": 90
        }

    def capturar_baseline(self, mag_x, mag_y, mag_z):
        """ Se llama justo después de cerrar la pinza sobre la pastilla """
        self.baseline_recoleccion = (mag_x**2 + mag_y**2 + mag_z**2)**0.5
        self.en_transporte = True
        print(f"[EVALUADOR] Baseline de transporte fijado en: {self.baseline_recoleccion:.1f}")

    def evaluar_agarre(self, mag_x, mag_y, mag_z, estado_actual="HOME"):
        if self.baseline_recoleccion is None:
            return "ABIERTA"

        norma_actual = (mag_x**2 + mag_y**2 + mag_z**2)**0.5
        
        # 1. Calcular compensación según donde esté el brazo
        offset = self.compensacion_estado.get(estado_actual, 0)
        
        # 2. Norma esperada si la pastilla SIGUE AHÍ
        norma_esperada = self.baseline_recoleccion + offset
        
        # 3. Diferencia
        desviacion = abs(norma_actual - norma_esperada)
        
        # Si la desviación es muy grande (ej. > 45), es que el imán saltó a posición de vacío
        if desviacion < self.umbral_tolerancia:
            return "CON_OBJETO"
        else:
            # Si se sale del umbral, hay sospecha de caída
            return "VACIA"

    def reset(self):
        self.baseline_recoleccion = None
        self.en_transporte = False
