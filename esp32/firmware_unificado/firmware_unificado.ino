#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include "Adafruit_VL53L0X.h"
#include <Adafruit_MLX90393.h>

/**
 * FIRMWARE UNIFICADO v5 - CORREGIDO
 * - Valores de HOME restaurados a los originales del usuario.
 * - Pin 13: Soporta hasta 270 grados.
 * - Suavidad: Movimiento controlado en arranque y paro.
 */

#define SDA0 21
#define SCL0 22
#define BUTTON_PIN 34

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);
Adafruit_VL53L0X lox = Adafruit_VL53L0X();
Adafruit_MLX90393 mag1 = Adafruit_MLX90393();

#define SERVOMIN  100       
#define SERVOMAX  575 

// Estos valores son tu posición de HOME
int angulosActuales[16] = {90, 180, 0, 0, 0, 0, 140, 0, 0, 0, 0, 0, 80, 0, 0, 90};
int retardosSeguros[16] = {7, 10, 10, 10, 10, 10, 12, 10, 10, 10, 10, 10, 7, 4, 10, 10}; 

unsigned long lastSensorTime = 0;
const int sensorInterval = 100; 

// Banderas de estado de hardware para evitar crashes
bool hasToF = false;
bool hasMag1 = false;

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT);
  
  Wire.begin(SDA0, SCL0);
  
  pwm.begin();
  pwm.setPWMFreq(60); 

  // Inicialización controlada de sensores (con reintentos para ToF)
  for (int i = 0; i < 3; i++) {
    if (lox.begin()) {
      hasToF = true;
      break;
    }
    delay(200);
  }
  if (!hasToF) Serial.println("ERR:TOF_NOT_FOUND");

  if (mag1.begin_I2C(0x0C, &Wire)) {
    mag1.setGain(MLX90393_GAIN_1X);
    hasMag1 = true;
  } else Serial.println("ERR:MAG1_NOT_FOUND");

  // --- POSICIONAMIENTO INICIAL DIRECTO (HOME) ---
  // Enviamos los pulsos de inmediato para que el robot se fije al encender
  for (int i = 0; i < 16; i++) {
    int pulso = map(angulosActuales[i], 0, 180, SERVOMIN, SERVOMAX);
    pwm.setPWM(i, 0, pulso);
    // Sincronización del pin 2 (espejo del pin 1)
    if (i == 1) pwm.setPWM(2, 0, (SERVOMIN + SERVOMAX) - pulso);
  }
  
  Serial.println("SYSTEM_READY");
}

bool lastButtonState = false;

void loop() {
  bool currentButtonState = (digitalRead(BUTTON_PIN) == HIGH);
  
  if (currentButtonState) {
    if (!lastButtonState) {
      Serial.println("boton precionado");
      lastButtonState = true;
    }
    // Limpiar buffer y forzar HOME si se presiona el botón
    while(Serial.available() > 0) Serial.read(); 
    for (int i = 0; i < 16; i++) {
      int pulso = map(angulosActuales[i], 0, 180, SERVOMIN, SERVOMAX);
      pwm.setPWM(i, 0, pulso);
      if (i == 1) pwm.setPWM(2, 0, (SERVOMIN + SERVOMAX) - pulso);
    }
  } 
  else {
    if (lastButtonState) {
      Serial.println("boton liberado");
      lastButtonState = false;
    }
    if (Serial.available() > 0) {
      if (Serial.peek() == '$') {
        Serial.read();
        String comando = Serial.readStringUntil('\n');
        if (procesarComando(comando)) {
          Serial.println("OK"); 
          while(Serial.available() > 0) Serial.read();
        }
      } else {
        Serial.read();
      }
    }
  }

  unsigned long currentMillis = millis();
  if (currentMillis - lastSensorTime >= sensorInterval) {
    // Solo leer si el sensor está presente (evita divisiones por cero/crashes)
    if (hasToF) {
      VL53L0X_RangingMeasurementData_t measure;
      lox.rangingTest(&measure, false);
      
      Serial.print("DIST:"); 
      if (measure.RangeStatus == 4) {
        Serial.println("999"); // Usar 999 como indicador de fuera de rango
      } else {
        Serial.println(measure.RangeMilliMeter);
      }
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
      
      int limite = (pin == 13) ? 270 : 180;
      if (pin >= 0 && pin <= 15 && ang >= 0 && ang <= limite) {
        pines[contador] = pin; destinos[contador] = ang; contador++;
      }
    }
  }
  if (contador > 0) {
    moverSimultaneo(pines, destinos, contador, false);
    return true;
  }
  return false;
}

void moverSimultaneo(int pines[], int destinos[], int cantidad, bool forzar) {
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
    if (!forzar && digitalRead(BUTTON_PIN) == HIGH) {
      Serial.println("boton precionado");
      return;
    }
    if (forzar) {
      while(Serial.available() > 0) Serial.read();
      if (p % 10 == 0) Serial.println("boton precionado");
    }
    for (int i = 0; i < cantidad; i++) {
      int pin = pines[i];
      int pulsoActual = pulsosInicio[i] + ((pulsosFin[i] - pulsosInicio[i]) * p) / numPasos;
      pwm.setPWM(pin, 0, pulsoActual);
      if (pin == 1) pwm.setPWM(2, 0, (SERVOMIN + SERVOMAX) - pulsoActual);
    }
    delay(pasoMs); 
  }

  for (int i = 0; i < cantidad; i++) {
    angulosActuales[pines[i]] = destinos[i];
    if (pines[i] == 1) angulosActuales[2] = 180 - destinos[i];
  }
}
