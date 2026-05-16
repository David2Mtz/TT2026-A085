# constants/posiciones.py

# Diccionario de posiciones predefinidas (7 servos)
# Formato: "NOMBRE": [(pin, angulo), (pin, angulo), ...]
POSICIONES = {
    # Se llama en el estado: INICIO_HOME y al terminar SOLTAR
    "HOME": [
        (0, 90),   # Base
        (1, 180), # Hombro 180 HOME 90 PARADO
        (6, 140), # Codo
        (15, 90),  # Muñeca (Pitch) 0 HACIA ARRIBA, 180 HACIA ABAJO
        (8, 90),  # Rotador (Roll)
        (12, 80)    # Pinza (Abierta: 80, Cerrada: 0)
    ],

    # Se llama en el estado: OBSERVAR_COLORES
    # Posición alta para que la cámara vea toda la zona de pastilleros
    "OBSERVACION": [
        (0, 90),   # Base (Frente)
        (6, 60),  # Codo flexionado para apuntar la cámara
        (1, 70),  # Hombro inclinado sobrela mesa
        (15, 170), # Muñeca (Pitch) apuntando hacia abajo
        (8, 0),  # Rotador (Roll) nivelado
        (12, 80)   # Pinza abierta
    ],

    # Se llama en el estado: RECOLECCION
    # Sube el brazo con la pastilla agarrada para evitar chocar al girar
    "PRE_RECOLECCION": [
        (6, 90), 
        (1, 90), 
        (15, 90)   # Muñeca (Pitch)
    ],

    # Se llama en el estado: OBSERVACION_MANIQUI
    # Posición inicial apuntando hacia el rostro para que el IBVS busque la boca
    "OBSERVACION_MANIQUI": [
        (0, 170),   # Regresar base al frente
        (6, 105), 
        (15, 70),    # Muñeca (Pitch)
        (1, 140), # Posición hacia la cara del usuario
        (8, 180), # ROTACIÓN 90 PARA MIRAR AL FRENTE
        (12, 0)     # Pinza (Cerrada)
    ],

    # Se llama en el estado: ENTREGA
    "ENTREGA": [
        (0, 160),   # Regresar base al frente
        (6, 120), 
        (15, 90),    # Muñeca (Pitch)
        (1, 140), # Posición hacia la cara del usuario
        (8, 0), # ROTACIÓN 180 PARA MIRAR AL FRENTE
        (12, 0)     # Pinza (Cerrada)
    ]
    }
