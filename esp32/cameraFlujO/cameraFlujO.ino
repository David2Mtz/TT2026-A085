#include "esp_camera.h"

// Pines para AI-Thinker
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22
#define FLASH_GPIO_NUM     4

const int freq = 5000;
const int ledResolution = 8;
sensor_t * s; // Puntero para ajustes del sensor

void setup() {
  Serial.begin(460800); 

  ledcAttach(FLASH_GPIO_NUM, freq, ledResolution);
  ledcWrite(FLASH_GPIO_NUM, 0);

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 12; // Calidad mejorada para detección
  config.fb_count = 1;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) { ESP.restart(); }

  s = esp_camera_sensor_get();
  // Bloqueo de controles automáticos para visión artificial estable
  s->set_gain_ctrl(s, 0);      // 0 = Ganancia manual
  s->set_agc_gain(s, 0);       // Ganancia al mínimo (0-30)
  s->set_exposure_ctrl(s, 0);       // 0 = Exposición manual (CRÍTICO)
  
  s->set_aec_value(s, 300);      // Valor inicial estándar
  
  s->set_sharpness(s, 2);

  s->set_awb_gain(s, 1);    
  s->set_raw_gma(s, 1);

  s->set_saturation(s, 2);
  s->set_contrast(s, 1);

  s->set_whitebal(s, 0);       // Habilita el balance de blancos automático
  s->set_wb_mode(s, 1);
}

void loop() {
  if (Serial.available() > 0) {
    char comando = Serial.read();
    
    if (comando == 'R') {
      while(Serial.available() > 0) Serial.read();
      camera_fb_t * fb = esp_camera_fb_get();
      if (!fb) return;
      Serial.write((const uint8_t*)"IMG:", 4);
      uint32_t image_len = fb->len;
      Serial.write((const uint8_t*)&image_len, 4);
      Serial.write(fb->buf, fb->len);
      Serial.flush();
      esp_camera_fb_return(fb);
    } 
    else if (comando == 'L') {
      unsigned long start = millis();
      while (Serial.available() == 0 && (millis() - start < 50));
      if (Serial.available() > 0) {
        ledcWrite(FLASH_GPIO_NUM, Serial.read());
      }
    }
    else if (comando == 'E') { // Comando para Exposición (2 bytes)
      unsigned long start = millis();
      while (Serial.available() < 2 && (millis() - start < 100));
      if (Serial.available() >= 2) {
        uint8_t msb = Serial.read();
        uint8_t lsb = Serial.read();
        int val = (msb << 8) | lsb;
        s->set_aec_value(s, constrain(val, 0, 1200));
      }
    }
  }
}