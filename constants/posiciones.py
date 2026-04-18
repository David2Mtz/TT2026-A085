# constants/posiciones.py

# Diccionario de posiciones predefinidas (7 servos)
# Formato: "NOMBRE": [(pin, angulo), (pin, angulo), ...]
POSICIONES = {
    # Se llama en el estado: INICIO_HOME y al terminar SOLTAR
    "HOME": [
        (0, 90),   # Base
        (1, 180), # Hombro
        (4, 120),  # Muñeca (Pitch)
        (3, 140), # Codo
        (5, 90),  # Rotador (Roll)
        (6, 88)    # Pinza (Abierta)
    ],
    
    # Se llama en el estado: OBSERVAR_COLORES
    # Posición alta para que la cámara vea toda la zona de pastilleros
    "OBSERVACION": [
        (0, 90),   # Base (Frente)
        (3, 60),  # Codo flexionado para apuntar la cámara
        (1, 70),  # Hombro inclinado sobre la mesa
        (4, 180), # Muñeca (Pitch) apuntando hacia abajo
        (5, 90),  # Rotador (Roll) nivelado
        (6, 44)   # Pinza semi-abierta
    ],
    
    # Se llama en el estado: RECOLECCION
    # Sube el brazo con la pastilla agarrada para evitar chocar al girar
    "PRE_RECOLECCION": [
        (3, 90), 
        (1, 90), 
        (4, 90)
    ],
    
    # Se llama en el estado: OBSERVACION_MANIQUI
    # Posición inicial apuntando hacia el rostro para que el IBVS busque la boca
    "ENTREGA": [
        (0, 150),   # Regresar base al frente
        (3, 120), 
        (4, 90),
        (1, 140), # Posición hacia la cara del usuario
        (6, 0)
    ]
}