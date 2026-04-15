# TT2026-A085: PROTOTIPO DE CONTROL HÍBRIDO EEG – VISIÓN POR COMPUTADORA PARA BRAZO ROBÓTICO

Este repositorio contiene el código fuente del módulo de Visión por Computadora y Control Cinemático para un brazo robótico. El sistema forma parte de una arquitectura de control híbrido que integra señales electroencefalográficas (EEG) capturadas mediante un casco EMOTIV EPOC+ y navegación autónoma mediante Servocontrol Visual Basado en Imagen (IBVS).

## 🚀 Características Principales

* **Visión *Eye-in-Hand*:** Procesamiento de flujo de video en tiempo real desde una ESP32-CAM montada directamente en el efector final (pinza).
* **Servocontrol Visual (IBVS):** Bucle de control cerrado que calcula el error en píxeles para centrar la pinza sobre el objetivo dinámicamente, eliminando la necesidad de calibración por milímetros absolutos.
* **Detección y Clasificación:** Análisis de rangos HSV y morfología para identificar bases y ejecutar la función de `definir-bloque-candidatos` para aislar las pastillas objetivo.
* **Gestión de Estados Cinéticos:** Implementación de un gemelo digital en memoria para rastrear y sincronizar la posición de 7 servomotores de manera simultánea.
* **Comunicación Síncrona:** Protocolo serial de confirmación ("OK") para evitar la saturación del buffer en el microcontrolador y garantizar movimientos fluidos.

## 📁 Estructura del Repositorio

```text
├── app/
│   └── happyPath.py            # Máquina de estados principal y bucle de ejecución.
├── constants/
│   └── positions.py            # Diccionario de posiciones vectoriales del brazo (HOME, OBSERVACION, etc.).
├── modules/
│   ├── arm_controller.py       # Lógica del servocontrol, serialización de cadenas y ajuste IBVS.
│   ├── color_detector_v2.py    # Detección de zonas de color y extracción de ROIs.
│   └── pastillas_detector.py   # Procesamiento morfológico y cálculo de error en ejes X/Y.
├── utils/
│   └── flujo_camara.py         # Cliente Serial para decodificar frames JPEG en crudo.
└── requirements.txt            # Dependencias del proyecto.

```

🛠️ Tecnologías y Hardware
Lenguaje: Python 3.x

Visión por Computadora: OpenCV (cv2), NumPy.

Hardware Visión: ESP32-CAM

Hardware Control: Microcontrolador (Controlador de Servos) + Brazo Robótico 5-DOF con pinza.

Interfaz Neuronal: EMOTIV EPOC+

⚙️ Instalación y Configuración
Clonar el repositorio:

Bash
git clone
cd TT2026-A085
Crear y activar un entorno virtual (Recomendado):

Bash
python3 -m venv venv
source venv/bin/activate
Instalar dependencias:

Bash
pip install -r requirements.txt
Configurar puertos:

Revisa la instanciación de CameraSerial y ArmController en app/happyPath.py para asegurar que los puertos coincidan con tu sistema operativo (por ejemplo, /dev/cu.usbserial-XXX en macOS).

🏃‍♂️ Ejecución
Para iniciar el flujo principal, asegúrate de que el brazo se encuentre físicamente doblado en su posición segura de descanso y ejecuta:

Bash
python app/happyPath.py
Controles Manuales: > * Presiona la tecla n en la ventana de video de OpenCV para avanzar explícitamente en la máquina de estados.

Presiona q para abortar la ejecución de manera segura y cerrar los puertos.

👥 Equipo de Desarrollo

Aldebarán

César Alberto

Luis David

Desarrollado en la Escuela Superior de Cómputo (ESCOM) - IPN.