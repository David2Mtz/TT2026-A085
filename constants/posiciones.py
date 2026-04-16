# constants/posiciones.py

# Diccionario de posiciones predefinidas (7 servos)
# Formato: "NOMBRE": [(pin, angulo), (pin, angulo), ...]
POSICIONES = {
    # Se llama en el estado: INICIO_HOME y al terminar SOLTAR
    "HOME": [
        (0, 0),   # Base
        (1, 180), # Hombro
        (3, 170), # Codo
        (4, 90),  # Muñeca (Pitch)
        (5, 90),  # Rotador (Roll)
        (6, 0)    # Pinza (Abierta)
    ],
    
    # Se llama en el estado: OBSERVAR_COLORES
    # Posición alta para que la cámara vea toda la zona de pastilleros
    "OBSERVACION": [
        (0, 0),   # Base (Frente)
        (1, 40),  # Hombro inclinado sobre la mesa
        (3, 20),  # Codo flexionado para apuntar la cámara
        (4, 180), # Muñeca (Pitch) apuntando hacia abajo
        (5, 90),  # Rotador (Roll) nivelado
        (6, 90)   # Pinza semi-abierta
    ],
    
    # Se llama en el estado: RECOLECCION
    # Sube el brazo con la pastilla agarrada para evitar chocar al girar
    "PRE_RECOLECCION": [
        (1, 90), 
        (3, 90), 
        (4, 90)
    ],
    
    # Se llama en el estado: OBSERVACION_MANIQUI
    # Posición inicial apuntando hacia el rostro para que el IBVS busque la boca
    "ENTREGA": [
        (0, 0),   # Regresar base al frente
        (1, 140), # Posición hacia la cara del usuario
        (3, 150), 
        (4, 120)
    ]
}