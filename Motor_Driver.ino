// Motor PWM pins
#define RPWM 5
#define LPWM 6

int pwmPercent = 0;
int pwmValue = 0;
int rpm = 0;

void setup() {
  pinMode(RPWM, OUTPUT);
  pinMode(LPWM, OUTPUT);

  pinMode(11, OUTPUT);
  pinMode(10, OUTPUT);

  digitalWrite(11, HIGH);
  digitalWrite(10, HIGH);

  analogWrite(RPWM, 0);
  analogWrite(LPWM, 0);

  Serial.begin(9600);
  Serial.println("Enter PWM percentage (0-100):");
}

void loop() {
  if (Serial.available() > 0) {
    pwmPercent = Serial.parseInt();  // Read percentage

    // Clear serial buffer
    while (Serial.available()) {
      Serial.read();
    }

    // Clamp value
    if (pwmPercent < 0) pwmPercent = 0;
    if (pwmPercent > 100) pwmPercent = 100;

    // Convert percent to PWM (0–255)
    pwmValue = map(pwmPercent, 0, 100, 0, 255);

    // Estimate RPM
    rpm = (pwmPercent * 3000) / 100;

    // One direction only
    analogWrite(RPWM, 0);
    analogWrite(LPWM, pwmValue);

    // Print result
    Serial.println("--------------------");
    Serial.print("PWM Percent : ");
    Serial.print(pwmPercent);
    Serial.println(" %");

    Serial.print("PWM Value   : ");
    Serial.println(pwmValue);

    Serial.print("Estimated RPM : ");
    Serial.print(rpm);
    Serial.println(" RPM");
  }
}
