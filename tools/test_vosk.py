import json
import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer

SAMPLE_RATE = 16000
MODEL_PATH = "models/vosk-pt"

# Grammar fechado: só reconhece estas frases (melhora MUITO a precisão)
GRAMMAR = [
    "evo",
    "fecha evo",
    "fechar evo",
    "dormir",
    "acordar",
    "hibernar",
    "bloquear",
    "cancela",
    "confirmo",
    "teste"
]

print("[TEST] A carregar modelo VOSK...")
model = Model(MODEL_PATH)

print("[TEST] A iniciar recognizer com grammar fechado...")
rec = KaldiRecognizer(model, SAMPLE_RATE, json.dumps(GRAMMAR))
rec.SetWords(False)

print("[TEST] Diz uma destas frases (5 segundos):")
print("   - " + "\n   - ".join(GRAMMAR))
print("[TEST] A gravar...")

audio = sd.rec(int(5 * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
sd.wait()

samples = audio.flatten()
samples = np.clip(samples, -1.0, 1.0)
audio_int16 = (samples * 32767).astype(np.int16)

print("[TEST] A processar...")
rec.AcceptWaveform(audio_int16.tobytes())
result = rec.FinalResult()

try:
    data = json.loads(result)
    text = (data.get("text") or "").strip()
except Exception:
    text = ""

print("\n[RESULTADO]")
print("Texto:", text if text else "(vazio)")
