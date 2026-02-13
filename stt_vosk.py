import json
import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from vosk import Model, KaldiRecognizer

log = logging.getLogger("EVO.STT.VOSK")


@dataclass
class VoskConfig:
    model_path: str = "models/vosk-pt"
    sample_rate: int = 16000
    grammar: Optional[List[str]] = None
    fallback_to_free: bool = True
    max_words: int = 10
    frame_ms: int = 40              # tamanho do "stream chunk" (ms)
    debug_raw: bool = False


class VoskSTTEngine:
    """
    STT offline com VOSK (modo robusto):
    - Alimenta o recognizer em "stream" (chunks pequenos), como numa app real.
    - Junta partials + final.
    - Tenta grammar -> se vazio, tenta free (fallback).
    """

    def __init__(self, cfg: VoskConfig):
        self.cfg = cfg
        self.model = Model(cfg.model_path)
        self._build_recognizers()

    def _build_recognizers(self):
        self.rec_grammar = None
        if self.cfg.grammar:
            self.rec_grammar = KaldiRecognizer(self.model, self.cfg.sample_rate, json.dumps(self.cfg.grammar))
            self.rec_grammar.SetWords(False)
            log.info("VOSK: GRAMMAR ativo (%d frases).", len(self.cfg.grammar))

        self.rec_free = KaldiRecognizer(self.model, self.cfg.sample_rate)
        self.rec_free.SetWords(False)
        log.info("VOSK: FREE ativo (fallback=%s).", self.cfg.fallback_to_free)

    def reset(self):
        self._build_recognizers()

    def transcribe_float32(self, samples: np.ndarray, sample_rate: int) -> str:
        if samples is None or samples.size == 0:
            return ""

        # VOSK trabalha a 16k normalmente; aqui assumimos que o teu pipeline já está a 16k
        x = samples.astype(np.float32, copy=False).flatten()
        x = np.clip(x, -1.0, 1.0)

        audio_int16 = (x * 32767).astype(np.int16)

        # 1) tentar grammar
        text = self._run_stream(self.rec_grammar, audio_int16) if self.rec_grammar else ""

        # 2) fallback livre se vazio
        if (not text) and self.cfg.fallback_to_free:
            text = self._run_stream(self.rec_free, audio_int16)

        text = self._cleanup_command_text(text)
        log.info("VOSK => '%s'", text)
        return text

    def _run_stream(self, rec: KaldiRecognizer, audio_int16: np.ndarray) -> str:
        if rec is None:
            return ""

        # reset do recognizer: KaldiRecognizer não tem reset explícito,
        # por isso recriamos pelo caminho mais seguro (reset externo quando necessário).
        # Aqui, para manter 1 ficheiro só e simples, usamos rec como está.

        frame_len = int(self.cfg.sample_rate * (self.cfg.frame_ms / 1000.0))
        frame_len = max(200, frame_len)  # mínimo seguro

        parts: List[str] = []

        # alimentar em chunks
        i = 0
        n = audio_int16.size
        while i < n:
            chunk = audio_int16[i:i + frame_len]
            i += frame_len

            ok = rec.AcceptWaveform(chunk.tobytes())
            if ok:
                # quando ok=True, há um "Result" completo intermédio
                r = rec.Result()
                if self.cfg.debug_raw:
                    log.info("RAW result: %s", r)
                t = self._extract_text(r)
                if t:
                    parts.append(t)
            else:
                # partials: opcional mas ajuda a não ficar vazio
                pr = rec.PartialResult()
                if self.cfg.debug_raw:
                    log.debug("RAW partial: %s", pr)
                t = self._extract_partial(pr)
                if t:
                    parts.append(t)

        final = rec.FinalResult()
        if self.cfg.debug_raw:
            log.info("RAW final: %s", final)

        t_final = self._extract_text(final)
        if t_final:
            parts.append(t_final)

        # junta e dedup
        joined = " ".join(parts).strip().lower()
        joined = " ".join(joined.split())  # normalize spaces
        return joined

    @staticmethod
    def _extract_text(raw_json: str) -> str:
        try:
            data = json.loads(raw_json)
            return (data.get("text") or "").strip().lower()
        except Exception:
            return ""

    @staticmethod
    def _extract_partial(raw_json: str) -> str:
        try:
            data = json.loads(raw_json)
            return (data.get("partial") or "").strip().lower()
        except Exception:
            return ""

    def _cleanup_command_text(self, text: str) -> str:
        if not text:
            return ""

        words = text.split()
        if not words:
            return ""

        # limitar palavras
        if len(words) > self.cfg.max_words:
            words = words[-self.cfg.max_words:]

        # remover repetição consecutiva
        cleaned = []
        for w in words:
            if not cleaned or cleaned[-1] != w:
                cleaned.append(w)

        joined = " ".join(cleaned)

        # normalizações de comandos
        if "fechar evo" in joined:
            return "fecha evo"
        if "fecha evo" in joined:
            return "fecha evo"

        # se só for "evo" repetido
        if cleaned and all(w == "evo" for w in cleaned):
            return "evo"

        return joined.strip()
