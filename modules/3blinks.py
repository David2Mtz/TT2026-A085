#Importing the required dependencies
import cv2                                     #for video rendering
import dlib                                    #for face and landmark detection
import imutils
import time                                    # --- NUEVA IMPORTACIÓN ---
from scipy.spatial import distance as dist     #for calculating dist b/w the eye landmarks
from imutils import face_utils                 #to get the landmark ids of the left and right eyes

# --------- Variables Globales de Configuración ------- #
VENTANA_TIEMPO = 2.0  # Segundos para la ventana de tiempo
PARPADEOS_REQUERIDOS = 3
blink_timestamps = [] # Lista para almacenar los momentos de cada parpadeo

cam = cv2.VideoCapture(0)

#------defining a function to calulate the EAR-----------#
def calculate_EAR(eye) :
    y1 = dist.euclidean(eye[1] , eye[5])
    y2 = dist.euclidean(eye[2] , eye[4])
    x1 = dist.euclidean(eye[0],eye[3])
    EAR = (y1+y2) / x1
    return EAR

#---------Mark the eye landmarks-------#
def mark_eyeLandmark(img , eyes):
    for eye in eyes:
        # Línea horizontal
        cv2.line(img, tuple(eye[0]), tuple(eye[3]), (200, 0, 0), 2)

        # Calcular el punto medio superior (entre 1 y 2)
        top_mid_x = int((eye[1][0] + eye[2][0]) / 2)
        top_mid_y = int((eye[1][1] + eye[2][1]) / 2)

        # Calcular el punto medio inferior (entre 5 y 4)
        bottom_mid_x = int((eye[5][0] + eye[4][0]) / 2)
        bottom_mid_y = int((eye[5][1] + eye[4][1]) / 2)

        # Línea vertical central
        cv2.line(img, (top_mid_x, top_mid_y), (bottom_mid_x, bottom_mid_y), (200, 0, 0), 2)
    return img

#---------Variables de detección-------#
blink_thresh = 0.5
succ_frame = 2
count_frame = 0

#-------Eye landmarks------#
(L_start, L_end) = face_utils.FACIAL_LANDMARKS_IDXS["left_eye"]
(R_start, R_end) = face_utils.FACIAL_LANDMARKS_IDXS['right_eye']

#------Initializing the Models---------#
detector = dlib.get_frontal_face_detector()
# Asegúrate de tener este archivo en la carpeta 'Model/'
landmark_predict = dlib.shape_predictor('Model/shape_predictor_68_face_landmarks.dat')

while 1 :
    if cam.get(cv2.CAP_PROP_POS_FRAMES) == cam.get(cv2.CAP_PROP_FRAME_COUNT) :
        cam.set(cv2.CAP_PROP_POS_FRAMES, 0)

    _, frame = cam.read()
    if frame is None: break
    frame = imutils.resize(frame, width=640)
    img = frame.copy()
    img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = detector(img_gray)

    for face in faces :
        shape = landmark_predict(img_gray, face)
        shape = face_utils.shape_to_np(shape)
        
        lefteye = shape[L_start : L_end]
        righteye = shape[R_start:R_end]

        left_EAR = calculate_EAR(lefteye)
        right_EAR = calculate_EAR(righteye)
        avg = (left_EAR + right_EAR) / 2

        # Lógica de detección de parpadeo
        if avg < blink_thresh:
            count_frame += 1
        else:
            if count_frame >= succ_frame:
                # --- NUEVA LÓGICA DE VENTANA DE TIEMPO ---
                ahora = time.time()
                blink_timestamps.append(ahora)
                # Limpiar timestamps viejos fuera de la ventana
                blink_timestamps = [t for t in blink_timestamps if ahora - t <= VENTANA_TIEMPO]
                
                print(f"Parpadeo detectado. Total en ventana: {len(blink_timestamps)}")
            
            count_frame = 0

        # Dibujar puntos de referencia
        for lm in shape:
            cv2.circle(frame, (lm), 2, (10, 2, 200), -1)
        img = frame.copy()
        img = mark_eyeLandmark(img, [lefteye, righteye])

        # --- VERIFICACIÓN DE INTENCIÓN ---
        if len(blink_timestamps) >= PARPADEOS_REQUERIDOS:
            texto = "Confirmacion de intencion"
            print(texto)
            
            # Cálculo para centrar el texto
            font = cv2.FONT_HERSHEY_DUPLEX
            escala = 1
            espesor = 2
            tamano_texto = cv2.getTextSize(texto, font, escala, espesor)[0]
            
            # Centrado Horizontal: (Ancho_Imagen - Ancho_Texto) / 2
            text_x = (img.shape[1] - tamano_texto[0]) // 2
            # Abajo Verticalmente: Alto_Imagen - Margen
            text_y = img.shape[0] - 20
            
            cv2.putText(img, texto, (text_x, text_y), font, escala, (0, 0, 255), espesor)

    cv2.imshow("Video", img)
    if cv2.waitKey(1) & 0xFF == ord('q') :
        break

cam.release()
cv2.destroyAllWindows()