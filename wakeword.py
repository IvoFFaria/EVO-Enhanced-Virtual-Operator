"""
EVO - Enhanced Virtual Operator
Wake Word Detector

Objetivo:
- Fornecer um detetor de wake word "EVO" (local)
- Interface compatível com o AudioEngine:
    detector.feed(samples: np.ndarray) -> bool

Implementação:
- Preferência: openwakeword (local, leve)
- Fallback seguro: nunca deteta (para não crashar o app)

Notas:
- Este ficheiro NÃO capta áudio por si. Apenas processa amostras (samples).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

log = logging.getLogger("EVO.WakeWord")


@dataclass
class WakeWordConfig:
    # Nome do wake word (usado para logs / identidade)
    keyword: str = "EVO"
    # Sensibilidade típica: 0.4–0.8 (depende do motor/modelo)
    sensitivity: float = 0.5
    # Taxa esperada pelo motor (vamos alinhar com AudioEngine: 16000)
    sample_rate: int = 16000


class BaseWakeWordDetector:
    def feed(self, samples: np.ndarray) -> bool:
        """Retorna True se detetar wake word."""
        raise NotImplementedError


class NullWakeWordDetector(BaseWakeWordDetector):
    """Fallback seguro: nunca deteta, nunca falha."""
    def feed(self, samples: np.ndarray) -> bool:
        return False


class OpenWakeWordDetector(BaseWakeWordDetector):
    """
    Detetor com openwakeword (se disponível).
    Este wrapper tenta manter a API simples e estável.
    """
    def __init__(self, cfg: WakeWordConfig):
        self.cfg = cfg
        self._model = None
        self._enabled = False

        try:
            # openwakeword
            # Nota: a API exata pode variar; este wrapper foi feito para falhar com segurança.
            from openwakeword.model import Model  # type: ignore
            self._model = Model()
            self._enabled = True
            log.info("Wake word ativo (openwakeword). Keyword='%s'", cfg.keyword)
        except Exception as e:
            self._enabled = False
            self._model = None
            log.warning("openwakeword não disponível / falhou a iniciar. Fallback para NULL. Detalhe: %s", e)

    def feed(self, samples: np.ndarray) -> bool:
        if not self._enabled or self._model is None:
            return False

        try:
            # Garantir float32 e mono
            x = samples.astype(np.float32, copy=False)

            # openwakeword espera tipicamente arrays 1D; processamos um bloco
            # A saída do modelo costuma ser um dict de scores por keyword/modelo.
            pred = self._model.predict(x)

            # Tentativa robusta de extrair score:
            # - se pred for dict: procurar max score
            # - se tiver keyword específica, usar essa (quando existir)
            score = None

            if isinstance(pred, dict) and pred:
                # Alguns modelos retornam: { "keyword": float, ... }
                # Outros: { "modelname": float, ... }
                if self.cfg.keyword in pred:
                    score = float(pred[self.cfg.keyword])
                else:
                    score = float(max(pred.values()))

            if score is None:
                return False

            # Limiar aproximado: ajusta-se depois em testes reais
            # (openwakeword costuma produzir scores entre 0 e 1)
            detected = score >= self.cfg.sensitivity
            return detected

        except Exception:
            # Nunca crashar por causa do wake word
            return False


def create_wakeword_detector(cfg: Optional[WakeWordConfig] = None) -> BaseWakeWordDetector:
    """
    Factory: cria o melhor detetor disponível.
    """
    cfg = cfg or WakeWordConfig()

    # Tenta openwakeword
    detector = OpenWakeWordDetector(cfg)
    if isinstance(detector, OpenWakeWordDetector) and detector._enabled:
        return detector

    # Fallback
    return NullWakeWordDetector()
