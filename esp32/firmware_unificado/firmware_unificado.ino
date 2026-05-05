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
#define SDA1 15
#define SCL1 4
#define BUTTON_PIN 34

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);
Adafruit_VL53L0X lox = Adafruit_VL53L0X();
Adafruit_MLX90393 mag1 = Adafruit_MLX90393();
Adafruit_MLX90393 mag2 = Adafruit_MLX90393();

#define SERVOMIN  100       
#define SERVOMAX  575 

// Inicializamos en 90 para asegurar que el primer movimiento a HOME sea suave
int angulosActuales[16] = {90, 180, 0, 0, 0, 0, 140, 0, 0, 0, 0, 0, 80, 0, 0, 90};
// VALORES ORIGINALES RESTAURADOS
int angulosHome[16]     = {90, 180, 0, 0, 0, 0, 140, 0, 0, 0, 0, 0, 80, 0, 0, 90};
int retardosSeguros[16] = {15, 20, 20, 20, 20, 20, 25, 20, 20, 20, 20, 20, 1, 2, 20, 15}; 

unsigned long lastSensorTime = 0;
const int sensorInterval = 100; 

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT);
  
  Wire.begin(SDA0, SCL0);
  Wire1.begin(SDA1, SCL1);
  
  pwm.begin();
  pwm.setPWMFreq(60); 

  if (!lox.begin()) Serial.println("ERR:TOF_NOT_FOUND");
  if (!mag1.begin_I2C(0x0C, &Wire)) Serial.println("ERR:MAG1_NOT_FOUND");
  else mag1.setGain(MLX90393_GAIN_1X);
  if (!mag2.begin_I2C(0x0C, &Wire1)) Serial.println("ERR:MAG2_NOT_FOUND");
  else mag2.setGain(MLX90393_GAIN_1X);

  // Mover suavemente a Home al encender (desde la posicion 90 inicial)
  int p[16]; for(int i=0; i<16; i++) p[i] = i;
  moverSimultaneo(p, angulosHome, 16, true);
  
  Serial.println("SYSTEM_READY");
}

void loop() {
  if (digitalRead(BUTTON_PIN) == HIGH) {
    while(Serial.available() > 0) Serial.read(); 
    Serial.println("boton precionado");
    int p[16]; for(int i=0; i<16; i++) p[i] = i;
    moverSimultaneo(p, angulosHome, 16, true);
  } 
  else {
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
    VL53L0X_RangingMeasurementData_t measure;
    lox.rangingTest(&measure, false);
    if (measure.RangeStatus != 4) {
      Serial.print("DIST:"); Serial.println(measure.RangeMilliMeter);
    }
    float mx1, my1, mz1, mx2, my2, mz2;
    if (mag1.readData(&mx1, &my1, &mz1)) {
      Serial.print("MAG1:"); Serial.print(mx1); Serial.print(","); Serial.print(my1); Serial.print(","); Serial.println(mz1);
    }
    if (mag2.readData(&mx2, &my2, &mz2)) {
      Serial.print("MAG2:"); Serial.print(mx2); Serial.print(","); Serial.print(my2); Serial.print(","); Serial.println(mz2);
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
    if (!forzar && digitalRead(BUTTON_PIN) == HIGH) return;
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
