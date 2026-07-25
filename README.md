<div align="center">

# 🏠 EchoCore

**ESP32 Smart Home Hub — Voice Control · Live Dashboard · WhatsApp Alerts · AI Assistant**

![ESP32](https://img.shields.io/badge/ESP32-IoT%20Hub-E7352C?style=for-the-badge&logo=espressif&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Backend-000000?style=for-the-badge&logo=flask&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-LLaMA%203-F55036?style=for-the-badge)
![WhatsApp](https://img.shields.io/badge/PyWhatKit-WhatsApp-25D366?style=for-the-badge&logo=whatsapp&logoColor=white)

*Sense everything. Miss nothing.*

</div>

---

## 📌 What is EchoCore?

EchoCore is a full-stack smart home automation system built on an **ESP32 microcontroller**. It reads live sensor data (temperature, humidity, motion, gas/smoke, sound), serves it to a web dashboard in real time via **Socket.IO**, and responds to natural-language voice commands powered by **Groq LLaMA 3**.

When motion or gas is detected, it automatically sends a **WhatsApp alert** to your phone. You can also control everything — fan, LED, buzzer — from the dashboard or by just talking to it.

---

## ✨ Features

| Feature | Details |
|---|---|
| 🌡️ Live Sensor Dashboard | Temperature, Humidity, PIR Motion, MQ-2 Gas (raw + threshold), Sound Level |
| 🎙️ AI Voice Assistant | Powered by Groq LLaMA 3 — understands natural language, not just exact phrases |
| 🗣️ Wake Word | Say **"Echo"** in the browser — no button press needed |
| 📱 WhatsApp Alerts | Auto-sends on motion and gas detection via PyWhatKit (cooldown: 5 min / 2 min) |
| 💡 Output Control | Fan (relay), Clap LED, Alert LED, Buzzer — via dashboard buttons or voice |
| 🌙 Routines | "Good night" / "Good morning" scenes that set multiple outputs at once |
| 🌤️ Weather + Activity Suggestions | Ask about weather in any city — Groq suggests activities |
| 📋 Daily Summary | Sent via WhatsApp at 9 PM every day (avg temp, motion count, fan runtime) |
| 🔕 Do Not Disturb | Suppress motion alerts for a set time ("don't disturb me for an hour") |
| 💬 Send WhatsApp to Contacts | "Tell Mani I'm on my way" — sends to saved contacts via voice |
| 🧪 Test Alert | One-click demo of full alert pipeline |
| 🔊 TTS Replies | Flask speaks Echo's replies aloud on the server PC via pyttsx3 |
| 🎤 Offline STT option | Vosk-based always-on background listener (voice_listener.py) |
| 🎤 Cloud STT option | Groq Whisper + WebRTC VAD for Hinglish/accented English (voice_groq.py) |

---

## 🛠️ Hardware

| Component | Pin | Notes |
|---|---|---|
| ESP32 Dev Module | — | Main MCU |
| DHT11 | GPIO 14 | Temperature & Humidity |
| PIR Sensor | GPIO 27 | Motion — INPUT_PULLDOWN |
| MQ-2 Gas (Analog) | GPIO 35 | Raw ADC reading → threshold 1500 |
| MQ-2 Gas (Digital) | GPIO 25 | Direct threshold output |
| Active Buzzer | GPIO 5 | Gas alarm only (not motion) |
| Red Alert LED | GPIO 4 | ON when motion OR gas OR manual |
| Clap/Light LED | GPIO 2 | Dashboard/voice controlled only |
| Relay Module | GPIO 32 | Fan — active LOW |
| SSD1306 OLED | SDA 21 / SCL 22 | Welcome, motion, gas, WiFi screens |

**Key thresholds:**
- Gas triggers at MQ-2 analog > **1500**
- Fan auto-turns on when temp > **35°C**
- Buzzer fires on **gas only**, not motion

---

## 🏗️ Architecture

```
┌────────────────────┐     HTTP POST /data      ┌─────────────────────┐
│   ESP32            │  ──── every 2 sec ──────▶ │   Flask Server      │
│                    │                           │   (localhost:5000)  │
│  DHT11, PIR, MQ-2  │ ◀── HTTP GET commands ─── │                     │
│  Buzzer, LEDs, Fan │   /fan/on, /led/off ...   │  Socket.IO live     │
│  OLED Display      │                           │  Groq LLaMA 3       │
└────────────────────┘                           │  pyttsx3 TTS        │
                                                 │  PyWhatKit alerts   │
                                                 │  OpenWeather API    │
                                                 └────────┬────────────┘
                                                          │ Socket.IO
                                                          ▼
                                                 ┌─────────────────────┐
                                                 │   Web Dashboard     │
                                                 │   (index.html)      │
                                                 │                     │
                                                 │  Animated orb UI    │
                                                 │  Sensor cards       │
                                                 │  Voice (browser STT)│
                                                 │  GSAP animations    │
                                                 └─────────────────────┘
```

**Data flow:** ESP32 POSTs sensor JSON to Flask every 2 seconds → Flask updates state, pushes to browser via Socket.IO, checks cooldowns, fires WhatsApp if needed → Browser updates all cards live. Control commands go Dashboard → Flask → ESP32 HTTP GET.

---

## 📁 Project Structure

```
EchoCore/
│
├── server/
│   ├── app.py               # Flask backend — all routes, Groq, WhatsApp, TTS, routines
│   ├── voice_groq.py        # Groq Whisper + WebRTC VAD — cloud STT for Hinglish
│   ├── voice_listener.py    # Vosk — fully offline background wake word listener
│   ├── gen_cert.py          # SSL cert generator (for HTTPS if needed)
│   └── PyWhatKit_DB.txt     # PyWhatKit internal log
│
├── website/
│   ├── index.html           # Full frontend — Hero, Assistant, Sensor Dashboard
│   ├── style.css            # Dark theme, orb animations, sensor cards
│   └── script.js            # Socket.IO live updates, browser STT, voice flow, GSAP
│
└── esp32/
    └── echocore_esp32.ino   # ESP32 firmware — WiFi, sensors, HTTP, OLED, WebServer
```

---

## 🚀 Setup

### 1. Flash the ESP32

Open `esp32/echocore_esp32.ino` in Arduino IDE.

**Required libraries** (Tools → Manage Libraries):
- `DHT sensor library` — Adafruit
- `Adafruit SSD1306`
- `Adafruit GFX Library`

**Edit these lines:**
```cpp
const char* ssid      = "YOUR_WIFI_NAME";
const char* password  = "YOUR_WIFI_PASSWORD";
const char* serverURL = "http://YOUR_PC_LOCAL_IP:5000/data";
```

Find your PC's local IP: `ipconfig` (Windows) or `ifconfig` (Linux/Mac) → look for `192.168.x.x`

Select **ESP32 Dev Module** → Upload.

---

### 2. Set Up the Flask Server

```bash
pip install flask flask-socketio pywhatkit pyttsx3 groq requests
```

Open `server/app.py` and fill in:

```python
ESP32_IP            = "http://YOUR_ESP32_IP"        # shown in Serial Monitor on boot
MY_NUMBER           = "+91XXXXXXXXXX"               # your WhatsApp number with country code
GROQ_API_KEY        = "your_groq_api_key"           # from console.groq.com (free)
OPENWEATHER_API_KEY = "your_openweather_key"        # from openweathermap.org (free)
WEATHER_CITY        = "Your City"                   # default city for weather queries
contacts            = {"Mani": "+91XXXXXXXXXX"}     # contacts for voice WhatsApp
```

Run the server:
```bash
python app.py
```

Dashboard opens at: **http://localhost:5000**

---

### 3. WhatsApp Setup (PyWhatKit)

PyWhatKit uses the **WhatsApp Web browser session** — no API or Twilio needed.

1. Open WhatsApp Web (`web.whatsapp.com`) in Chrome and keep it logged in
2. First time it runs, it will open a browser window — scan QR if needed
3. After that, alerts send automatically

> ⚠️ WhatsApp Web must be open on the same PC running Flask.

---

### 4. Groq API Key (Free)

1. Go to [console.groq.com](https://console.groq.com)
2. Create a free account → API Keys → Create Key
3. Paste it in `app.py` under `GROQ_API_KEY`

Groq's free tier is generous — LLaMA 3 calls for voice commands cost almost nothing.

---

### 5. Voice Options

**Option A — Browser STT (built-in, no setup)**
- Works in Chrome only
- Say "Echo" as wake word → browser mic activates → command goes to Groq LLaMA 3
- No extra software needed

**Option B — Offline STT via Vosk (voice_listener.py)**
```bash
pip install vosk sounddevice
# Download model from alphacephei.com/vosk/models → vosk-model-small-en-us
# Place folder as "model/" next to voice_listener.py
python voice_listener.py
```

**Option C — Groq Whisper + VAD (voice_groq.py) — best for Hinglish**
```bash
pip install sounddevice numpy webrtcvad groq
python voice_groq.py
```

---

## 🎙️ Voice Commands

EchoCore uses Groq LLaMA 3 to understand **intent**, not exact phrases:

| Say something like... | What happens |
|---|---|
| "it's dark here" / "lights on" | Turns on Clap LED |
| "too hot" / "start the fan" | Fan ON |
| "I'm going to sleep" / "good night" | Routine: lights off, buzzer off |
| "good morning" / "start the day" | Routine: lights on |
| "how's everything at home" | Full sensor status report |
| "tell Mani I'm on my way" | WhatsApp to saved contact |
| "don't disturb me for 30 minutes" | DND ON for 30 min |
| "I'm back" / "stop do not disturb" | DND OFF |
| "what should I do today" | Weather + activity suggestions |
| "weather in Mumbai" | Weather for Mumbai from OpenWeather |
| "is there gas?" / "temperature?" | Sensor readings spoken aloud |

---

## 🔌 API Reference

### ESP32 → Flask

| Method | Endpoint | Body | Description |
|---|---|---|---|
| `POST` | `/data` | `{temp, humidity, motion, gas, gas_val, fan, clap_led, alert_led}` | Sensor data from ESP32 |

### Dashboard / Voice → Flask

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/sensor` | Current sensor state JSON |
| `POST` | `/voice_command` | `{"command": "turn on fan"}` |
| `GET` | `/fan/on` `/fan/off` | Fan control |
| `GET` | `/led/on` `/led/off` | Clap LED control |
| `GET` | `/buzzer/on` `/buzzer/off` | Buzzer control |
| `GET` | `/alertled/on` `/alertled/off` | Alert LED control |
| `GET` | `/test_alert` | Simulate gas alert (5 sec demo) |
| `GET` | `/dnd_status` | Check if DND is active |

### Flask → ESP32

Flask calls ESP32's own web server directly:

| ESP32 Endpoint | Effect |
|---|---|
| `GET /fan/on` `/fan/off` | Toggle relay (active LOW) |
| `GET /led/on` `/led/off` | Toggle Clap LED |
| `GET /buzzer/on` `/buzzer/off` | Toggle buzzer |
| `GET /alertled/on` `/alertled/off` | Toggle Alert LED |
| `GET /status` | Returns "EchoCore OK" |

---

## 📊 Sensor Data Shape

```json
{
  "temp": 28.5,
  "humidity": 65.0,
  "motion": 1,
  "gas": 0,
  "gas_val": 980,
  "fan": 0,
  "clap_led": 0,
  "alert_led": 1,
  "sound_level": 0
}
```

---

## ⚠️ Alert Logic

| Event | Trigger | Cooldown | WhatsApp | Buzzer | Alert LED |
|---|---|---|---|---|---|
| Motion | PIR HIGH | 5 minutes | ✅ (if DND off) | ❌ | ✅ |
| Gas | MQ-2 ADC > 1500 | 2 minutes | ✅ always | ✅ | ✅ |
| Test Alert | `/test_alert` | — | ✅ (test message) | ✅ (5s) | ✅ (5s) |
| Daily Summary | 9 PM daily | — | ✅ | ❌ | ❌ |

---

## 🔮 Roadmap

- [ ] MQTT support for multi-device homes
- [ ] SQLite historical data + graphs
- [ ] Mobile-responsive dashboard
- [ ] PWA / mobile app
- [ ] Camera integration for visual alerts

---

## 👥 Built by:

Built as an **IDP (Interdisciplinary Project)** at Bapuji Institute of Engineering and Technology.

Manav- Hardware & Backend architecture — Flask, Groq AI pipeline, system design, ESP32 firmware, circuit design, sensor integration

<div align="center">
Made with ☕ and way too many Serial.println() calls.
</div>
