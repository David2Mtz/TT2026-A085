#Importing the required dependencies
import cv2
import dlib
import imutils
import time
from scipy.spatial import distance as dist
from imutils import face_utils

# --------- Variables Globales de Configuración ------- #
VENTANA_TIEMPO = 2.0  # Segundos para la ventana de tiempo
PARPADEOS_REQUERIDOS = 3
blink_timestamps = [] # Lista para almacenar los momentos de cada parpadeo
alerta_terminal_impresa = False  # <--- NUEVA VARIABLE DE ESTADO

cam = cv2.VideoCapture(0)

def calculate_EAR(eye) :
    y1 = dist.euclidean(eye[1] , eye[5])
    y2 = dist.euclidean(eye[2] , eye[4])
    x1 = dist.euclidean(eye[0],eye[3])
    EAR = (y1+y2) / x1
    return EAR

def mark_eyeLandmark(img , eyes):
    for eye in eyes:
        pt1,pt2 = (eye[1] , eye[5])
        pt3,pt4 = (eye[0],eye[3])
        cv2.line(img,pt1,pt2,(200,00,0),2)
        cv2.line(img, pt3, pt4, (200, 0, 0), 2)
    return img

#---------Variables de detección-------#
blink_thresh = 0.5
succ_frame = 2
count_frame = 0

(L_start, L_end) = face_utils.FACIAL_LANDMARKS_IDXS["left_eye"]
(R_start, R_end) = face_utils.FACIAL_LANDMARKS_IDXS['right_eye']

detector = dlib.get_frontal_face_detector()
landmark_predict = dlib.shape_predictor('Model/shape_predictor_68_face_landmarks.dat')

while 1 :
    if cam.get(cv2.CAP_PROP_POS_FRAMES) == cam.get(cv2.CAP_PROP_FRAME_COUNT) :
        cam.set(cv2.CAP_PROP_POS_FRAMES, 0)

    _, frame = cam.read()
    if frame is None: break
    frame = imutils.resize(frame, width=640)
    img = frame.copy()
    
    # --- LIMPIEZA DE TIEMPOS CADA FRAME ---
    ahora = time.time()
    blink_timestamps = [t for t in blink_timestamps if ahora - t <= VENTANA_TIEMPO]
    
    img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = detector(img_gray)

    for face in faces :
        shape = landmark_predict(img_gray, face)
        shape = face_utils.shape_to_np(shape)
        
        lefteye = shape[L_start : L_end]
        righteye = shape[R_start:R_end]
        avg = (calculate_EAR(lefteye) + calculate_EAR(righteye)) / 2

        # Lógica de detección de parpadeo (Corregida para evitar conteos dobles)
        if avg < blink_thresh:
            count_frame += 1
        else:
            if count_frame >= succ_frame:
                blink_timestamps.append(ahora)
                print(f"Parpadeo detectado ({len(blink_timestamps)} en ventana)")
            count_frame = 0 # Reiniciamos siempre al abrir los ojos

        # Dibujar puntos
        for lm in shape:
            cv2.circle(frame, (lm), 2, (10, 2, 200), -1)
        img = frame.copy()
        img = mark_eyeLandmark(img, [lefteye, righteye])

        # --- VERIFICACIÓN DE INTENCIÓN ---
        if len(blink_timestamps) >= PARPADEOS_REQUERIDOS:
            texto = "Confirmacion de intencion"
            
            # 1. Terminal: Solo imprime la primera vez que se cumple la condición
            if not alerta_terminal_impresa:
                print(f"\n>>> {texto} <<<\n")
                alerta_terminal_impresa = True
            
            # 2. Ventana: Se mantiene (como pediste)
            font = cv2.FONT_HERSHEY_DUPLEX
            escala = 1
            espesor = 2
            tamano_texto = cv2.getTextSize(texto, font, escala, espesor)[0]
            text_x = (img.shape[1] - tamano_texto[0]) // 2
            text_y = img.shape[0] - 20
            cv2.putText(img, texto, (text_x, text_y), font, escala, (0, 0, 255), espesor)
            
        else:
            # Si hay menos de 3 parpadeos, reseteamos el interruptor para la próxima vez
            alerta_terminal_impresa = False

    cv2.imshow("Video", img)
    if cv2.waitKey(1) & 0xFF == ord('q') :
        break

cam.release()
cv2.destroyAllWindows()