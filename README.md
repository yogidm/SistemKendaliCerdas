# Sistem Kendali Cerdas
---


# Jobsheet 1: Fuzzy Logic ESP32 dengan DHT11, Motor DC, dan LED Indikator

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

# Jobsheet 2: Smart Dehumidifier dengan Fuzzy Logic

## Dasar Teori

Fuzzy Logic adalah metode komputasi yang meniru cara berpikir manusia dalam menghadapi ketidakpastian. 
Alih-alih hanya menggunakan nilai biner (0 atau 1), fuzzy menggunakan derajat keanggotaan antara 0 hingga 1. 
Dalam sistem dehumidifier cerdas, fuzzy logic dapat digunakan untuk menentukan kecepatan kipas berdasarkan suhu dan kelembapan ruangan.



## Fungsi Keanggotaan

## Suhu (T, °C)

μRendah(T) =
- 1,                   jika T ≤ 22
- (24 − T) / 2,        jika 22 < T < 24
- 0,                   jika T ≥ 24

μSedang(T) =
- 0,                   jika T ≤ 24 atau T ≥ 30
- (T − 24) / 3,        jika 24 < T < 27
- (30 − T) / 3,        jika 27 ≤ T < 30

μTinggi(T) =
- 0,                   jika T ≤ 28
- (T − 28) / 2,        jika 28 < T < 30
- 1,                   jika T ≥ 30

---

## Kelembapan (H, %RH)

μKering(H) =
- 1,                   jika H ≤ 35
- (40 − H) / 5,        jika 35 < H < 40
- 0,                   jika H ≥ 40

μNyaman(H) =
- 0,                   jika H ≤ 40 atau H ≥ 60
- (H − 40) / 10,       jika 40 < H < 50
- (60 − H) / 10,       jika 50 ≤ H < 60

μLembap(H) =
- 0,                   jika H ≤ 55
- (H − 55) / 5,        jika 55 < H < 60
- 1,                   jika H ≥ 60

---

## Output (Kecepatan Kipas → Nilai PWM 0–255)

- **Lambat** = 80  
- **Sedang** = 160  
- **Cepat** = 255  

---

## Rule Base (9 Aturan)

1. Rendah & Kering → Lambat  
2. Rendah & Nyaman → Lambat  
3. Rendah & Lembap → Sedang  
4. Sedang & Kering → Lambat  
5. Sedang & Nyaman → Sedang  
6. Sedang & Lembap → Cepat  
7. Tinggi & Kering → Sedang  
8. Tinggi & Nyaman → Cepat  
9. Tinggi & Lembap → Cepat  

---

## Perhitungan Contoh

Metode agregasi rule:  
- Evaluasi kondisi (AND = min)  
- Defuzzifikasi: weighted average (centroid sederhana)  

Output = ( Σ μrule × z ) / ( Σ μrule )

---

### Skenario 1 — Dingin & Kering

- Input: Suhu rendah, kelembapan kering  
- Fuzzifikasi: hanya Rendah & Kering aktif → μ = 1  
- Output: Lambat (80)  

Output = (1 × 80) / 1 = 80  

**Hasil: PWM = 80 (Lambat)**  

---

### Skenario 2 — Mixed (dua rule aktif)

Contoh: Suhu sedang, kelembapan 58%  

Fuzzifikasi kelembapan:  
- μNyaman(58) = (60 − 58) / 10 = 0.2  
- μLembap(58) = (58 − 55) / 5 = 0.6  

Rule aktif:  
- Sedang & Nyaman → 0.2 → Output = Sedang (160)  
- Sedang & Lembap → 0.6 → Output = Cepat (255)  

Defuzzifikasi:  
Output = (0.2×160 + 0.6×255) / (0.2+0.6)  
Output = (32 + 153) / 0.8 = 185 / 0.8 ≈ 231.25  

**Hasil: PWM ≈ 231 (dekat Cepat)**  

---

### Skenario 3 — Panas & Lembap

- Input: Suhu tinggi, kelembapan lembap  
- Fuzzifikasi: μ = 1  
- Rule aktif: Tinggi & Lembap → Cepat (255)  

Output = (1 × 255) / 1 = 255  

**Hasil: PWM = 255 (Cepat penuh)**

---

### Variabel Fuzzy

- **Input 1: Suhu (°C)**
  - Rendah
  - Sedang
  - Tinggi

- **Input 2: Kelembapan (%)**
  - Kering
  - Normal
  - Lembap

- **Output: Kecepatan Kipas (PWM 0-255)**
  - Lambat
  - Sedang
  - Cepat

### Fungsi Keanggotaan (Contoh)

Suhu (°C):

- Rendah: μ = 1 pada ≤ 20, menurun linier ke 0 pada 25

- Sedang: μ = 0 pada 20 dan 30, puncak 1 pada 25

- Tinggi: μ = 0 pada 25, meningkat linier hingga 1 pada ≥ 30


Kelembapan (%):

- Kering: μ = 1 pada ≤ 40, menurun ke 0 pada 50

- Normal: μ = 0 pada 40 dan 60, puncak 1 pada 50

- Lembap: μ = 0 pada 50, meningkat ke 1 pada ≥ 60

---

## Basis Aturan (Rule Base)

| Rule | Suhu | Kelembapan | Output |
|------|------|------------|--------|
| 1    | Rendah | Kering   | Lambat |
| 2    | Rendah | Normal   | Lambat |
| 3    | Rendah | Lembap   | Sedang |
| 4    | Sedang | Kering   | Lambat |
| 5    | Sedang | Normal   | Sedang |
| 6    | Sedang | Lembap   | Cepat  |
| 7    | Tinggi | Kering   | Sedang |
| 8    | Tinggi | Normal   | Cepat  |
| 9    | Tinggi | Lembap   | Cepat  |

---

## Perhitungan Fuzzy (Contoh)

Misalkan hasil sensor: Suhu = 28 °C, Kelembapan = 65%

1. Fuzzyfikasi

- Suhu 28 °C → Sedang (0.4), Tinggi (0.6)
- Kelembapan 65% → Normal (0.0), Lembap (1.0)

2. Inferensi (Rule Matching)

- Rule 6: Sedang ∧ Lembap → min(0.4, 1.0) = 0.4 → Output Cepat
- Rule 9: Tinggi ∧ Lembap → min(0.6, 1.0) = 0.6 → Output Cepat

3. Agregasi

- Cepat mendapat keanggotaan max(0.4, 0.6) = 0.6

4. Defuzzyfikasi (Metode Centroid)

- Cepat ≈ 255 × 0.6 = 153 (mendekati kecepatan kipas sedang–cepat)

Hasil: Kipas akan berputar dengan PWM ≈ 153.


---

## Implementasi ESP32 + DHT11 + Motor DC

### Alat dan Bahan
- ESP32
- Sensor DHT11
- Kipas DC + driver TIP41
- Breadboard dan kabel jumper
- Power supply sesuai kebutuhan

### Wiring
- DHT11 -> pin data ke GPIO 4 ESP32
- Motor DC -> dikendalikan via TIP41, PWM dari GPIO 5 ESP32
- VCC dan GND sesuai kebutuhan

### Kode Program

```cpp
#include <DHT.h>

#define DHTPIN 4
#define DHTTYPE DHT11
#define FAN_PIN 5

DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(115200);
  dht.begin();
  pinMode(FAN_PIN, OUTPUT);
}

float fuzzyMembership(float x, float x0, float x1, float x2, float x3) {
  if (x <= x0 || x >= x3) return 0;
  else if (x >= x1 && x <= x2) return 1;
  else if (x > x0 && x < x1) return (x - x0) / (x1 - x0);
  else return (x3 - x) / (x3 - x2);
}

void loop() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();

  if (isnan(h) || isnan(t)) {
    Serial.println("Failed to read from DHT sensor!");
    return;
  }

  // Membership Suhu
  float suhuRendah = fuzzyMembership(t, 15, 20, 20, 25);
  float suhuSedang = fuzzyMembership(t, 20, 25, 25, 30);
  float suhuTinggi = fuzzyMembership(t, 25, 30, 35, 40);

  // Membership Kelembapan
  float humKering = fuzzyMembership(h, 30, 40, 40, 50);
  float humNormal = fuzzyMembership(h, 40, 50, 50, 60);
  float humLembap = fuzzyMembership(h, 50, 60, 70, 80);

  // Aturan (9 Rule)
  float outLambat = max(
    max(min(suhuRendah, humKering), min(suhuRendah, humNormal)),
    min(suhuSedang, humKering)
  );

  float outSedang = max(
    max(min(suhuRendah, humLembap), min(suhuTinggi, humKering)),
    min(suhuSedang, humNormal)
  );

  float outCepat = max(
    max(min(suhuSedang, humLembap), min(suhuTinggi, humNormal)),
    min(suhuTinggi, humLembap)
  );

  // Defuzzyfikasi (rata-rata berbobot sederhana)
  float pwm = (outLambat * 85 + outSedang * 170 + outCepat * 255) / 
              (outLambat + outSedang + outCepat + 0.0001);

  analogWrite(FAN_PIN, (int)pwm);

  Serial.print("Suhu: "); Serial.print(t);
  Serial.print(" | Kelembapan: "); Serial.print(h);
  Serial.print(" | PWM Fan: "); Serial.println(pwm);

  delay(2000);
}
```

---

## Tugas Praktikum
1. Jelaskan konsep fuzzy logic dalam mengontrol kecepatan kipas.  
2. Ubah fungsi keanggotaan (range suhu/kelembapan) dan amati perubahan sistem.  
3. Simulasikan beberapa nilai sensor dan lakukan perhitungan fuzzy manual untuk membandingkan hasil dengan program.
4. Buat laporan dan analisanya. 

---


## Lisensi
Proyek ini bersifat open-source dan bebas digunakan untuk pembelajaran maupun pengembangan lebih lanjut.
