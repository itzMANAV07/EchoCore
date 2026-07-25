# ============================================================
#  EchoCore - Groq Whisper + VAD Voice Pipeline
#  Records only while you're speaking, stops automatically on pause
#  Handles Hinglish and accented English far better than Vosk
# ============================================================

import sounddevice as sd
import numpy as np
import wave
import io
import time
import collections
from groq import Groq

try:
    import webrtcvad
    VAD_AVAILABLE = True
except ImportError:
    VAD_AVAILABLE = False
    print("webrtcvad not installed — falling back to energy-based detection")

# ── Paste your NEW Groq API key here ───────────────────────────
GROQ_API_KEY = "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"
client = Groq(api_key=GROQ_API_KEY)

SAMPLE_RATE = 16000

if VAD_AVAILABLE:
    vad = webrtcvad.Vad(2)

# =============================================================
#  RECORD UNTIL SILENCE — energy based (your active method)
# =============================================================
def record_until_silence_energy(max_duration=8, silence_limit=1.2,
                                  silence_threshold=150):
    frame_duration = 0.1
    frame_size = int(SAMPLE_RATE * frame_duration)

    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16',
                             blocksize=frame_size)
    stream.start()

    print("🎙️  Waiting for you to speak...")
    voiced_frames = []
    triggered = False
    silence_chunks = 0
    max_silence_chunks = int(silence_limit / frame_duration)
    start_time = time.time()

    while time.time() - start_time < max_duration:
        frame, _ = stream.read(frame_size)
        volume = np.abs(frame).mean()

        if volume > silence_threshold:
            if not triggered:
                triggered = True
                print("🎤 Speech detected, recording...")
            voiced_frames.append(frame)
            silence_chunks = 0
        elif triggered:
            voiced_frames.append(frame)
            silence_chunks += 1
            if silence_chunks > max_silence_chunks:
                print("✅ Done speaking.")
                break

    stream.stop()
    stream.close()

    if not voiced_frames:
        return None
    return np.concatenate(voiced_frames)

# =============================================================
#  UNIFIED RECORD FUNCTION
# =============================================================
def smart_record(max_duration=8, silence_limit=1.0):
    return record_until_silence_energy(max_duration, silence_limit)

# =============================================================
#  CONVERT NUMPY AUDIO TO WAV BYTES
# =============================================================
def audio_to_wav_bytes(audio_data):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data.tobytes())
    buffer.seek(0)
    return buffer

# =============================================================
#  TRANSCRIBE USING GROQ WHISPER
# =============================================================
def transcribe_audio(audio_data):
    if audio_data is None or len(audio_data) < SAMPLE_RATE * 0.3:
        return ""

    wav_bytes = audio_to_wav_bytes(audio_data)
    wav_bytes.name = "audio.wav"

    try:
        transcription = client.audio.transcriptions.create(
            file=wav_bytes,
            model="whisper-large-v3",
            response_format="text"
        )
        return transcription.strip()
    except Exception as e:
        print(f"Transcription error: {e}")
        return ""

# =============================================================
#  WAKE WORD LISTENING LOOP
# =============================================================
def listen_for_wake_word(on_wake_detected):
    print("🎙️  EchoCore listening for wake word 'Hey Echo'...")
    while True:
        audio = smart_record(max_duration=5, silence_limit=0.8)
        text = transcribe_audio(audio)

        if text:
            print(f"Heard: {text}")
            text_lower = text.lower()
            if 'echo' in text_lower or 'eco' in text_lower:
                print("✅ Wake word detected!")
                on_wake_detected()

# =============================================================
#  LISTEN FOR FULL COMMAND
# =============================================================
def listen_for_command():
    print("🎙️  Listening for your command...")
    audio = smart_record(max_duration=8, silence_limit=1.0)
    text = transcribe_audio(audio)
    print(f"Command heard: {text}")
    return text


# ── Standalone test ────────────────────────────────────────────
if __name__ == '__main__':
    def on_wake():
        command = listen_for_command()
        print(f"[FINAL COMMAND] {command}")

    listen_for_wake_word(on_wake)