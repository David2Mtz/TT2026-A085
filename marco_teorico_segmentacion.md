# Marco Teórico: Segmentación de Colores y Detección de Objetos

Este documento contiene la explicación técnica detallada para la sección **2.3.6 Segmentación de colores** del marco teórico, basada en la implementación final de producción.

---

### 2.3.6 Segmentación de colores

Uno de los pasos cruciales es la segmentación de colores. Por medio de esta técnica, podemos lograr la localización del comprimido sólido y de la boca del maniquí. El proceso para la segmentación se describe a continuación:

#### 1. Pastilleros (Detección de Comprimidos)

Para la identificación de los comprimidos sobre los pastilleros, se utiliza una técnica de visión artificial basada en el espacio de color **HSV (Hue, Saturation, Value)**, la cual es más robusta ante variaciones de iluminación que el espacio RGB. El proceso consta de los siguientes pasos:

*   **Segmentación por Rangos HSV:** Se definen rangos específicos para los colores base de los pastilleros (Rojo, Verde, Azul). Mediante la función `cv2.inRange`, se genera una máscara binaria que identifica el área ocupada por el pastillero.
*   **Limpieza Morfológica:** Se aplican operaciones de apertura (`cv2.MORPH_OPEN`) y cierre (`cv2.MORPH_CLOSE`) para eliminar el ruido electrónico y suavizar los contornos de la base.
*   **Sustracción de Región de Interés (ROI):** Una vez identificada la base del pastillero, se genera una máscara de su área total. El sistema realiza una sustracción lógica entre el área total de la base y el área del color base detectado. Los píxeles resultantes representan objetos que se encuentran sobre la base pero que no pertenecen al color de esta (es decir, el comprimido o su sombra).
*   **Filtrado por Circularidad:** Para distinguir el comprimido sólido de sombras irregulares, se calcula el factor de circularidad de cada contorno detectado mediante la siguiente relación:

    Circularidad = (4 * π * Área) / (Perímetro^2)

    *(Nota para Word: Puedes insertar esta fórmula profesionalmente usando el menú Insertar > Ecuación y escribiendo: C=(4\pi*Área)/Perímetro^2)*

#### 2. Boca del maniquí (Identificación de Landmarks)

La localización de la boca del maniquí se realiza mediante una estrategia de **Marcadores de Color Dual**, diseñada para proporcionar una alta precisión sin depender de la detección facial estándar, que puede fallar en maniquíes o condiciones de poca luz.

*   **Marcadores Fluorescentes:** Se utilizan marcadores físicos de colores de alta visibilidad (Magenta/Rosa Neón y Naranja Neón) situados en puntos estratégicos de la boca (comisuras, labio superior e inferior).
*   **Segmentación de Color Dual:** El sistema procesa el frame en el espacio HSV buscando simultáneamente ambos rangos cromáticos. Se combina la detección mediante una operación OR bit a bit (`cv2.bitwise_or`), permitiendo que el sistema sea resistente si uno de los colores se ve ocluido o degradado por la luz.
*   **Máscara de Región de Interés (ROI):** Para optimizar el procesamiento y reducir falsos positivos, se ignora el 10% lateral de la imagen y el 30% inferior, centrando la búsqueda en el área donde se espera encontrar la cara del maniquí.
*   **Agrupamiento (Clustering) y Selección de Landmarks:** De los posibles candidatos detectados, el sistema emplea un algoritmo de agrupamiento para encontrar el conjunto de 4 puntos más compactos y cercanos entre sí. Estos 4 puntos se clasifican automáticamente según sus coordenadas espaciales:
    *   **Eje Y:** El punto más alto se identifica como el labio superior (*Top*) y el más bajo como el inferior (*Bottom*).
    *   **Eje X:** Los puntos intermedios se clasifican como las comisuras izquierda y derecha (*Left/Right Corner*).
*   **Cálculo del Centro de Objetivo:** Finalmente, se calcula el promedio aritmético de las coordenadas de los 4 landmarks para obtener el centro geométrico de la boca, el cual sirve como punto de referencia para el sistema de control del brazo robótico.

---

**Nota:** Esta implementación utiliza la biblioteca **OpenCV** para el procesamiento de imágenes y **NumPy** para el análisis matricial de los datos visuales.
