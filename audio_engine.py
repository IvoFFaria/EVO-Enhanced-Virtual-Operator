"""
EVO - Enhanced Virtual Operator
Audio Engine (Wake word + VAD)

Responsabilidade:
- Capturar áudio do microfone (stream)
- Detetar wake word (local) -> on_wake()
- Detetar atividade de voz (VAD simples por energia, MVP) -> on_voice_start/on_voice_end
- Emitir chunks de áudio SEMPRE -> on_audio_chunk(samples)
  (a app decide se grava para STT ou apenas mantém pré-roll)

Notas:
- Não grava ficheiros.
- Não envia nada para rede.
- Processa apenas em memória, em tempo real.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from .wakeword import create_wakeword_detector, WakeWordConfig, BaseWakeWordDetector

log = logging.getLogger("EVO.AudioEngine")


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    block_size: int = 512          # ~32ms a 16kHz
    channels: int = 1
    vad_threshold: float = 0.004   # energia RMS (ajusta mais tarde)
    vad_hangover_ms: int = 400     # mantém "voz ativa" por um bocado após silêncio


class AudioEngine:
    def __init__(
        self,
        cfg: AudioConfig = AudioConfig(),
        wake_cfg: Optional[WakeWordConfig] = None,
        wake_detector: Optional[BaseWakeWordDetector] = None,
        on_wake: Optional[Callable[[], None]] = None,
        on_voice_start: Optional[Callable[[], None]] = None,
        on_voice_end: Optional[Callable[[], None]] = None,
        on_audio_chunk: Optional[Callable[[np.ndarray], None]] = None,
    ):
        self.cfg = cfg

        # Wake word: usa detector injetado OU cria automaticamente
        self.wake_cfg = wake_cfg or WakeWordConfig(keyword="EVO", sensitivity=0.6, sample_rate=cfg.sample_rate)
        self.wake_detector: BaseWakeWordDetector = wake_detector or create_wakeword_detector(self.wake_cfg)

        # callbacks
        self.on_wake = on_wake
        self.on_voice_start = on_voice_start
        self.on_voice_end = on_voice_end
        self.on_audio_chunk = on_audio_chunk

        self._stream: Optional[sd.InputStream] = None
        self._running = False
        self._lock = threading.Lock()

        # VAD state
        self._voice_active = False
        self._last_voice_ms = 0.0

        # Debug leve (não spam): para logar RMS 2x/seg
        self._last_dbg_ms = 0.0

    # ---------- Lifecycle ----------

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True

        log.info("A iniciar AudioEngine (sr=%d, block=%d).", self.cfg.sample_rate, self.cfg.block_size)

        self._stream = sd.InputStream(
            samplerate=self.cfg.sample_rate,
            blocksize=self.cfg.block_size,
            channels=self.cfg.channels,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False

        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        log.info("AudioEngine parado.")

    # ---------- Internals ----------

    def _callback(self, indata, frames, time_info, status) -> None:
        # Callback no thread de áudio: manter ultra-rápido
        if status:
            # se quiseres, mais tarde mandamos isto para logs de debug
            pass

        with self._lock:
            if not self._running:
                return

        # indata: shape (frames, channels)
        samples = np.squeeze(indata, axis=1) if indata.ndim == 2 else indata
        if samples.size == 0:
            return

        # Copiar só uma vez (evita depender do buffer interno do sounddevice)
        chunk = samples.astype(np.float32, copy=True)

        # 0) Enviar SEMPRE áudio cru (pré-roll/gestão fica na app)
        if self.on_audio_chunk:
            try:
                self.on_audio_chunk(chunk)
            except Exception:
                pass

        # 1) Wake word
        try:
            if self.wake_detector.feed(chunk):
                if self.on_wake:
                    self.on_wake()
        except Exception:
            # nunca crashar por wakeword
            pass

        # 2) VAD simples por energia RMS
        rms = float(np.sqrt(np.mean(np.square(chunk))))
        now_ms = time.time() * 1000.0

        if rms >= self.cfg.vad_threshold:
            self._last_voice_ms = now_ms
            if not self._voice_active:
                self._voice_active = True
                if self.on_voice_start:
                    self.on_voice_start()
        else:
            if self._voice_active:
                if (now_ms - self._last_voice_ms) >= self.cfg.vad_hangover_ms:
                    self._voice_active = False
                    if self.on_voice_end:
                        self.on_voice_end()

        # Debug leve: mostra RMS e voice_active 2x/seg (útil para afinar threshold)
        if (now_ms - self._last_dbg_ms) >= 500:
            self._last_dbg_ms = now_ms
            log.debug("RMS=%.5f | voice_active=%s | thr=%.5f", rms, self._voice_active, self.cfg.vad_threshold)

    # ---------- Exposed state ----------

    def is_voice_active(self) -> bool:
        return self._voice_active
