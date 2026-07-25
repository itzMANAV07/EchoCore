# ============================================================
#  EchoCore - Flask Backend Server (Full Feature Build)
#  - Groq Llama 3 understands natural language + conversational memory
#  - Routine/scene mode (good night / good morning)
#  - Daily summary report (scheduled)
#  - Do Not Disturb mode
#  - Weather-based activity suggestions (OpenWeather + Groq)
#  - Wake word via browser background listening
#  - Test Alert button for demo purposes
#  - Weather query for any city by voice
#  - FIX: Mic aborted error resolved
# ============================================================

from flask import Flask, request, jsonify, render_template_string
from flask_socketio import SocketIO, emit
import pywhatkit
import pyttsx3
import threading
import time
import json
import requests
from datetime import datetime
from groq import Groq
import webbrowser

webbrowser.register('chrome', None,
    webbrowser.BackgroundBrowser("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'echocore2024'
socketio = SocketIO(app, cors_allowed_origins="*")

# ── Config ────────────────────────────────────────────────────
ESP32_IP = "http://10.198.46.180"
MY_NUMBER  = #your moblie number

GROQ_API_KEY = "#grok_api_key"
groq_client         = Groq(api_key=GROQ_API_KEY)

OPENWEATHER_API_KEY = "#openweather_api_key"
WEATHER_CITY        = "#your location"

MOTION_COOLDOWN   = 300
GAS_COOLDOWN      = 120
last_motion_alert = 0
last_gas_alert    = 0

dnd_active = False
dnd_until  = None

conversation_history = []
MAX_HISTORY = 6

daily_log = {
    "temp_readings":   [],
    "motion_count":    0,
    "gas_alerts":      0,
    "fan_on_seconds":  0,
    "last_fan_change": time.time(),
    "fan_was_on":      False
}

sensor_data = {
    "temp": 0, "humidity": 0, "motion": 0, "gas": 0,
    "gas_val": 0, "fan": 0, "clap_led": 0,
    "alert_led": 0, "sound_level": 0
}

contacts = {
    #Add contact of peoples using name and there number
}

# =============================================================
#  VOICE REPLY
# =============================================================
def speak(text):
    def _speak():
        try:
            print(f"EchoCore says: {text}")
            tts = pyttsx3.init()
            tts.setProperty('rate', 160)
            tts.setProperty('volume', 1.0)
            tts.say(text)
            tts.runAndWait()
            tts.stop()
        except Exception as e:
            print(f"Speak error: {e}")
    threading.Thread(target=_speak, daemon=True).start()

# =============================================================
#  WHATSAPP ALERT
# =============================================================
def send_whatsapp_alert(number, message):
    def _send():
        try:
            pywhatkit.sendwhatmsg_instantly(
                number, message, wait_time=15, tab_close=True, close_time=5
            )
            print(f"WhatsApp sent to {number}")
        except Exception as e:
            print(f"WhatsApp failed: {e}")
    threading.Thread(target=_send).start()

# =============================================================
#  ESP32 COMMAND
# =============================================================
def esp32_command(endpoint):
    try:
        r = requests.get(f"{ESP32_IP}/{endpoint}", timeout=3)
        print(f"ESP32 /{endpoint}: {r.status_code}")
        return True
    except Exception as e:
        print(f"ESP32 command failed: {e}")
        return False

# =============================================================
#  WEATHER + ACTIVITY SUGGESTIONS
# =============================================================
def get_weather(city=None):
    target_city = city if city else WEATHER_CITY
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={target_city}&appid={OPENWEATHER_API_KEY}&units=metric"
        r = requests.get(url, timeout=5)
        data = r.json()
        if data.get('cod') != 200:
            return None
        return {
            "city":        target_city,
            "temp":        data['main']['temp'],
            "feels_like":  data['main']['feels_like'],
            "condition":   data['weather'][0]['main'],
            "description": data['weather'][0]['description'],
            "humidity":    data['main']['humidity'],
            "wind_speed":  data['wind']['speed']
        }
    except Exception as e:
        print(f"Weather fetch error: {e}")
        return None

def suggest_activities(weather):
    if not weather:
        return "I couldn't fetch the weather for that location."
    prompt = f"""Current weather in {weather['city']}: {weather['temp']}°C, feels like {weather['feels_like']}°C,
{weather['description']}, humidity {weather['humidity']}%, wind {weather['wind_speed']} m/s.
Reply naturally mentioning the city name and weather, then suggest 2-3 brief suitable activities. Max 45 words total, conversational tone, no bullet points."""
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Activity suggestion error: {e}")
        return "I couldn't generate suggestions right now."

# =============================================================
#  GROQ — UNDERSTAND COMMAND
# =============================================================
def understand_command(user_text, sensor_context):
    global conversation_history

    system_prompt = f"""You are EchoCore, a smart home assistant.
Current sensor readings: {sensor_context}
Do Not Disturb mode is currently: {"ON" if dnd_active else "OFF"}

Respond ONLY with valid JSON, no markdown, no explanation. Format:
{{
  "action": "fan_on" | "fan_off" | "light_on" | "light_off" | "buzzer_on" | "buzzer_off" | "status_report" | "send_message" | "routine_goodnight" | "routine_goodmorning" | "dnd_on" | "dnd_off" | "weather_activities" | "none",
  "contact": "name if sending a message, else null",
  "message": "message content if sending a message, else null",
  "dnd_minutes": "number of minutes for DND if mentioned, else null",
  "city": "city name if user asks about weather/activities in a specific place, else null",
  "reply": "a short natural spoken reply, max 15 words"
}}

Understand intent and meaning, not exact phrases:
"it's dark here" -> light_on
"it's too hot" -> fan_on
"I'm going to sleep" / "good night" -> routine_goodnight
"good morning" / "start the day" -> routine_goodmorning
"tell mani I'm on my way" -> send_message
"how's everything at home" -> status_report
"don't disturb me for an hour" -> dnd_on, dnd_minutes: 60
"stop do not disturb" / "I'm back" -> dnd_off
"what should I do today" -> weather_activities, city: null
"what's the weather in Mumbai" -> weather_activities, city: Mumbai
"suggest activities for Goa" -> weather_activities, city: Goa
"how's the weather in Bangalore" -> weather_activities, city: Bangalore
Use conversation history to understand follow-up references.

Only output the JSON object."""

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_text})

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.3
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)

        conversation_history.append({"role": "user", "content": user_text})
        conversation_history.append({"role": "assistant", "content": result.get("reply", "")})
        conversation_history = conversation_history[-MAX_HISTORY:]

        return result
    except Exception as e:
        print(f"Groq understanding error: {e}")
        return {"action": "none", "reply": "Sorry, I didn't quite catch that."}

# =============================================================
#  ROUTINES
# =============================================================
def run_routine_goodnight():
    esp32_command('led/off')
    esp32_command('buzzer/off')
    sensor_data['clap_led'] = 0
    socketio.emit('sensor_update', sensor_data)

def run_routine_goodmorning():
    esp32_command('led/on')
    sensor_data['clap_led'] = 1
    socketio.emit('sensor_update', sensor_data)

# =============================================================
#  DAILY SUMMARY
# =============================================================
def generate_daily_summary():
    temps = daily_log["temp_readings"]
    avg_temp = sum(temps) / len(temps) if temps else 0
    max_temp = max(temps) if temps else 0
    fan_minutes = round(daily_log["fan_on_seconds"] / 60, 1)

    summary = (
        f"📋 EchoCore Daily Summary\n"
        f"Average temperature: {avg_temp:.1f}°C\n"
        f"Peak temperature: {max_temp:.1f}°C\n"
        f"Motion detected: {daily_log['motion_count']} times\n"
        f"Gas alerts: {daily_log['gas_alerts']}\n"
        f"Fan ran for: {fan_minutes} minutes"
    )
    print(summary)
    send_whatsapp_alert(MY_NUMBER, summary)
    speak(f"Here is today's summary. Average temperature {avg_temp:.0f} degrees. "
          f"Motion detected {daily_log['motion_count']} times. "
          f"Fan ran for {fan_minutes} minutes.")

    daily_log["temp_readings"]  = []
    daily_log["motion_count"]   = 0
    daily_log["gas_alerts"]     = 0
    daily_log["fan_on_seconds"] = 0

def daily_summary_scheduler():
    SUMMARY_HOUR = 21
    while True:
        now = datetime.now()
        if now.hour == SUMMARY_HOUR and now.minute == 0:
            generate_daily_summary()
            time.sleep(61)
        time.sleep(20)

threading.Thread(target=daily_summary_scheduler, daemon=True).start()

# =============================================================
#  RECEIVE SENSOR DATA FROM ESP32
# =============================================================
@app.route('/data', methods=['POST'])
def receive_data():
    global last_motion_alert, last_gas_alert, dnd_active, dnd_until

    data = request.get_json()
    if not data:
        return jsonify({"error": "no data"}), 400

    sensor_data.update(data)
    print(f"[DATA] Temp={data.get('temp')}C  Motion={data.get('motion')}  "
          f"Gas={data.get('gas')}  GasVal={data.get('gas_val')}")

    socketio.emit('sensor_update', sensor_data)

    if data.get('temp'):
        daily_log["temp_readings"].append(data.get('temp'))
    if data.get('motion') == 1:
        daily_log["motion_count"] += 1
    if data.get('gas') == 1:
        daily_log["gas_alerts"] += 1

    fan_now = bool(data.get('fan'))
    if daily_log["fan_was_on"] and not fan_now:
        daily_log["fan_on_seconds"] += time.time() - daily_log["last_fan_change"]
    if fan_now != daily_log["fan_was_on"]:
        daily_log["last_fan_change"] = time.time()
        daily_log["fan_was_on"] = fan_now

    if dnd_active and dnd_until and time.time() > dnd_until:
        dnd_active = False
        dnd_until  = None

    now = time.time()

    if data.get('motion') == 1 and not dnd_active:
        if now - last_motion_alert > MOTION_COOLDOWN:
            last_motion_alert = now
            send_whatsapp_alert(MY_NUMBER, "🚨 EchoCore Alert: Motion detected at home!")

    if data.get('gas') == 1:
        if now - last_gas_alert > GAS_COOLDOWN:
            last_gas_alert = now
            send_whatsapp_alert(MY_NUMBER, "🔥 EchoCore Alert: Gas detected at home!")
            speak("Warning! Gas detected at home.")

    return jsonify({"status": "ok"})

# =============================================================
#  CLAP TRIGGER
# =============================================================
@app.route('/clap', methods=['GET'])
def clap_trigger():
    socketio.emit('clap_detected', {})
    speak("Yes, I am listening.")
    return jsonify({"status": "ok"})

# =============================================================
#  TEST ALERT
# =============================================================
@app.route('/test_alert', methods=['GET'])
def test_alert():
    print("🧪 TEST ALERT triggered")
    esp32_command('buzzer/on')
    esp32_command('alertled/on')

    sensor_data['gas']     = 1
    sensor_data['gas_val'] = 2200
    socketio.emit('sensor_update', sensor_data)

    send_whatsapp_alert(MY_NUMBER, "🧪 EchoCore TEST Alert: This is a simulated gas/fire alert.")
    speak("Test alert triggered. This is a simulated gas detection.")

    def clear_test_alert():
        time.sleep(5)
        esp32_command('buzzer/off')
        esp32_command('alertled/off')
        sensor_data['gas']     = 0
        sensor_data['gas_val'] = 0
        socketio.emit('sensor_update', sensor_data)
        print("Test alert cleared")

    threading.Thread(target=clear_test_alert, daemon=True).start()
    return jsonify({"status": "test alert triggered"})

# =============================================================
#  VOICE COMMAND
# =============================================================
@app.route('/voice_command', methods=['POST'])
def voice_command():
    global dnd_active, dnd_until

    data    = request.get_json()
    command = data.get('command', '')
    print(f"Voice command: {command}")

    sensor_context = (
        f"Temperature: {sensor_data['temp']}C, Humidity: {sensor_data['humidity']}%, "
        f"Motion: {'detected' if sensor_data['motion'] else 'clear'}, "
        f"Gas: {'detected' if sensor_data['gas'] else 'clear'}, "
        f"Fan: {'on' if sensor_data['fan'] else 'off'}, "
        f"Light: {'on' if sensor_data['clap_led'] else 'off'}"
    )

    result = understand_command(command, sensor_context)
    action = result.get('action', 'none')
    reply  = result.get('reply', 'OK')

    if action == 'fan_on':
        esp32_command('fan/on'); sensor_data['fan'] = 1
        socketio.emit('sensor_update', sensor_data)

    elif action == 'fan_off':
        esp32_command('fan/off'); sensor_data['fan'] = 0
        socketio.emit('sensor_update', sensor_data)

    elif action == 'light_on':
        esp32_command('led/on'); sensor_data['clap_led'] = 1
        socketio.emit('sensor_update', sensor_data)

    elif action == 'light_off':
        esp32_command('led/off'); sensor_data['clap_led'] = 0
        socketio.emit('sensor_update', sensor_data)

    elif action == 'buzzer_on':
        esp32_command('buzzer/on')

    elif action == 'buzzer_off':
        esp32_command('buzzer/off')

    elif action == 'send_message':
        contact = (result.get('contact') or '').capitalize()
        message = result.get('message') or ''
        if contact in contacts:
            send_whatsapp_alert(contacts[contact], message)
        else:
            reply = f"I couldn't find {contact} in your contacts."

    elif action == 'status_report':
        reply = (
            f"Temperature is {sensor_data['temp']} degrees, "
            f"humidity {sensor_data['humidity']} percent. "
            f"{'Motion detected.' if sensor_data['motion'] else 'No motion.'} "
            f"{'Gas detected!' if sensor_data['gas'] else 'No gas detected.'} "
            f"Fan is {'on' if sensor_data['fan'] else 'off'}."
        )

    elif action == 'routine_goodnight':
        run_routine_goodnight()

    elif action == 'routine_goodmorning':
        run_routine_goodmorning()

    elif action == 'dnd_on':
        minutes = result.get('dnd_minutes') or 60
        dnd_active = True
        dnd_until  = time.time() + (int(minutes) * 60)
        reply = f"Do not disturb enabled for {minutes} minutes."

    elif action == 'dnd_off':
        dnd_active = False
        dnd_until  = None
        reply = "Do not disturb turned off."

    elif action == 'weather_activities':
        city_requested = result.get('city')
        weather = get_weather(city_requested)
        reply = suggest_activities(weather)

    speak(reply)
    return jsonify({"reply": f"🤖 {reply}"})

# =============================================================
#  CONTROL ENDPOINTS
# =============================================================
@app.route('/fan/on')
def fan_on():
    esp32_command('fan/on'); sensor_data['fan'] = 1
    socketio.emit('sensor_update', sensor_data)
    return jsonify({"status": "fan on"})

@app.route('/fan/off')
def fan_off():
    esp32_command('fan/off'); sensor_data['fan'] = 0
    socketio.emit('sensor_update', sensor_data)
    return jsonify({"status": "fan off"})

@app.route('/buzzer/on')
def buzzer_on():
    esp32_command('buzzer/on')
    return jsonify({"status": "buzzer on"})

@app.route('/buzzer/off')
def buzzer_off():
    esp32_command('buzzer/off')
    return jsonify({"status": "buzzer off"})

@app.route('/led/on')
def led_on():
    esp32_command('led/on'); sensor_data['clap_led'] = 1
    socketio.emit('sensor_update', sensor_data)
    return jsonify({"status": "led on"})

@app.route('/led/off')
def led_off():
    esp32_command('led/off'); sensor_data['clap_led'] = 0
    socketio.emit('sensor_update', sensor_data)
    return jsonify({"status": "led off"})

@app.route('/alertled/on')
def alertled_on():
    esp32_command('alertled/on'); sensor_data['alert_led'] = 1
    socketio.emit('sensor_update', sensor_data)
    return jsonify({"status": "alert led on"})

@app.route('/alertled/off')
def alertled_off():
    esp32_command('alertled/off'); sensor_data['alert_led'] = 0
    socketio.emit('sensor_update', sensor_data)
    return jsonify({"status": "alert led off"})

@app.route('/sensor')
def get_sensor():
    return jsonify(sensor_data)

@app.route('/dnd_status')
def dnd_status():
    return jsonify({"dnd_active": dnd_active, "dnd_until": dnd_until})

# =============================================================
#  DASHBOARD
# =============================================================
@app.route('/')
def dashboard():
    return render_template_string(HTML_DASHBOARD)

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EchoCore</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.6.1/socket.io.min.js"></script>
<style>
  :root{
    --bg:#0a0e1a; --bg-soft:#0e1424; --panel:#131a2e; --panel-border:#222c47;
    --text:#e7ecf7; --text-dim:#7c87a8;
    --cyan:#00d9ff; --violet:#a78bfa; --amber:#ffb84d; --green:#34d399; --red:#f87171;
    --mono:'JetBrains Mono',monospace; --sans:'Space Grotesk',sans-serif;
  }
  *{margin:0;padding:0;box-sizing:border-box;}
  body{font-family:var(--sans); background:radial-gradient(circle at 20% 0%, rgba(167,139,250,0.10), transparent 45%), radial-gradient(circle at 85% 15%, rgba(0,217,255,0.08), transparent 40%), var(--bg); color:var(--text); min-height:100vh; padding:28px 16px 60px; overflow-x:hidden;}
  body::before{content:''; position:fixed; inset:0; background-image:linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px); background-size:48px 48px; mask-image:radial-gradient(ellipse at 50% 0%, black 0%, transparent 70%); pointer-events:none; z-index:0;}
  .wrap{position:relative; z-index:1; max-width:680px; margin:0 auto;}
  header{text-align:center; margin-bottom:8px;}
  .brand{display:inline-flex; align-items:center; gap:10px; font-size:1.9rem; font-weight:700; letter-spacing:0.02em;}
  .brand .bolt{width:30px; height:30px; filter:drop-shadow(0 0 10px rgba(0,217,255,0.6));}
  .brand-gradient{background:linear-gradient(120deg, var(--cyan), var(--violet)); -webkit-background-clip:text; background-clip:text; color:transparent;}
  .tagline{font-family:var(--mono); font-size:0.72rem; letter-spacing:0.12em; text-transform:uppercase; color:var(--text-dim); margin-top:6px; display:flex; align-items:center; justify-content:center; gap:8px;}
  .live-dot{width:7px; height:7px; border-radius:50%; background:var(--green); box-shadow:0 0 8px var(--green); animation:livepulse 2s ease-in-out infinite;}
  @keyframes livepulse{0%,100%{opacity:1;transform:scale(1);}50%{opacity:0.4;transform:scale(0.8);}}
  .dnd-banner{display:none; margin:18px auto 0; background:linear-gradient(90deg, rgba(255,184,77,0.16), rgba(255,184,77,0.06)); border:1px solid rgba(255,184,77,0.4); color:var(--amber); padding:10px 16px; border-radius:12px; font-family:var(--mono); font-size:0.8rem; text-align:center; align-items:center; justify-content:center; gap:8px;}
  .dnd-banner.show{display:flex; animation:slideIn 0.4s ease;}
  @keyframes slideIn{from{opacity:0; transform:translateY(-8px);} to{opacity:1; transform:translateY(0);}}
  .grid{display:grid; grid-template-columns:repeat(auto-fit, minmax(145px, 1fr)); gap:12px; margin:28px 0 24px;}
  .card{position:relative; background:linear-gradient(160deg, var(--panel), var(--bg-soft)); border:1px solid var(--panel-border); border-radius:16px; padding:18px 16px; overflow:hidden; transition:border-color 0.4s ease, transform 0.25s ease, box-shadow 0.4s ease;}
  .card::before{content:''; position:absolute; inset:0; background:radial-gradient(circle at 30% 0%, rgba(255,255,255,0.05), transparent 60%); pointer-events:none;}
  .card:hover{transform:translateY(-2px);}
  .card .icon-wrap{width:34px; height:34px; border-radius:10px; display:flex; align-items:center; justify-content:center; background:rgba(255,255,255,0.04); margin-bottom:10px; font-size:1.1rem;}
  .card .label{font-family:var(--mono); font-size:0.66rem; letter-spacing:0.08em; text-transform:uppercase; color:var(--text-dim); margin-bottom:6px;}
  .card .value{font-family:var(--mono); font-size:1.5rem; font-weight:600; color:var(--text); transition:color 0.3s ease;}
  .card .unit{font-size:0.85rem; color:var(--text-dim); font-weight:400;}
  .card.state-alert{border-color:rgba(248,113,113,0.55); box-shadow:0 0 0 1px rgba(248,113,113,0.15), 0 0 24px rgba(248,113,113,0.12); animation:alertGlow 1.6s ease-in-out infinite;}
  .card.state-alert .value{color:var(--red);}
  @keyframes alertGlow{0%,100%{box-shadow:0 0 0 1px rgba(248,113,113,0.15), 0 0 24px rgba(248,113,113,0.12);}50%{box-shadow:0 0 0 1px rgba(248,113,113,0.35), 0 0 36px rgba(248,113,113,0.25);}}
  .card.state-on{border-color:rgba(52,211,153,0.5); box-shadow:0 0 18px rgba(52,211,153,0.10);}
  .card.state-on .value{color:var(--green);}
  .section-title{font-family:var(--mono); font-size:0.72rem; letter-spacing:0.14em; text-transform:uppercase; color:var(--text-dim); margin:26px 2px 10px; display:flex; align-items:center; gap:8px;}
  .section-title::after{content:''; flex:1; height:1px; background:linear-gradient(90deg, var(--panel-border), transparent);}
  .controls{display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:6px;}
  .btn{position:relative; padding:15px; border:1px solid var(--panel-border); border-radius:13px; font-family:var(--sans); font-size:0.92rem; font-weight:600; cursor:pointer; color:var(--text); background:var(--panel); transition:transform 0.15s ease, border-color 0.3s ease; display:flex; align-items:center; justify-content:center; gap:8px;}
  .btn:active{transform:scale(0.96);}
  .btn-on:hover{border-color:var(--green); color:var(--green);}
  .btn-off:hover{border-color:var(--red); color:var(--red);}
  .btn-dnd:hover{border-color:var(--amber); color:var(--amber);}
  .btn-test{grid-column:1 / -1; border-color:rgba(248,113,113,0.4); background:linear-gradient(90deg, rgba(248,113,113,0.08), rgba(248,113,113,0.02));}
  .btn-test:hover{border-color:var(--red); color:var(--red);}
  .btn .ripple{position:absolute; border-radius:50%; background:rgba(255,255,255,0.4); transform:scale(0); animation:rippleAnim 0.6s ease-out; pointer-events:none;}
  @keyframes rippleAnim{to{transform:scale(3); opacity:0;}}
  .voice-section{margin-top:34px; background:linear-gradient(170deg, var(--panel), var(--bg-soft)); border:1px solid var(--panel-border); border-radius:22px; padding:34px 24px 28px; text-align:center; position:relative; overflow:hidden;}
  .voice-section::before{content:''; position:absolute; top:-50%; left:50%; transform:translateX(-50%); width:300px; height:300px; border-radius:50%; background:radial-gradient(circle, rgba(167,139,250,0.12), transparent 70%); pointer-events:none;}
  .voice-hint{font-size:0.84rem; color:var(--text-dim); margin-bottom:4px; position:relative;}
  .voice-examples{font-family:var(--mono); font-size:0.68rem; color:#56618a; margin-bottom:26px; line-height:1.6; position:relative;}

  /* Mic permission banner */
  .mic-permission-banner{display:none; margin-bottom:18px; background:linear-gradient(90deg,rgba(248,113,113,0.14),rgba(248,113,113,0.04)); border:1px solid rgba(248,113,113,0.4); border-radius:14px; padding:14px 16px; font-size:0.82rem; color:var(--red); line-height:1.6; position:relative;}
  .mic-permission-banner.show{display:block;}
  .mic-permission-banner strong{display:block; margin-bottom:4px; font-size:0.88rem;}
  .mic-permission-banner ol{padding-left:18px; color:#e7a0a0; margin-top:4px;}
  .mic-permission-banner ol li{margin-bottom:2px;}

  .orb-zone{position:relative; width:140px; height:140px; margin:0 auto 22px; display:flex; align-items:center; justify-content:center; cursor:pointer;}
  .orb-ring{position:absolute; border-radius:50%; border:1.5px solid rgba(167,139,250,0.35); inset:0; animation:ringDrift 4s ease-in-out infinite;}
  .orb-ring.r2{inset:-14px; border-color:rgba(0,217,255,0.18); animation-delay:0.3s;}
  .orb-ring.r3{inset:-28px; border-color:rgba(167,139,250,0.10); animation-delay:0.6s;}
  @keyframes ringDrift{0%,100%{opacity:0.5; transform:scale(1);}50%{opacity:0.9; transform:scale(1.06);}}
  .orb-core{width:88px; height:88px; border-radius:50%; background:radial-gradient(circle at 35% 30%, #c4b5fd, #7c3aed 60%, #4c1d95); box-shadow:0 0 30px rgba(167,139,250,0.55), inset 0 0 20px rgba(255,255,255,0.15); display:flex; align-items:center; justify-content:center; position:relative; z-index:2; animation:idleBreathe 3.2s ease-in-out infinite;}
  @keyframes idleBreathe{0%,100%{transform:scale(1);}50%{transform:scale(1.045);}}
  .orb-core svg{width:34px; height:34px; stroke:#fff; fill:none; stroke-width:2; opacity:0.95;}
  .orb-zone.listening .orb-core{animation:listenPulse 1.1s ease-in-out infinite; box-shadow:0 0 50px rgba(0,217,255,0.75), inset 0 0 20px rgba(255,255,255,0.2); background:radial-gradient(circle at 35% 30%, #67e8f9, #06b6d4 60%, #0e7490);}
  @keyframes listenPulse{0%,100%{transform:scale(1);}50%{transform:scale(1.12);}}
  .orb-zone.listening .orb-ring{border-color:rgba(0,217,255,0.5); animation:expandRing 1.4s ease-out infinite;}
  .orb-zone.listening .orb-ring.r2{animation-delay:0.25s;}
  .orb-zone.listening .orb-ring.r3{animation-delay:0.5s;}
  @keyframes expandRing{0%{transform:scale(0.85); opacity:0.9;}100%{transform:scale(1.5); opacity:0;}}
  .orb-zone.thinking .orb-core{background:radial-gradient(circle at 35% 30%, #fde68a, #f59e0b 60%, #b45309); box-shadow:0 0 40px rgba(245,158,11,0.6), inset 0 0 20px rgba(255,255,255,0.2); animation:thinkSpin 1.6s linear infinite;}
  @keyframes thinkSpin{0%{transform:rotate(0deg) scale(1);}50%{transform:rotate(180deg) scale(1.04);}100%{transform:rotate(360deg) scale(1);}}
  .orb-zone.speaking .orb-core{background:radial-gradient(circle at 35% 30%, #6ee7b7, #10b981 60%, #047857); box-shadow:0 0 40px rgba(16,185,129,0.6), inset 0 0 20px rgba(255,255,255,0.2); animation:idleBreathe 1s ease-in-out infinite;}
  .wave-bars{display:none; gap:4px; align-items:center; z-index:2; position:absolute;}
  .orb-zone.speaking .wave-bars{display:flex;}
  .orb-zone.speaking .orb-core svg{display:none;}
  .wave-bars span{width:4px; height:14px; border-radius:3px; background:#fff; animation:waveBounce 0.8s ease-in-out infinite;}
  .wave-bars span:nth-child(1){animation-delay:0s;} .wave-bars span:nth-child(2){animation-delay:0.15s;} .wave-bars span:nth-child(3){animation-delay:0.3s;} .wave-bars span:nth-child(4){animation-delay:0.45s;} .wave-bars span:nth-child(5){animation-delay:0.6s;}
  @keyframes waveBounce{0%,100%{height:10px;} 50%{height:28px;}}
  .orb-status{font-family:var(--mono); font-size:0.8rem; color:var(--text-dim); min-height:20px; margin-bottom:4px; transition:color 0.3s ease;}
  .orb-status.is-listening{color:var(--cyan);} .orb-status.is-thinking{color:var(--amber);} .orb-status.is-speaking{color:var(--green);} .orb-status.is-error{color:var(--red);}
  .reply-box{margin-top:16px; padding:14px 16px; background:rgba(255,255,255,0.03); border:1px solid var(--panel-border); border-radius:14px; font-size:0.92rem; color:var(--text); min-height:24px; display:none; text-align:left; line-height:1.5;}
  .reply-box.show{display:block; animation:replyIn 0.4s ease;}
  @keyframes replyIn{from{opacity:0; transform:translateY(6px);} to{opacity:1; transform:translateY(0);}}
  footer{text-align:center; margin-top:36px; font-family:var(--mono); font-size:0.68rem; color:#4a5478; letter-spacing:0.04em;}
  @media(max-width:380px){.grid{grid-template-columns:repeat(2,1fr);}}
  @media(prefers-reduced-motion:reduce){*{animation-duration:0.01ms !important;}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">
      <svg class="bolt" viewBox="0 0 24 24" fill="none" stroke="url(#g)" stroke-width="2">
        <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#00d9ff"/><stop offset="100%" stop-color="#a78bfa"/></linearGradient></defs>
        <path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" stroke-linejoin="round" stroke-linecap="round"/>
      </svg>
      <span class="brand-gradient">EchoCore</span>
    </div>
    <div class="tagline"><span class="live-dot"></span> Live · Groq AI Powered</div>
  </header>

  <div class="dnd-banner" id="dnd-banner">🔕 Do Not Disturb is active</div>

  <div class="grid">
    <div class="card" id="card-temp"><div class="icon-wrap">🌡️</div><div class="label">Temperature</div><div class="value" id="temp">--<span class="unit"> °C</span></div></div>
    <div class="card" id="card-hum"><div class="icon-wrap">💧</div><div class="label">Humidity</div><div class="value" id="hum">--<span class="unit"> %</span></div></div>
    <div class="card" id="card-motion"><div class="icon-wrap">🚶</div><div class="label">Motion</div><div class="value" id="motion">--</div></div>
    <div class="card" id="card-gas"><div class="icon-wrap">💨</div><div class="label">Gas</div><div class="value" id="gas">--</div></div>
    <div class="card" id="card-gasval"><div class="icon-wrap">📊</div><div class="label">Gas Level</div><div class="value" id="gasval">--</div></div>
    <div class="card" id="card-fan"><div class="icon-wrap">🌀</div><div class="label">Fan</div><div class="value" id="fan">--</div></div>
    <div class="card" id="card-led"><div class="icon-wrap">💡</div><div class="label">Light</div><div class="value" id="led">--</div></div>
    <div class="card" id="card-alertled"><div class="icon-wrap">🔴</div><div class="label">Alert LED</div><div class="value" id="alertled">--</div></div>
  </div>

  <div class="section-title">Fan</div>
  <div class="controls">
    <button class="btn btn-on" onclick="cmd('/fan/on',this)">⏻ Turn On</button>
    <button class="btn btn-off" onclick="cmd('/fan/off',this)">⏼ Turn Off</button>
  </div>

  <div class="section-title">Buzzer</div>
  <div class="controls">
    <button class="btn btn-on" onclick="cmd('/buzzer/on',this)">🔔 Turn On</button>
    <button class="btn btn-off" onclick="cmd('/buzzer/off',this)">🔕 Turn Off</button>
  </div>

  <div class="section-title">Light</div>
  <div class="controls">
    <button class="btn btn-on" onclick="cmd('/led/on',this)">💡 Turn On</button>
    <button class="btn btn-off" onclick="cmd('/led/off',this)">🌑 Turn Off</button>
  </div>

  <div class="section-title">Alert LED</div>
  <div class="controls">
    <button class="btn btn-on" onclick="cmd('/alertled/on',this)">🔴 Turn On</button>
    <button class="btn btn-off" onclick="cmd('/alertled/off',this)">⚫ Turn Off</button>
  </div>

  <div class="section-title">Do Not Disturb</div>
  <div class="controls">
    <button class="btn btn-dnd" onclick="sendCommand('do not disturb for 60 minutes')">🔕 Enable</button>
    <button class="btn btn-dnd" onclick="sendCommand('turn off do not disturb')">🔔 Disable</button>
  </div>

  <div class="section-title">Demo Tools</div>
  <div class="controls">
    <button class="btn btn-test" onclick="cmd('/test_alert',this)">🧪 Test Alert — Gas + Buzzer + LED + WhatsApp</button>
  </div>

  <div class="voice-section">
    <p class="voice-hint">Say <strong>"Hey Echo"</strong> or tap the orb</p>
    <p class="voice-examples">"it's dark in here" · "good night" · "how's everything at home" · "what's the weather in Mumbai"</p>

    <!-- Mic permission error banner -->
    <div class="mic-permission-banner" id="mic-banner">
      <strong>🎙️ Microphone permission needed</strong>
      To fix this in Chrome:
      <ol>
        <li>Click the 🔒 lock icon in the address bar</li>
        <li>Set <strong>Microphone</strong> → <strong>Allow</strong></li>
        <li>Refresh this page and tap the orb again</li>
      </ol>
    </div>

    <div class="orb-zone" id="orb" onclick="startVoice()">
      <div class="orb-ring r3"></div>
      <div class="orb-ring r2"></div>
      <div class="orb-ring r1"></div>
      <div class="orb-core">
        <svg viewBox="0 0 24 24"><path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" stroke-linecap="round" stroke-linejoin="round"/><path d="M19 10v1a7 7 0 0 1-14 0v-1M12 18v4M9 22h6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <div class="wave-bars"><span></span><span></span><span></span><span></span><span></span></div>
      </div>
    </div>
    <div class="orb-status" id="voice-status">Tap orb or say "Hey Echo"…</div>
    <div class="reply-box" id="reply-box"></div>
  </div>

  <footer>ESP32 · Flask · Groq Llama 3 · OpenWeather · EchoCore v2</footer>
</div>

<script>
  const socket = io();

  // ── Mic state management ──────────────────────────────────
  let bgRecognizer   = null;   // background wake-word listener
  let isListening    = false;  // true while startVoice() recognition is active
  let micPermGranted = false;  // track if user has granted mic

  // ── Socket ────────────────────────────────────────────────
  socket.on('sensor_update', function(data){
    document.getElementById('temp').innerHTML = (data.temp ?? '--') + '<span class="unit"> °C</span>';
    document.getElementById('hum').innerHTML  = (data.humidity ?? '--') + '<span class="unit"> %</span>';
    document.getElementById('gasval').textContent = data.gas_val ?? '--';
    setCard('motion',  'card-motion',   data.motion,    'Detected', 'Clear', true);
    setCard('gas',     'card-gas',      data.gas,       'Detected', 'Clear', true);
    setCard('fan',     'card-fan',      data.fan,       'Running',  'Idle',  false);
    setCard('led',     'card-led',      data.clap_led,  'On',       'Off',   false);
    setCard('alertled','card-alertled', data.alert_led, 'ON',       'OFF',   true);
  });

  function setCard(valId, cardId, val, onText, offText, alertOnTrue){
    const el   = document.getElementById(valId);
    const card = document.getElementById(cardId);
    if(!el || !card) return;
    el.textContent = val ? onText : offText;
    card.classList.remove('state-alert','state-on');
    if(val && alertOnTrue)  card.classList.add('state-alert');
    if(val && !alertOnTrue) card.classList.add('state-on');
  }

  function cmd(endpoint, btnEl){
    ripple(btnEl);
    fetch(endpoint).then(r=>r.json()).then(d=>console.log(d));
  }

  function ripple(el){
    if(!el) return;
    const c = document.createElement('span');
    c.className = 'ripple';
    const rect = el.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    c.style.width = c.style.height = size+'px';
    c.style.left = (rect.width/2 - size/2)+'px';
    c.style.top  = (rect.height/2 - size/2)+'px';
    el.appendChild(c);
    setTimeout(()=>c.remove(), 600);
  }

  // ── Orb UI helpers ────────────────────────────────────────
  const orb      = document.getElementById('orb');
  const statusEl = document.getElementById('voice-status');
  const micBanner = document.getElementById('mic-banner');

  function setOrbState(state, label){
    orb.classList.remove('listening','thinking','speaking');
    statusEl.classList.remove('is-listening','is-thinking','is-speaking','is-error');
    if(state){ orb.classList.add(state); statusEl.classList.add('is-'+state); }
    statusEl.textContent = label;
  }

  function showMicBanner(show){
    micBanner.classList.toggle('show', show);
  }

  // ── Check if browser supports SpeechRecognition ──────────
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if(!SR){
    setOrbState('', 'Voice needs Chrome browser');
  }

  // ── Stop background listener safely ──────────────────────
  function stopBgListener(){
    if(bgRecognizer){
      try{ bgRecognizer.abort(); } catch(e){}
      bgRecognizer = null;
    }
  }

  // ── Background wake-word listener ─────────────────────────
  function startContinuousListening(){
    if(!SR || isListening) return;   // don't run if voice command is active

    stopBgListener();                 // clear any existing instance first

    const cr = new SR();
    cr.lang = 'en-US';
    cr.continuous = false;
    cr.interimResults = false;
    bgRecognizer = cr;

    cr.onresult = (e) => {
      const heard = e.results[0][0].transcript.toLowerCase();
      console.log('Wake word check:', heard);
      if(heard.includes('echo') || heard.includes('eco')){
        setOrbState('listening','✦ Wake word detected');
        startVoice();
      }
    };

    cr.onerror = (e) => {
      // 'aborted' fires normally when we call abort() — ignore it
      // 'not-allowed' means mic is blocked
      if(e.error === 'aborted') return;
      if(e.error === 'not-allowed'){
        showMicBanner(true);
        setOrbState('is-error', '🚫 Mic blocked — see instructions above');
        return;
      }
      console.warn('BG recognizer error:', e.error);
    };

    cr.onend = () => {
      bgRecognizer = null;
      // restart only if startVoice() is not active
      if(!isListening){
        setTimeout(startContinuousListening, 400);
      }
    };

    try{ cr.start(); }
    catch(e){ console.warn('BG start error:', e); }
  }

  // ── Main voice command ────────────────────────────────────
  function startVoice(){
    if(!SR){
      setOrbState('', 'Voice needs Chrome browser');
      return;
    }

    // Stop background listener before starting command listener
    stopBgListener();
    isListening = true;
    showMicBanner(false);

    const r = new SR();
    r.lang = 'en-US';
    r.continuous = false;
    r.interimResults = false;

    r.onstart = () => {
      micPermGranted = true;
      setOrbState('listening','🎙 Listening…');
    };

    r.onresult = (e) => {
      const command = e.results[0][0].transcript;
      setOrbState('thinking', '"' + command + '"');
      sendCommand(command);
    };

    r.onerror = (e) => {
      isListening = false;
      if(e.error === 'not-allowed' || e.error === 'permission-denied'){
        showMicBanner(true);
        setOrbState('is-error', '🚫 Mic blocked — see instructions above');
        return;
      }
      if(e.error === 'no-speech'){
        setOrbState('', 'No speech detected — tap to try again');
        setTimeout(startContinuousListening, 600);
        return;
      }
      if(e.error === 'aborted'){
        // user or system aborted, just restart bg
        setOrbState('', 'Tap orb or say "Hey Echo"…');
        setTimeout(startContinuousListening, 400);
        return;
      }
      setOrbState('is-error', 'Error: ' + e.error);
      setTimeout(startContinuousListening, 1000);
    };

    r.onend = () => {
      // If onresult didn't fire (no speech / aborted before result)
      // isListening will be reset in onerror or after sendCommand
      if(isListening && orb.classList.contains('listening')){
        isListening = false;
        setOrbState('', 'Tap orb or say "Hey Echo"…');
        setTimeout(startContinuousListening, 400);
      }
    };

    try{ r.start(); }
    catch(e){
      isListening = false;
      console.warn('Voice start error:', e);
      setOrbState('', 'Tap orb or say "Hey Echo"…');
      setTimeout(startContinuousListening, 600);
    }
  }

  // ── Send command to Flask ─────────────────────────────────
  function sendCommand(command){
    isListening = false;
    setOrbState('thinking','🤔 Thinking…');
    fetch('/voice_command',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({command: command})
    })
    .then(r=>r.json())
    .then(data=>{
      setOrbState('speaking','Responding…');
      const box = document.getElementById('reply-box');
      box.classList.add('show');
      box.textContent = data.reply;
      setTimeout(()=>{
        setOrbState('','Tap orb or say "Hey Echo"…');
        setTimeout(startContinuousListening, 500);
      }, 2600);
    })
    .catch(()=>{
      setOrbState('is-error','Connection error');
      setTimeout(startContinuousListening, 1500);
    });
  }

  // ── DND Status ────────────────────────────────────────────
  function checkDND(){
    fetch('/dnd_status').then(r=>r.json()).then(data=>{
      document.getElementById('dnd-banner').classList.toggle('show', !!data.dnd_active);
    }).catch(()=>{});
  }
  setInterval(checkDND, 5000);

  // ── Init ──────────────────────────────────────────────────
  fetch('/sensor').then(r=>r.json()).then(data=>{
    socket.emit('sensor_update', data);
  }).catch(()=>{});

  window.addEventListener('load', () => {
    checkDND();
    // Request mic permission proactively on load
    if(SR && navigator.mediaDevices && navigator.mediaDevices.getUserMedia){
      navigator.mediaDevices.getUserMedia({ audio: true })
        .then(stream => {
          micPermGranted = true;
          showMicBanner(false);
          // Stop the stream immediately — we only needed the permission grant
          stream.getTracks().forEach(t => t.stop());
          setTimeout(startContinuousListening, 800);
        })
        .catch(err => {
          console.warn('Mic permission denied on load:', err);
          showMicBanner(true);
          setOrbState('is-error', '🚫 Mic blocked — see instructions above');
        });
    } else {
      setTimeout(startContinuousListening, 1000);
    }
  });
</script>
</body>
</html>
"""

if __name__ == '__main__':
    print("=" * 50)
    print("  EchoCore Flask Server — Full Feature Set")
    print("=" * 50)
    print(f"  Dashboard (this PC) : http://localhost:5000")
    print(f"  LAN address (ESP32) : http://10.198.46.196:5000")
    print("=" * 50)
    speak("EchoCore is online and ready.")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)