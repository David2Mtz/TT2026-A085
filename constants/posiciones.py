# constants/posiciones.py
from .config import PIN_BASE, PIN_HOMBRO, PIN_CODO, PIN_MUÑECA, PIN_ROTADOR, PIN_PINZA

# Diccionario de posiciones predefinidas (7 servos)
# Formato: "NOMBRE": [(pin, angulo), (pin, angulo), ...]
POSICIONES = {
    # Se llama en el estado: INICIO_HOME y al terminar SOLTAR
    "HOME": [
        (PIN_BASE, 90),   # Base
        (PIN_HOMBRO, 180), # Hombro 180 HOME 90 PARADO
        (PIN_CODO, 140), # Codo
        (PIN_MUÑECA, 90),  # Muñeca (Pitch) 0 HACIA ARRIBA, 180 HACIA ABAJO
        (PIN_ROTADOR, 90),  # Rotador (Roll)
        (PIN_PINZA, 0)    # Pinza (Abierta: 80, Cerrada: 0)
    ],

    # Se llama en el estado: OBSERVAR_COLORES
    # Posición alta para que la cámara vea toda la zona de pastilleros
    "OBSERVACION": [
        (PIN_BASE, 90),   # Base (Frente)
        (PIN_CODO, 60),  # Codo flexionado para apuntar la cámara
        (PIN_HOMBRO, 80),  # Hombro inclinado sobrela mesa
        (PIN_MUÑECA, 140), # Muñeca (Pitch) apuntando hacia abajo
        (PIN_ROTADOR, 0),  # Rotador (Roll) nivelado
        (PIN_PINZA, 80)   # Pinza abierta
    ],

    # Se llama en el estado: RECOLECCION
    # Sube el brazo con la pastilla agarrada para evitar chocar al girar
    "PRE_RECOLECCION": [
        (PIN_CODO, 90), 
        (PIN_HOMBRO, 90), 
        (PIN_MUÑECA, 90)   # Muñeca (Pitch)
    ],

    # Se llama en el estado: OBSERVACION_MANIQUI
    # Posición inicial apuntando hacia el rostro para que el IBVS busque la boca
    "OBSERVACION_MANIQUI": [
        (PIN_BASE, 170),   # Regresar base al frente
        (PIN_CODO, 105), 
        (PIN_MUÑECA, 80),    # Muñeca (Pitch)
        (PIN_HOMBRO, 140), # Posición hacia la cara del usuario
        (PIN_ROTADOR, 0), # MANTENER NIVELADO PARA MIRAR AL FRENTE (Sin invertir)
        (PIN_PINZA, 0)     # Pinza (Cerrada)
    ],


    # Se llama en el estado: ENTREGA
    "ENTREGA": [
        (PIN_BASE, 160),   # Regresar base al frente
        (PIN_CODO, 120), 
        (PIN_MUÑECA, 90),    # Muñeca (Pitch)
        (PIN_HOMBRO, 140), # Posición hacia la cara del usuario
        (PIN_ROTADOR, 0), # ROTACIÓN 180 PARA MIRAR AL FRENTE (Mismo que OBSERVACION_MANIQUI)
        (PIN_PINZA, 0)     # Pinza (Cerrada)
    ]
    }

