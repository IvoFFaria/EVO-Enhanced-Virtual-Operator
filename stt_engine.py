"""
EVO - Speech-to-Text Engine (offline)

Objetivo:
- Transcrever fala localmente (offline) após wake word
- API simples:
    - transcribe_float32(samples, sample_rate) -> text

Motores suportados (por ordem de preferência):
1) faster-whisper (recomendado) -> pip install faster-whisper
2) openai-whisper              -> pip install openai-whisper

Mudanças importantes (para NÃO ficar mudo):
- Desliga vad_filter no faster-whisper por defeito (tu já tens VAD antes do STT).
- Normaliza áudio e aplica trim de silêncio leve (evita áudio “baixo” ou muito silêncio).
- Logs com duração/RMS para afinação.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

log = logging.getLogger("EVO.STT")


@dataclass
class STTConfig:
    language: str = "pt"           # "pt" para português
    model: str = "small"           # tiny / base / small / medium / large-v3
    device: str = "cpu"            # "cpu" por defeito (seguro)
    compute_type: str = "int8"     # faster-whisper: int8 é bom em CPU

    # Qualidade/robustez
    beam_size: int = 5
    best_of: int = 5
    temperature: float = 0.0

    # IMPORTANTÍSSIMO: como já tens VAD no pipeline, aqui deve ser False.
    use_internal_vad: bool = False

    # Pré-processamento
    normalize_peak: float = 0.95   # normaliza pico para ~0.95
    trim_silence: bool = True
    trim_rms_threshold: float = 0.0035  # ajustável; não é o mesmo que o VAD
    min_audio_s: float = 0.6       # abaixo disto, normalmente dá lixo/vazio


class BaseSTTEngine:
    def transcribe_float32(self, samples: np.ndarray, sample_rate: int) -> str:
        raise NotImplementedError


class NullSTTEngine(BaseSTTEngine):
    """Fallback seguro: não transcreve (devolve string vazia)."""
    def transcribe_float32(self, samples: np.ndarray, sample_rate: int) -> str:
        return ""


def _rms(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x.astype(np.float32, copy=False)))))


def _trim_silence_edges(x: np.ndarray, rms_thr: float, block: int = 256) -> np.ndarray:
    """
    Trim leve de silêncio no início e no fim.
    Trabalha por blocos pequenos para ser rápido.
    """
    n = x.size
    if n < block * 2:
        return x

    # início
    start = 0
    while start + block <= n:
        if _rms(x[start:start + block]) >= rms_thr:
            break
        start += block

    # fim
    end = n
    while end - block >= 0:
        if _rms(x[end - block:end]) >= rms_thr:
            break
        end -= block

    if end <= start:
        return x

    return x[start:end]


def _normalize(x: np.ndarray, target_peak: float) -> np.ndarray:
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    if peak <= 1e-6:
        return x
    gain = target_peak / peak
    # limitar ganho para não amplificar ruído de forma absurda
    gain = min(gain, 10.0)
    return (x * gain).astype(np.float32, copy=False)


class FasterWhisperEngine(BaseSTTEngine):
    def __init__(self, cfg: STTConfig):
        self.cfg = cfg
        from faster_whisper import WhisperModel  # type: ignore

        self.model = WhisperModel(
            cfg.model,
            device=cfg.device,
            compute_type=cfg.compute_type,
        )
        log.info(
            "STT: faster-whisper ativo (model=%s, device=%s, compute=%s, internal_vad=%s).",
            cfg.model, cfg.device, cfg.compute_type, cfg.use_internal_vad
        )

    def transcribe_float32(self, samples: np.ndarray, sample_rate: int) -> str:
        x = samples.astype(np.float32, copy=False).flatten()

        dur_s = x.size / float(sample_rate) if sample_rate else 0.0
        if dur_s < self.cfg.min_audio_s:
            log.debug("STT: áudio curto (%.2fs) -> ignora", dur_s)
            return ""

        # Pré-processamento
        if self.cfg.trim_silence:
            x = _trim_silence_edges(x, self.cfg.trim_rms_threshold)

        x = _normalize(x, self.cfg.normalize_peak)

        dur2_s = x.size / float(sample_rate) if sample_rate else 0.0
        rms = _rms(x)

        # Transcrição
        try:
            segments, info = self.model.transcribe(
                x,
                language=self.cfg.language,
                beam_size=self.cfg.beam_size,
                best_of=self.cfg.best_of,
                temperature=self.cfg.temperature,
                vad_filter=self.cfg.use_internal_vad,  # <- agora controlado e por defeito False
            )
        except TypeError:
            # compatibilidade com versões diferentes
            segments, info = self.model.transcribe(
                x,
                language=self.cfg.language,
                vad_filter=self.cfg.use_internal_vad,
            )

        parts = []
        for seg in segments:
            t = (getattr(seg, "text", "") or "").strip()
            if t:
                parts.append(t)

        text = " ".join(parts).strip()
        log.info("STT: dur=%.2fs->%.2fs rms=%.5f => '%s'", dur_s, dur2_s, rms, text)
        return text


class OpenAIWhisperEngine(BaseSTTEngine):
    def __init__(self, cfg: STTConfig):
        self.cfg = cfg
        import whisper  # type: ignore

        self.whisper = whisper
        self.model = whisper.load_model(cfg.model)
        log.info("STT: openai-whisper ativo (model=%s).", cfg.model)

    def transcribe_float32(self, samples: np.ndarray, sample_rate: int) -> str:
        x = samples.astype(np.float32, copy=False).flatten()

        dur_s = x.size / float(sample_rate) if sample_rate else 0.0
        if dur_s < self.cfg.min_audio_s:
            return ""

        if self.cfg.trim_silence:
            x = _trim_silence_edges(x, self.cfg.trim_rms_threshold)

        x = _normalize(x, self.cfg.normalize_peak)

        result = self.model.transcribe(
            x,
            language=self.cfg.language,
            fp16=False,
            temperature=self.cfg.temperature,
        )
        txt = (result.get("text") or "").strip()
        log.info("STT(openai): dur=%.2fs => '%s'", dur_s, txt)
        return txt


def create_stt_engine(cfg: Optional[STTConfig] = None) -> BaseSTTEngine:
    cfg = cfg or STTConfig()

    # 1) faster-whisper
    try:
        return FasterWhisperEngine(cfg)
    except Exception as e:
        log.warning("STT: faster-whisper não disponível (%s).", e)

    # 2) openai-whisper
    try:
        return OpenAIWhisperEngine(cfg)
    except Exception as e:
        log.warning("STT: openai-whisper não disponível (%s).", e)

    log.warning("STT: nenhum motor disponível. A transcrição está desativada.")
    return NullSTTEngine()
