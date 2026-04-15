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