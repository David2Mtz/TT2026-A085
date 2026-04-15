# constants/positions.py

# Diccionario de posiciones predefinidas (7 servos)
# Formato: "NOMBRE": [(pin, angulo), (pin, angulo), ...]
# Nota: Puedes mover hasta 4 servos simultáneamente en cada 'mover_tiempo'
POSICIONES = {
    "HOME": [
        (0, 0),   # Base
        (1, 180), # Hombro
        (3, 170), # Codo
        (4, 90),  # Muñeca (Pitch)
        (5, 90),  # Rotador (Roll)
        (6, 0)    # Pinza (Abierta)
    ],
    "OBSERVACION": [
        (0, 90),  # Girar al centro de la mesa
        (1, 120), # Bajar un poco el hombro
        (3, 100), # Extender codo para ver mejor
        (4, 45)   # Inclinar cámara hacia la mesa
    ],
    "PRE_RECOLECCION": [
        (1, 90), 
        (3, 90), 
        (4, 90)
    ],
    "ENTREGA": [
        (0, 0),   # Regresar base al frente
        (1, 140), # Posición hacia la cara del usuario
        (3, 150), 
        (4, 120)
    ]
}