#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

/**
 * TEST DE PARO DE EMERGENCIA INTEGRADO v3
 * - Botón presionado: Limpia buffer serial y regresa a HOME inmediatamente.
 * - Botón libre: Procesa comandos $pin,angulo;
 */

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);

#define BUTTON_PIN 34
#define SERVOMIN  100       
#define SERVOMAX  575 

int angulosActuales[16] = {90, 180, 0, 0, 0, 0, 140, 0, 0, 0, 0, 0, 80, 0, 0, 90};
int angulosHome[16]     = {90, 180, 0, 0, 0, 0, 140, 0, 0, 0, 0, 0, 80, 0, 0, 90};
int retardosSeguros[16] = {15, 20, 20, 20, 20, 20, 25, 20, 20, 20, 20, 20, 0, 20, 20, 15}; 

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT);
  
  Wire.begin(21, 22);
  pwm.begin();
  pwm.setPWMFreq(60);

  Serial.println("SYSTEM_READY (Paro corregido)");
}

void loop() {
  // --- LÓGICA DE PARO DE EMERGENCIA ---
  if (digitalRead(BUTTON_PIN) == HIGH) {
    Serial.println("boton precionado");
    
    // 1. Limpiar buffer serial
    while(Serial.available() > 0) Serial.read(); 
    
    // 2. Regreso directo a HOME
    for (int i = 0; i < 16; i++) {
      int pulso;
      if (i == 2) { 
        pulso = (SERVOMIN + SERVOMAX) - map(angulosHome[1], 0, 180, SERVOMIN, SERVOMAX);
      } else {
        pulso = map(angulosHome[i], 0, 180, SERVOMIN, SERVOMAX);
      }
      pwm.setPWM(i, 0, pulso);
      angulosActuales[i] = angulosHome[i];
    }
    angulosActuales[2] = 180 - angulosHome[1];
    
    delay(50);
  } 
  else {
    // --- LÓGICA DE COMANDOS SERIALES ---
    if (Serial.available() > 0) {
      if (Serial.peek() == '$') {
        Serial.read(); 
        String comando = Serial.readStringUntil('\n');
        if (procesarComando(comando)) {
           Serial.println("OK");
        }
      } else {
        Serial.read(); 
      }
    }
  }
}

bool procesarComando(String comando) {
  comando.trim();
  int pines[16], destinos[16], contador = 0;
  int startIndex = 0;

  while (startIndex < comando.length() && contador < 16) {
    int sepIndex = comando.indexOf(';', startIndex);
    String parStr = (sepIndex == -1) ? comando.substring(startIndex) : comando.substring(startIndex, sepIndex);
    startIndex = (sepIndex == -1) ? comando.length() : sepIndex + 1;

    int commaIndex = parStr.indexOf(',');
    if (commaIndex != -1) {
      int pin = parStr.substring(0, commaIndex).toInt();
      int ang = parStr.substring(commaIndex + 1).toInt();
      if (pin >= 0 && pin <= 15 && ang >= 0 && ang <= 180) {
        pines[contador] = pin;
        destinos[contador] = ang;
        contador++;
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
    // ABORTO: Si se presiona el botón durante un movimiento normal, salir
    if (digitalRead(BUTTON_PIN) == HIGH) return; 

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
