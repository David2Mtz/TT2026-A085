import os
from dotenv import load_dotenv

load_dotenv()

# Offsets de la pinza respecto al centro de la cámara (Recolección)
OFFSET_X = int(os.getenv('OFFSET_X', -40))
OFFSET_Y = int(os.getenv('OFFSET_Y', -265))

# Offset de alineación final (justo antes de cerrar)
OFFSET_ALINEACION_X = int(os.getenv('OFFSET_ALINEACION_X', -20))
OFFSET_ALINEACION_Y = int(os.getenv('OFFSET_ALINEACION_Y', -235))


# Offsets de búsqueda de boca (Maniquí)
BOCA_OFFSET_X = int(os.getenv('BOCA_OFFSET_X', 0))
BOCA_OFFSET_Y = int(os.getenv('BOCA_OFFSET_Y', 0))
BOCA_COMP_FACTOR = float(os.getenv('BOCA_COMP_FACTOR', 1.5))

# --- ASIGNACIÓN DE PINES DE SERVOS ---
PIN_BASE = 15    # Anteriormente 4, ahora 10
PIN_HOMBRO = 1
PIN_CODO = 6
PIN_MUÑECA = 7
PIN_ROTADOR = 8
PIN_PINZA = 12

