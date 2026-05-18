# modules/sujecion_evaluator.py

class SujecionEvaluator:
    def __init__(self, umbral_flexibilidad=2, max_historial=12):
        """
        Versión 3: Basada en la Magnitud del Vector (Norma).
        Detecta que la magnitud disminuye cuando hay un objeto (bloqueo mecánico del imán).
        """
        self.historial_estado = []
        self.max_historial = max_historial
        self.umbral_flexibilidad = umbral_flexibilidad
        self.en_transporte = False # Estado "Sticky"

    def evaluar_agarre(self, mag_x, mag_y, mag_z):
        if mag_x == 0.0 and mag_y == 0.0 and mag_z == 0.0:
            return None

        # 1. Calcular Magnitud (Norma) del campo magnético
        mag_norm = (mag_x**2 + mag_y**2 + mag_z**2)**0.5
        
        es_objeto = False
        
        # --- LÓGICA DE UMBRALES DINÁMICOS (Calibrados por datos del usuario) ---
        # Posición de Transporte / Recolección Alta (Z > 1000)
        # VACIO: ~1460-1510 | OBJETO: ~1380-1445
        if mag_z > 1000:
            if mag_norm < 1455: 
                es_objeto = True
        
        # Posición de Observación / Recolección Baja (Z < 1000)
        # VACIO: ~1310 | OBJETO: ~1220
        else:
            if mag_norm < 1280:
                es_objeto = True

        # Regla de Oro: Si el Eje X es muy positivo, hay objeto 100%
        if mag_x > -885:
            es_objeto = True

        # 2. Gestión del Historial (Suavizado)
        self.historial_estado.append(es_objeto)
        if len(self.historial_estado) > self.max_historial:
            self.historial_estado.pop(0)

        # 3. Decisión con Flexibilidad
        # Si ya estábamos en transporte, somos EXTRA flexibles (Sticky)
        votos_positivos = sum(self.historial_estado)
        
        # Umbral dinámico: 
        # - Si ya creemos tener el objeto, solo necesitamos 1 voto positivo de 12 para mantenerlo.
        # - Si estamos verificando por primera vez, necesitamos al menos 'umbral_flexibilidad' (2).
        req = 1 if self.en_transporte else self.umbral_flexibilidad
        
        if votos_positivos >= req:
            self.en_transporte = True
            return "CON_OBJETO"
        else:
            self.en_transporte = False
            return "VACIA"

    def reset(self):
        """ Limpia historial y estado sticky. """
        self.historial_estado = []
        self.en_transporte = False
