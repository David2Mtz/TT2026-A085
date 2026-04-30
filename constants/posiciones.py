# constants/posiciones.py

# Diccionario de posiciones predefinidas (7 servos)
# Formato: "NOMBRE": [(pin, angulo), (pin, angulo), ...]
POSICIONES = {
    # Se llama en el estado: INICIO_HOME y al terminar SOLTAR
    "HOME": [
        (0, 90),   # Base
        (1, 180), # Hombro 180 HOME 90 PARADO
        (6, 140), # Codo
        (15, 90),  # Muñeca (Pitch) 0 HACIA ARRIBA, 180 HACIA ABAJO ANTES PIN 4
        (13, 90),  # Rotador (Roll) 0 A 180. ANTES PIN 5
        (12, 90)    # Pinza (Abierta) 90 grados abre, 10 grados cierra
    ],

    # Se llama en el estado: OBSERVAR_COLORES
    # Posición alta para que la cámara vea toda la zona de pastilleros
    "OBSERVACION": [
        (0, 90),   # Base (Frente)
        (6, 60),  # Codo flexionado para apuntar la cámara
        (1, 70),  # Hombro inclinado sobre la mesa
        (15, 170), # Muñeca (Pitch) apuntando hacia abajo (ANTES PIN 4)
        (13, 0),  # Rotador (Roll) nivelado (ANTES PIN 5)
        (12, 90)   # Pinza abierta
    ],

    # Se llama en el estado: RECOLECCION
    # Sube el brazo con la pastilla agarrada para evitar chocar al girar
    "PRE_RECOLECCION": [
        (6, 90), 
        (1, 90), 
        (15, 90)   # Muñeca (Pitch) (ANTES PIN 4)
    ],

    # Se llama en el estado: OBSERVACION_MANIQUI
    # Posición inicial apuntando hacia el rostro para que el IBVS busque la boca
    "ENTREGA": [
        (0, 160),   # Regresar base al frente
        (6, 120), 
        (15, 90),    # Muñeca (Pitch) (ANTES PIN 4)
        (1, 140), # Posición hacia la cara del usuario
        (13, 180), # ROTACIÓN 180 PARA MIRAR AL FRENTE
        (12, 10)     # Pinza (Cerrada)
    ]
    }
