# src/test_propioceptivo.py
import sys
import os
import time
import cv2 
import numpy as np
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.arm_controller import ArmController

load_dotenv()

def main():
    print("\n" + "="*80)
    print("=== HERRAMIENTA DE CALIBRACIÓN: IMPACTO Y PRESENCIA ===")
    print("="*80)
    print("Controles:")
    print(" [n]: Siguiente estado cinemático")
    print(" [c]: Cerrar pinza y fijar BASELINE (con objeto)")
    print(" [o]: Abrir pinza y resetear alarmas")
    print(" [+]: Aumentar Umbral Colisión | [-]: Disminuir Umbral Colisión")
    print(" [q]: Salir")
    print("="*80 + "\n")
    
    puerto = os.getenv('PUERTO_BRAZO', '/dev/ttyUSB0')
    try:
        brazo = ArmController(puerto=puerto, baudios=115200)
    except Exception as e:
        print(f"[ERROR] {e}")
        return

    estados = ["HOME", "OBSERVACION", "PRE_RECOLECCION", "OBSERVACION_MANIQUI", "ENTREGA"]
    idx_est = 0

    try:
        cv2.imshow("Calibrador Magnético", np.zeros((100, 500, 3), dtype=np.uint8))

        while True:
            est_nom = estados[idx_est]
            est_p = brazo.estado_pinza
            m = brazo.mag1
            norma = (m[0]**2 + m[1]**2 + m[2]**2)**0.5
            
            # Datos del evaluador
            delta = brazo.evaluador_agarre.ultimo_delta
            thr = brazo.evaluador_agarre.umbral_colision
            tol = brazo.evaluador_agarre.umbral_tolerancia

            # Alarma visual en consola
            color_p = "\033[92m" # Verde
            if est_p == "COLISION": color_p = "\033[91m" # Rojo
            elif est_p == "VACIA": color_p = "\033[93m" # Amarillo
            
            status = (
                f"\rESTADO: {est_nom:<15} | "
                f"PINZA: {color_p}{est_p:<10}\033[0m | "
                f"DELTA: {delta:>4.1f} / THR: {thr:>2.0f} | "
                f"NORM: {norma:>6.1f}"
            )
            sys.stdout.write(status)
            sys.stdout.flush()

            key = cv2.waitKey(50) & 0xFF
            if key == ord('q'): break
            
            # --- AJUSTE DE UMBRALES ---
            if key == ord('+'):
                brazo.evaluador_agarre.umbral_colision += 1
                print(f"\n[CONFIG] Umbral de colisión subido a: {brazo.evaluador_agarre.umbral_colision}")
            elif key == ord('-'):
                brazo.evaluador_agarre.umbral_colision = max(1, brazo.evaluador_agarre.umbral_colision - 1)
                print(f"\n[CONFIG] Umbral de colisión bajado a: {brazo.evaluador_agarre.umbral_colision}")

            # --- MOVIMIENTO ---
            if key == ord('n'):
                idx_est = (idx_est + 1) % len(estados)
                nombre_estado = estados[idx_est]
                print(f"\n[MOVIMIENTO] Moviendo a {nombre_estado}...")
                
                # FILTRADO DE PINZA: Obtenemos los movimientos pero quitamos el pin 12
                # para que el estado de la pinza sea manual durante este test.
                movimientos_sucios = brazo.evaluador_agarre.compensacion_estado.keys() # Solo nombres
                from constants.posiciones import POSICIONES
                if nombre_estado in POSICIONES:
                    # Crear lista de movimientos excluyendo el Pin 12
                    movs_filtrados = [(p, a) for p, a in POSICIONES[nombre_estado] if p != 12]
                    brazo.mover_tiempo(movs_filtrados, esperar=True)
                    # Actualizar el nombre del estado en el evaluador para la compensación
                    brazo.nombre_estado_actual = nombre_estado

            # --- ACCIONES PINZA ---
            if key == ord('c'):
                print("\n[CONTROL] Cerrando pinza...")
                brazo.mover_tiempo([(12, 0)], forzar=True, esperar=True)
                time.sleep(1.0)
                m_act = brazo.mag1
                brazo.evaluador_agarre.capturar_baseline(m_act[0], m_act[1], m_act[2])

            if key == ord('o'):
                print("\n[CONTROL] Abriendo pinza y reseteando alarmas...")
                brazo.mover_tiempo([(12, 80)], forzar=True, esperar=True)
                # Resetear pero mantener el baseline para ver si detecta vacía al abrir
                brazo.evaluador_agarre.hubo_colision = False
                brazo.evaluador_agarre.ultimo_delta = 0.0

    except KeyboardInterrupt: pass
    finally:
        if 'brazo' in locals(): brazo.cerrar()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
