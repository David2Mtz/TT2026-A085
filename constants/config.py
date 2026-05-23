import os
from dotenv import load_dotenv

load_dotenv()

# Offsets de la pinza respecto al centro de la cámara (Recolección)
OFFSET_X = int(os.getenv('OFFSET_X', -30))
OFFSET_Y = int(os.getenv('OFFSET_Y', -260))

# Offsets de búsqueda de boca (Maniquí)
BOCA_OFFSET_X = int(os.getenv('BOCA_OFFSET_X', 0))
BOCA_OFFSET_Y = int(os.getenv('BOCA_OFFSET_Y', 0))
BOCA_COMP_FACTOR = float(os.getenv('BOCA_COMP_FACTOR', 1.5))
