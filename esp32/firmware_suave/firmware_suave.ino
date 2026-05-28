#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include "Adafruit_VL53L0X.h"
#include <Adafruit_MLX90393.h>

/**
 * FIRMWARE SUAVE v1.3 - TT2026-A085
 * - IMPACT DRIVING: Super-Kick de 18 grados para romper fricción extrema.
 * - INERTIA CANCEL: Fase de frenado para evitar sobre-oscilación.
 * - Sincronizado para control manual de 1 grado.
 */

#define SDA0 21
#define SCL0 22
#define BUTTON_PIN 34

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);
Adafruit_VL53L0X lox = Adafruit_VL53L0X();
Adafruit_MLX90393 mag1 = Adafruit_MLX90393();

#define SERVOMIN  100       
#define SERVOMAX  575 

int angulosActuales[16] = {90, 180, 0, 0, 0, 0, 140, 0, 0, 0, 0, 0, 80, 0, 0, 90};
int retardosSeguros[16] = {50, 10, 10, 10, 10, 10, 12, 10, 10, 10, 10, 10, 7, 4, 10, 10}; 

unsigned long lastSensorTime = 0;
const int sensorInterval = 100; 

bool hasToF = false;
bool hasMag1 = false;

unsigned long lastDitherTime = 0;
bool ditherSide = false;
bool moviendoActual = false; 

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT);
  Wire.begin(SDA0, SCL0);
  Wire.setClock(400000); 
  pwm.begin();
  pwm.setPWMFreq(60); 

  for (int i = 0; i < 3; i++) {
    if (lox.begin()) {
      hasToF = true;
      break;
    }
    delay(200);
  }
  
  if (mag1.begin_I2C(0x0C, &Wire)) {
    mag1.setGain(MLX90393_GAIN_1X);
    hasMag1 = true;
  }

  for (int i = 0; i < 16; i++) {
    int pulso = map(angulosActuales[i], 0, 180, SERVOMIN, SERVOMAX);
    pwm.setPWM(i, 0, pulso);
    if (i == 1) pwm.setPWM(2, 0, (SERVOMIN + SERVOMAX) - pulso);
  }
  Serial.println("SYSTEM_READY");
}

void loop() {
  if (digitalRead(BUTTON_PIN) == HIGH) {
    while(Serial.available() > 0) Serial.read(); 
    for (int i = 0; i < 16; i++) {
      int pulso = map(angulosActuales[i], 0, 180, SERVOMIN, SERVOMAX);
      pwm.setPWM(i, 0, pulso);
    }
  } 
  else {
    if (Serial.available() > 0) {
      if (Serial.peek() == '$') {
        Serial.read();
        String comando = Serial.readStringUntil('\n');
        moviendoActual = true;
        if (procesarComando(comando)) {
          Serial.println("OK"); 
          while(Serial.available() > 0) Serial.read();
        }
        moviendoActual = false;
      } else { Serial.read(); }
    }
  }

  // Dither con más energía (3 ticks) para mantener motor vibrando
  if (!moviendoActual && (millis() - lastDitherTime >= 40)) { 
    lastDitherTime = millis();
    ditherSide = !ditherSide;
    int offset = ditherSide ? 3 : -3;
    int pulsoBase = map(angulosActuales[0], 0, 180, SERVOMIN, SERVOMAX) + offset;
    pwm.setPWM(0, 0, pulsoBase);
  }

  unsigned long currentMillis = millis();
  if (currentMillis - lastSensorTime >= sensorInterval) {
    if (hasToF) {
      VL53L0X_RangingMeasurementData_t measure;
      lox.rangingTest(&measure, false);
      Serial.print("DIST:"); 
      if (measure.RangeStatus == 4) Serial.println("999");
      else Serial.println(measure.RangeMilliMeter);
    }
    float mx, my, mz;
    if (hasMag1 && mag1.readData(&mx, &my, &mz)) {
      Serial.printf("MAG1:%.1f,%.1f,%.1f\n", mx, my, mz);
    }
    lastSensorTime = currentMillis;
  }
}

bool procesarComando(String comando) {
  comando.trim();
  int pines[16], destinos[16], contador = 0, startIndex = 0;
  while (startIndex < comando.length() && contador < 16) {
    int sepIndex = comando.indexOf(';', startIndex);
    String parStr = (sepIndex == -1) ? comando.substring(startIndex) : comando.substring(startIndex, sepIndex);
    startIndex = (sepIndex == -1) ? comando.length() : sepIndex + 1;
    int commaIndex = parStr.indexOf(',');
    if (commaIndex != -1) {
      int pin = parStr.substring(0, commaIndex).toInt();
      int ang = parStr.substring(commaIndex + 1).toInt();
      if (pin >= 0 && pin <= 15) {
        pines[contador] = pin; destinos[contador] = ang; contador++;
      }
    }
  }
  if (contador > 0) {
    moverSimultaneo(pines, destinos, contador);
    return true;
  }
  return false;
}

void moverSimultaneo(int pines[], int destinos[], int cantidad) {
  long tiempoMaximoMs = 0;
  int pulsosInicio[16], pulsosFin[16];

  for (int i = 0; i < cantidad; i++) {
    int pin = pines[i];
    long tReq = abs(destinos[i] - angulosActuales[pin]) * (long)retardosSeguros[pin];
    if (tReq > tiempoMaximoMs) tiempoMaximoMs = tReq;
    pulsosInicio[i] = map(angulosActuales[pin], 0, 180, SERVOMIN, SERVOMAX);
    pulsosFin[i]    = map(destinos[i], 0, 180, SERVOMIN, SERVOMAX);
  }

  if (tiempoMaximoMs == 0) return;

  int pasoMs = 15; 
  int numPasos = tiempoMaximoMs / pasoMs;
  if (numPasos < 1) numPasos = 1;

  for (int p = 1; p <= numPasos; p++) {
    float progresoLineal = (float)p / numPasos;
    float progresoSuave = progresoLineal * progresoLineal * (3.0 - 2.0 * progresoLineal);

    for (int i = 0; i < cantidad; i++) {
      int pin = pines[i];
      int dif = pulsosFin[i] - pulsosInicio[i];
      int pulsoActual = pulsosInicio[i] + (int)(dif * progresoSuave);

      // --- LOGICA DE IMPACT DRIVING (SOLO SERVO 0 - BASE) ---
      if (pin == 0 && abs(dif) > 0) {
          // PASO 1 y 2 (30ms): SUPER KICK - Forzar torque máximo
          if (p <= 2) {
              int direccion = (dif > 0) ? 1 : -1;
              pulsoActual += (direccion * 45); // Kick masivo de 18 grados
          }
          // PASO 3 (15ms): FRENADO ACTIVO - Contra-pulso para detener inercia
          else if (p == 3) {
              int direccion = (dif > 0) ? 1 : -1;
              pulsoActual -= (direccion * 5); // Pequeño jalón hacia atrás
          }
      }
      
      pulsoActual = constrain(pulsoActual, SERVOMIN, SERVOMAX);
      pwm.setPWM(pin, 0, pulsoActual);
      if (pin == 1) pwm.setPWM(2, 0, (SERVOMIN + SERVOMAX) - pulsoActual);
    }
    delay(pasoMs); 
  }

  for (int i = 0; i < cantidad; i++) {
    angulosActuales[pines[i]] = destinos[i];
  }
}
