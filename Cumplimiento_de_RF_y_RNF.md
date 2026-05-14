# Reporte de Cumplimiento de Requerimientos - TT2026-A085

Este documento evalúa el estado del prototipo frente a los requerimientos definidos en el Documento Técnico (Capítulo III).

## 1. Requerimientos Funcionales (RF)

### 1.1 Brazo Robótico (Tabla 2)
| ID        | Requerimiento                    | Estado           | Observación                                                                                      |
| :-------- | :------------------------------- | :--------------- | :----------------------------------------------------------------------------------------------- |
| **RF-01** | Restringir movimiento (40-55 cm) | **Cumplido**     | El software aplica límites angulares (`np.clip`) y el sensor ToF detiene el avance en el eje Z.  |
| **RF-02** | Movimiento a contenedores        | **Cumplido**     | Implementado mediante `Estado.OBSERVACION` y la posición predefinida en `posiciones.py`.         |
| **RF-03** | Sujeción de comprimido           | **Cumplido**     | Ejecuta la secuencia de cierre (Pin 12 a 0°) tras la alineación visual.                          |
| **RF-04** | Mantener fuerza de sujeción      | **Cumplido**     | El material e-Flesh y la rampa de cierre en el firmware aseguran un agarre estable sin fractura. |
| **RF-05** | Entrega a 15 cm de la boca       | **Cumplido**     | `Z_LIMITE_ENTREGA = 150` (150mm = 15cm) definido en `ciclo_completo.py`.                         |
| **RF-06** | Detenerse si suelta comprimido   | **Cumplido**     | Implementado el **Monitor de Caída** con magnetómetro en tiempo real.                            |
| **RF-07** | Detenerse si no detecta boca     | **Cumplido**     | La máquina de estados regresa a `OBSERVACION_MANIQUI` si se pierde el objetivo visual.           |
| **RF-08** | Sensores de contacto (FSR)       | **No Detectado** | El firmware actual solo reporta ToF y Magnetómetro. No hay lectura de FSR en el flujo serial.    |
| **RF-09** | Parado de emergencia físico      | **Cumplido**     | Botón en Pin 34 funcional, gestionado por interrupción en hardware y detectado por software.     |
| **RF-10** | Regreso a HOME tras error        | **Cumplido**     | Implementado en los bloques `finally` y en la lógica de emergencia.                              |
| **RF-11** | Inicio mediante comando BCI      | **Parcial**      | Se utiliza `BlinkDetector` (parpadeos) como disparador de intención.                             |

### 1.2 Visión por Computadora (Tabla 5)
| ID | Requerimiento | Estado | Observación |
| :--- | :--- | :--- | :--- |
| **RF-22** | Segmentar comprimido | **Cumplido** | `pastillas_detector.py` aísla el comprimido restando la máscara de la base. |
| **RF-23** | Recibir color objetivo | **Cumplido** | `COLOR_OBJETIVO` se pasa dinámicamente a los módulos de detección. |
| **RF-24** | Clasificar por color/forma | **Cumplido** | Usa filtros de circularidad > 0.50 y rangos HSV. |
| **RF-25** | Coordenadas Cartesianas | **Cumplido** | El sistema traduce el error en píxeles a pasos de servo proporcionales. |
| **RF-27** | Detectar marcadores maniquí | **Cumplido** | Implementado esquema Dual (Magenta/Naranja) en `detectorBoca.py`. |
| **RF-28** | Correcciones dinámicas | **Cumplido** | Servocontrol Visual (IBVS) activo durante todo el descenso. |
| **RF-30** | Enviar dimensiones reales | **Parcial** | `pastillas2.py` calcula mm, pero `ciclo_completo.py` usa área en píxeles para el seguimiento. |

---

## 2. Requerimientos No Funcionales (RNF)

| ID | Requerimiento | Estado | Observación |
| :--- | :--- | :--- | :--- |
| **RNF-01** | Movimiento en 5 ejes | **Cumplido** | Brazo 5-DOF (Base, Hombro, Codo, Pitch, Roll). |
| **RNF-03** | Velocidad < 250 mm/s | **Cumplido** | El firmware implementa una rampa de 15ms por grado para suavizar el torque. |
| **RNF-04** | Mantener carga ante fallo | **Cumplido** | La pinza mecánica mantiene su posición si se pierde la señal de control. |
| **RNF-06** | Sin bordes afilados | **Cumplido** | Piezas en PETG impresas con bordes redondeados según diseño CAD. |
| **RNF-11** | Latencia < 10ms (Markers) | **No Detectado** | No se ha validado la latencia de sincronización con la diadema EMOTIV en este entorno. |
| **RNF-16** | Procesamiento < 500ms | **Cumplido** | El flujo de video (`get_frame`) y procesamiento operan a ~10-15 FPS. |
| **RNF-18** | Cámara en efector final | **Cumplido** | ESP32-CAM montada directamente en la pinza (*Eye-in-Hand*). |

---

## Hallazgos Críticos para el Trabajo Terminal:
1. **Diferencia de Marcadores:** El documento técnico especifica marcadores verdes para la boca (pág. 116), pero el código usa Magenta/Naranja. Se recomienda actualizar el documento o el código para consistencia.
2. **Ausencia de FSR:** El RF-08 (sensores de contacto) es el único requerimiento de seguridad de hardware que no está integrado en la telemetría actual.
3. **Calibración Dimensional:** Se requiere integrar la lógica de `pastillas2.py` (píxeles a mm) en el ciclo principal para cumplir cabalmente con el RF-30.
