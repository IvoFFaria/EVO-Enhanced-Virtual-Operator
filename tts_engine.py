"""
EVO - Text-to-Speech Engine (Windows nativo)

Melhoria:
- Permite selecionar voz por NOME exato (mais fiável do que culture)
- Mantém fallback se a voz não existir
"""

from __future__ import annotations

import logging
import platform
import queue
import threading
import subprocess
from dataclasses import dataclass

log = logging.getLogger("EVO.TTS")


@dataclass
class TTSConfig:
    enabled: bool = True
    rate: int = 0        # -10 a +10
    volume: int = 100    # 0 a 100

    # Preferência 1: escolher por nome EXATO (recomendado)
    voice_name: str | None = None  # ex: "Microsoft Maria Desktop"

    # Preferência 2 (fallback): cultura (best-effort)
    voice_culture_hint: str | None = "pt-PT"


class TTSEngine:
    def __init__(self, cfg: TTSConfig | None = None):
        self.cfg = cfg or TTSConfig()
        self._q: "queue.Queue[str]" = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)

        if platform.system().lower() != "windows":
            self.cfg.enabled = False
            log.warning("TTS desativado: apenas suportado em Windows.")

        self._thread.start()
        log.info("TTSEngine iniciado (enabled=%s).", self.cfg.enabled)

    def speak(self, text: str) -> None:
        if not self.cfg.enabled:
            return
        t = (text or "").strip()
        if not t:
            return
        self._q.put(t)

    def stop(self) -> None:
        self._stop.set()
        self._q.put("")
        log.info("TTSEngine a parar...")

    def _worker(self) -> None:
        while not self._stop.is_set():
            text = self._q.get()
            if self._stop.is_set():
                break
            if not text:
                continue
            try:
                self._speak_windows(text)
            except Exception as e:
                log.exception("Erro no TTS: %s", e)

    def _speak_windows(self, text: str) -> None:
        safe = text.replace("'", "''")

        select_voice = ""

        # 1) Seleção por nome (preferida)
        if self.cfg.voice_name:
            select_voice += (
                f"try {{ $s.SelectVoice('{self.cfg.voice_name}'); }} catch {{ }}; "
            )

        # 2) Seleção por cultura (fallback)
        if self.cfg.voice_culture_hint:
            select_voice += (
                "$v = $s.GetInstalledVoices() | "
                f"Where-Object {{$_.VoiceInfo.Culture.Name -like '*{self.cfg.voice_culture_hint}*'}} | "
                "Select-Object -First 1; "
                "if ($v) { try { $s.SelectVoice($v.VoiceInfo.Name) } catch { } }; "
            )

        ps = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Rate = {int(self.cfg.rate)}; "
            f"$s.Volume = {int(self.cfg.volume)}; "
            f"{select_voice}"
            f"$s.Speak('{safe}');"
        )

        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            check=False,
        )
