import sounddevice as sd
import numpy as np

print("A ouvir microfone... fala agora (Ctrl+C para sair)")

def callback(indata, frames, time, status):
    volume = np.linalg.norm(indata) * 10
    print(f"Volume: {volume:.3f}")

with sd.InputStream(
    channels=1,
    samplerate=16000,
    callback=callback
):
    while True:
        sd.sleep(500)
