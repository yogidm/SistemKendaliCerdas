# SistemKendaliCerdas
---


# Fuzzy Logic ESP32 dengan DHT11, Motor DC, dan LED Indikator

Proyek ini menggunakan **ESP32** untuk mengimplementasikan logika fuzzy sederhana dalam mengontrol kecepatan motor DC (sebagai kipas angin) berdasarkan suhu yang dibaca dari sensor **DHT11**. Selain itu, terdapat indikator LED (merah, kuning, hijau) yang menunjukkan kondisi suhu dingin, hangat, atau panas.

---

## Dasar Teori

### 1. Logika Fuzzy
Logika fuzzy merupakan metode pengambilan keputusan yang memungkinkan nilai berada di antara benar (1) dan salah (0). Tidak hanya biner, tetapi mendukung derajat keanggotaan (membership function) antara 0 sampai 1. Hal ini sesuai dengan kondisi dunia nyata yang bersifat tidak pasti.

Pada sistem ini:
- **Input**: Suhu dari sensor DHT11.
- **Output**: Kecepatan motor DC (PWM) dan status LED.

### 2. Membership Function
Suhu dibagi menjadi tiga himpunan fuzzy:
- **Dingin**: 20°C - 25°C
- **Hangat**: 25°C - 30°C
- **Panas**: >30°C

Output berupa duty cycle PWM motor:
- **Dingin** -> Motor mati, LED hijau menyala
- **Hangat** -> Motor putar sedang, LED kuning menyala
- **Panas** -> Motor putar cepat, LED merah menyala

### 3. Transistor TIP41 sebagai Driver Motor
Transistor TIP41 digunakan sebagai **saklar elektronik** dan **penguat arus**. ESP32 mengeluarkan sinyal PWM ke basis transistor melalui resistor. Motor terhubung pada kolektor, dan emitter ke ground. Dioda flyback dipasang paralel motor untuk mencegah tegangan induksi balik yang dapat merusak komponen.

---

## Wiring

```text
ESP32                Komponen
-------------------------------------------------
3V3                  VCC DHT11
GND                  GND DHT11
GPIO 4               DATA DHT11 (dengan resistor pull-up 10k ke 3V3)

GPIO 5 (PWM CH0)     Resistor 1kÎ© --> Basis TIP41
GND                  Emitter TIP41
Motor DC (+)         +5V / +12V (sesuai motor)
Motor DC (-)         Kolektor TIP41
Dioda 1N4007         Katoda ke +V Motor, Anoda ke Kolektor TIP41 (flyback diode)

GPIO 15              LED Hijau (+) --> resistor 220Î© --> GND
GPIO 2               LED Kuning (+) --> resistor 220Î© --> GND
GPIO 18              LED Merah (+) --> resistor 220Î© --> GND

ESP32 GND ----------- GND Power Motor (wajib common ground)
```

---

## Contoh Kode Arduino (ESP32)

```cpp
#include <DHT.h>

#define DHTPIN 4
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

#define LED_HIJAU 15
#define LED_KUNING 2
#define LED_MERAH 18
#define MOTOR_PWM 5

void setup() {
  Serial.begin(115200);
  dht.begin();

  pinMode(LED_HIJAU, OUTPUT);
  pinMode(LED_KUNING, OUTPUT);
  pinMode(LED_MERAH, OUTPUT);
  ledcSetup(0, 5000, 8);
  ledcAttachPin(MOTOR_PWM, 0);
}

void loop() {
  float suhu = dht.readTemperature();
  if (isnan(suhu)) {
    Serial.println("Gagal membaca sensor DHT11!");
    return;
  }

  int pwm = 0;
  digitalWrite(LED_HIJAU, LOW);
  digitalWrite(LED_KUNING, LOW);
  digitalWrite(LED_MERAH, LOW);

  if (suhu <= 25) {
    pwm = 0;
    digitalWrite(LED_HIJAU, HIGH);
  } else if (suhu > 25 && suhu <= 30) {
    pwm = 128;
    digitalWrite(LED_KUNING, HIGH);
  } else {
    pwm = 255;
    digitalWrite(LED_MERAH, HIGH);
  }

  ledcWrite(0, pwm);

  Serial.print("Suhu: ");
  Serial.print(suhu);
  Serial.print("Â°C | PWM: ");
  Serial.println(pwm);
  delay(2000);
}
```

---

## Catatan Teknis
- Gunakan adaptor 5V/12V terpisah untuk motor.
- Pastikan **common ground** antara ESP32 dan sumber motor.
- Gunakan resistor basis 1kÎ© untuk TIP41.
- Pasang **dioda flyback** (1N4007/1N5819) untuk melindungi transistor.

---

## Lisensi
Proyek ini bersifat open-source dan bebas digunakan untuk pembelajaran maupun pengembangan lebih lanjut.
