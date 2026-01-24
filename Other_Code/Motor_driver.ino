#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SH110X.h>

#define I2C_ADDR 0x3C
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1

#define RPWM 15
#define LPWM 16

#define POT_PIN 1
#define ADC_MAX 1785        // <<< CALIBRATED MAX
#define MAX_RPM 400

Adafruit_SH1106G display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// Filter variables
float adcFiltered = 0;
const float alpha = 0.2;    // smoothing factor

int powerPercent = 0;
int rpm = 0;

void drawFrame() {
  display.drawRect(0, 0, 128, 64, SH110X_WHITE);
  display.drawLine(0, 12, 128, 12, SH110X_WHITE);
}

void drawPowerBar(int percent) {
  int barWidth = map(percent, 0, 100, 0, 50);
  int barX = 48;
  int barY = 42;

  display.drawRect(barX, barY, 50, 6, SH110X_WHITE);
  display.fillRect(barX, barY, barWidth, 6, SH110X_WHITE);
}

void setup() {
  Serial.begin(115200);

  Wire.begin();
  display.begin(I2C_ADDR, true);
  display.clearDisplay();

  pinMode(POT_PIN, INPUT);
  analogSetAttenuation(ADC_11db);

  adcFiltered = analogRead(POT_PIN); // init filter

  pinMode(RPWM, OUTPUT);
  pinMode(LPWM, OUTPUT);

  // สั่งให้มอเตอร์หยุด
  analogWrite(RPWM, 0);
  analogWrite(LPWM, 0);

  digitalWrite(RPWM, LOW);
}

void loop() {
   // เร่งความเร็ว หมุนไปด้านหน้า

  // === READ ADC ===
  int adcRaw = analogRead(POT_PIN);

  // === LOW-PASS FILTER ===
  adcFiltered = adcFiltered * (1.0 - alpha) + adcRaw * alpha;

  // === MAP TO POWER % ===
  powerPercent = map((int)adcFiltered, 0, ADC_MAX, 100, 0);
  powerPercent = constrain(powerPercent, 0, 100);
  analogWrite(LPWM, map(powerPercent, 0, 100, 0, 255));

  // === MAP TO RPM ===
  rpm = map(powerPercent, 0, 100, 0, MAX_RPM);

  // === SERIAL DEBUG ===
  Serial.print("ADC raw: ");
  Serial.print(adcRaw);
  Serial.print(" | ADC filt: ");
  Serial.print((int)adcFiltered);
  Serial.print(" | Power: ");
  Serial.print(powerPercent);
  Serial.print("% | RPM: ");
  Serial.println(rpm);

  // === OLED UI ===
  display.clearDisplay();

  drawFrame();

  // Title
  display.setTextSize(1);
  display.setTextColor(SH110X_WHITE);
  display.setCursor(6, 3);
  display.print("MOTOR CONTROL UNIT");

  // RPM
  display.setTextSize(2);
  display.setCursor(42, 18);
  display.print(rpm);

  display.setTextSize(1);
  display.setCursor(52, 34);
  display.print("RPM");

  // Power bar
  display.setCursor(6, 42);
  display.print("POWER");

  drawPowerBar(powerPercent);

  display.setCursor(100, 42);
  if (powerPercent < 10) display.print(" ");
  if (powerPercent < 100) display.print(" ");
  display.print(powerPercent);
  display.print("%");

  // Status
  display.setCursor(6, 54);
  display.print("STATUS : ACTIVE");

  display.display();
  delay(40);   // POV-safe refresh
}
