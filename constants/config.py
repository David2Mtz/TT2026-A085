import os
from dotenv import load_dotenv

load_dotenv()

# Offsets de la pinza respecto al centro de la cámara (Recolección)
OFFSET_X = int(os.getenv('OFFSET_X', 0))
OFFSET_Y = int(os.getenv('OFFSET_Y', -260))

# Offsets de búsqueda de boca (Maniquí)
BOCA_OFFSET_X = int(os.getenv('BOCA_OFFSET_X', 0))
BOCA_OFFSET_Y = int(os.getenv('BOCA_OFFSET_Y', 0))
BOCA_COMP_FACTOR = float(os.getenv('BOCA_COMP_FACTOR', 1.5))

# --- ASIGNACIÓN DE PINES DE SERVOS ---
PIN_BASE = 13    # Anteriormente 4, ahora 10
PIN_HOMBRO = 1
PIN_CODO = 6
PIN_MUÑECA = 14
PIN_ROTADOR = 8
PIN_PINZA = 12

