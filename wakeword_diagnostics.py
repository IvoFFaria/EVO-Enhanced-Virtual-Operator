"""
EVO - Wake Word Diagnostics

Objetivo:
- Testar o wake word em tempo real a partir do microfone
- Mostrar "scores" e indicar quando deteta
- Ajudar a afinar a sensibilidade (threshold)

Como usar:
  python -m evo.wakeword_diagnostics

Notas:
- Não grava ficheiros
- Não envia nada para rede
"""

import time
import numpy as np
import sounddevice as sd

from .wakeword import create_wakeword_detector, WakeWordConfig


SAMPLE_RATE = 16000
BLOCK_SIZE = 1024  # ~64ms
KEYWORD = "EVO"
SENSITIVITY = 0.6  # começa aqui, ajusta depois


def main():
    cfg = WakeWordConfig(keyword=KEYWORD, sensitivity=SENSITIVITY, sample_rate=SAMPLE_RATE)
    detector = create_wakeword_detector(cfg)

    print("\n[EVO] Wake word diagnostics")
    print(f"- Keyword: {KEYWORD}")
    print(f"- Sensitivity (threshold): {SENSITIVITY}")
    print("- Fala: 'EVO' perto do microfone.\n")
    print("Dica: se detetar demasiado facilmente, sobe para 0.7/0.8. Se não detetar, desce para 0.5.\n")

    last_hit = 0.0

    def callback(indata, frames, time_info, status):
        nonlocal last_hit
        samples = np.squeeze(indata, axis=1).astype(np.float32, copy=False)

        detected = detector.feed(samples)

        # Evitar spam: só imprime DETETADO no máximo 1x por segundo
        now = time.time()
        if detected and (now - last_hit) > 1.0:
            last_hit = now
            print("[EVO] ✅ WAKE WORD DETETADO")

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_SIZE,
        channels=1,
        dtype="float32",
        callback=callback
    ):
        while True:
            time.sleep(0.25)


if __name__ == "__main__":
    main()
