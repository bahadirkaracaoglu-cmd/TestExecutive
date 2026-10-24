# Test Executive

Üretim ve doğrulama istasyonları için geliştirilmiş, Python ve PySide6 tabanlı modüler **Test Executive** yazılımı. Test edilen birimlerle (DUT) seri port, TCP veya UDP üzerinden çerçeveli/metin tabanlı haberleşir; aynı zamanda SCPI/VISA destekli test cihazlarını (Keysight, Rohde & Schwarz, TDK-Lambda vb.) kontrol ederek test sekanslarını otomatik koşturur, verileri analiz eder, SQLite/PostgreSQL veritabanına kaydeder ve PDF/HTML/Excel raporları üretir.

---

## ✨ Temel Özellikler

- **Çoklu Haberleşme Kanalları (`testexec/transports`):**
  - `TCP`, `UDP`, `Serial (pyserial)`, `VISA (PyVISA / pyvisa-py)` ve donanımsız geliştirme için `MockTransport`.
  - Gönderilen ve alınan tüm paketlerin zaman damgalı ham iletişim (traffic) kaydı.
- **SCPI Cihaz Soyutlama Katmanı (`testexec/instruments`):**
  - Genel `PowerSupply`, `Dmm`, `ElectronicLoad` sınıfları ve üreticiye özel alt sınıflar (örn. `TdkLambdaPsu`).
  - `*IDN?` yanıtına göre otomatik sürücü eşleştirme (`refine_by_idn`).
- **DUT Çerçeve Protokolü ve Mesaj Kataloğu (`testexec/codec.py`, `testexec/dut`):**
  - `messageID (4B, little-endian) | messageLen (4B, payload uzunluğu) | payload (N byte) | checksum (1B, XOR)` çerçeve yapısı ve akış senkronizasyonlu `StreamDecoder`.
  - Yüzlerce mesajı kod yazmadan yönetmek için YAML tabanlı **DUT Profili** (`uint/int 8..64`, `float32/64`, `bytes`, `ascii`, `bits`, `enum`, `scale`, `unit`).
  - **Excel / CSV İçe-Dışa Aktarma:** Mesaj dokümanlarını Excel tablosundan tek tıkla içe aktarma, örnek Excel şablonu oluşturma ve katalogdan otomatik test sekansı üretme.
- **Deklaratif Test Sekanslayıcı (`testexec/core`):**
  - YAML ile tanımlanan test adımları: `dut_message`, `frame`, `send_receive`, `measure`, `scpi_write`, `operator_input`, `delay`.
  - Limit kontrolü (`min`/`max`), tekrar deneme (`retries`), hata politikası (`on_fail: stop | continue`) ve anlık iptal desteği.
- **Veritabanı, Analiz ve Raporlama (`testexec/db`, `testexec/analysis`, `testexec/reports`):**
  - SQLAlchemy tabanlı kayıt: koşu özeti, adım sonuçları, çözülmüş DUT mesaj alanları (`fields_json`), ölçüm serileri ve ham iletişim.
  - İstatistiksel süreç kontrolü: Ortalama, standart sapma, min/max, **Cp / Cpk** ve başarı oranı (yield).
  - Grafik gömülü **PDF**, **HTML** ve çok sayfalı **Excel (`.xlsx`)** rapor çıktısı.
- **Modern Koyu Temalı Masaüstü Arayüzü (`testexec/ui`):**
  - **▶ Koşu:** Barkod/seri no girişi, KPI kartları, renkli adım tablosu, büyük GEÇTİ/KALDI göstergesi, limit çizgili canlı `pyqtgraph` grafiği, olay günlüğü ve ham iletişim sekmesi.
  - **☰ Geçmiş:** Seri numarasına göre filtreleme, adım ve grafik inceleme, tek tıkla PDF/HTML/Excel rapor üretimi.
  - **◔ İstatistik:** Ölçüm bazlı trend grafiği, dağılım histogramı ve Cp/Cpk hesapları.
  - **⇄ Mesajlar:** DUT mesaj kataloğu arama/filtreleme, byte aralığı bazlı canlı payload parametre düzenleyici, preset kaydetme, canlı çerçeve önizleme ve tekil mesaj gönderip çözülmüş yanıtı inceleme.
  - **⌨ Konsol:** Kanallara doğrudan SCPI, metin, HEX veya DUT çerçevesi gönderme.

---

## 📁 Proje Yapısı

```text
TestExecutive/
├─ testexec/
│  ├─ codec.py              # DUT çerçeve kodlayıcı/çözücü (ID | Len | Payload | XOR)
│  ├─ simulators.py         # Donanımsız test için sahte SCPI ve DUT yanıtlayıcıları
│  ├─ core/                 # Sequencer, Station, StepResult/RunResult ve adım tipleri
│  ├─ transports/           # TCP, UDP, Serial, VISA ve Mock haberleşme sınıfları
│  ├─ instruments/          # SCPI cihaz sürücüleri (PSU, DMM, Load, TDK-Lambda)
│  ├─ dut/                  # Mesaj kataloğu, Excel/CSV içe aktarıcı, otomatik sekans üretici
│  ├─ analysis/             # Ortalama, std, Cp, Cpk ve yield hesaplamaları
│  ├─ db/                   # SQLAlchemy veritabanı modelleri ve Repository
│  ├─ reports/              # Jinja2 HTML şablonu, PDF ve Excel rapor üreticileri
│  └─ ui/                   # PySide6 masaüstü arayüzü sayfaları ve koyu tema
├─ stations/                # İstasyon donanım/kanal tanımları (YAML)
├─ sequences/               # Test sekans tanımları (YAML)
├─ dut_profiles/            # DUT mesaj ve parametre katalogları (YAML)
├─ tests/                   # Pytest birim ve entegrasyon testleri
├─ main.py                  # Masaüstü arayüzü giriş noktası
└─ main_cli.py              # Komut satırı (CLI) koşturucu
```

---

## 🚀 Kurulum ve Çalıştırma

### 1. Ortamı Hazırlama

Python 3.11+ önerilir:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Masaüstü Arayüzünü Başlatma

```powershell
.venv\Scripts\python.exe main.py
```

### 3. Komut Satırından (CLI) Koşturma

```powershell
.venv\Scripts\python.exe main_cli.py --station stations/demo_station.yaml --sequence sequences/demo_sequence.yaml --serial SN0001 --operator op1
```

### 4. Testleri Çalıştırma

```powershell
.venv\Scripts\python.exe -m pytest -q
```

---

## 🛠️ Yapılandırma Örnekleri

### İstasyon Tanımı (`stations/demo_station.yaml`)

Gerçek donanıma geçerken `mock` kanalları `serial`, `tcp`, `udp` veya `visa` ile değiştirmeniz yeterlidir:

```yaml
station: ISTASYON-1
dut_profile: dut_profiles/example_dut.yaml
transports:
  dut:      {type: serial, port: COM3, baudrate: 115200}
  psu_link: {type: visa, resource: "TCPIP0::192.168.1.20::INSTR"}
instruments:
  psu1:     {type: psu, transport: psu_link}
```

### DUT Mesaj Profili (`dut_profiles/example_dut.yaml`)

```yaml
dut: ModelX-Rev2
byte_order: little
messages:
  INIT_REQ:
    id: 0x10
    direction: tx
    response: INIT_RSP
    group: init
    fields:
      - {name: mode,        offset: 0, type: uint8, enum: {NORMAL: 0, TEST: 1}}
      - {name: init_params, offset: 1, size: 3, type: bytes, default: "00 00 00"}
      - {name: timeout_ms,  offset: 4, type: uint16, default: 500, unit: ms}
  INIT_RSP:
    id: 0x90
    direction: rx
    group: init
    fields:
      - {name: status, offset: 0, type: uint8, enum: {OK: 0, ERR: 1}}
      - {name: temp,   offset: 3, type: int16, scale: 0.1, unit: "°C"}
```