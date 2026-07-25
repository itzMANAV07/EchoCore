# ============================================================
#  EchoCore - Vosk Voice Listener
#  Always-on background listening via PC microphone
#  No browser needed
# ============================================================

import vosk
import sounddevice as sd
import queue
import json
import threading

# ── Load Vosk model once ──────────────────────────────────────
MODEL_PATH = "model"
model = vosk.Model(MODEL_PATH)

SAMPLE_RATE = 16000
audio_queue = queue.Queue()

# ── Callback — feeds mic audio into the queue ─────────────────
def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"Audio status: {status}")
    audio_queue.put(bytes(indata))

# ============================================================
#  MAIN LISTENING LOOP
#  on_text: function called with every recognized phrase
# ============================================================
def start_listening(on_text):
    rec = vosk.KaldiRecognizer(model, SAMPLE_RATE)

    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=8000,
                            dtype='int16', channels=1,
                            callback=audio_callback):
        print("🎙️  EchoCore is listening continuously...")
        while True:
            data = audio_queue.get()
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = result.get('text', '').strip()
                if text:
                    print(f"Heard: {text}")
                    on_text(text)

# ============================================================
#  RUN IN BACKGROUND THREAD
# ============================================================
def run_in_background(on_text):
    thread = threading.Thread(target=start_listening, args=(on_text,), daemon=True)
    thread.start()
    return thread


# ── Standalone test ────────────────────────────────────────────
if __name__ == '__main__':
    def print_text(text):
        text_lower = text.lower()
        wake_variants = ['hey echo', 'a echo', 'a ago', 'hey eco', 
                          'hey eko', 'a eco', 'k echo', 'hey ego']
        
        if any(variant in text_lower for variant in wake_variants):
            print(f"[WAKE WORD DETECTED] Heard: '{text}'")
        else:
            print(f"[TEST] You said: {text}")

    start_listening(print_text)