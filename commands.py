"""
EVO - Enhanced Virtual Operator
Commands / Intent Parser (MVP)

Responsabilidade:
- Receber texto (do STT no futuro, ou de testes manuais agora)
- Normalizar a frase
- Detetar intenção (intent) e eventuais parâmetros
- NUNCA executar ações críticas diretamente (apenas retorna intenção)
"""

from dataclasses import dataclass
from enum import Enum, auto
import re
from typing import Optional

from .config import CONFIG


class Intent(Enum):
    UNKNOWN = auto()
    WAKE = auto()
    SLEEP = auto()
    EXIT = auto()
    REPEAT = auto()
    HIBERNATE = auto()
    LOCK = auto()
    SUSPEND = auto()
    CANCEL = auto()
    CONFIRM = auto()


@dataclass(frozen=True)
class ParsedCommand:
    intent: Intent
    confidence: float = 0.7
    raw_text: str = ""
    normalized_text: str = ""
    needs_confirmation: bool = False
    confirmation_kind: Optional[str] = None  # ex: "power.hibernate"


def normalize_text(text: str) -> str:
    """Normalização simples para PT (MVP)."""
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def _match_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def parse_command(text: str) -> ParsedCommand:
    """
    Converte texto em intenção.
    Nota: isto é determinístico (bom para segurança).
    """
    raw = text or ""
    norm = normalize_text(raw)

    # Confirmação / Cancelamento (muito importante para ações críticas)
    # Confirmação tem de ser explícita (segurança)
    if _match_any(norm, [r"\bconfirmo\b", r"\bsim,\s*confirmo\b", r"\bconfirmar\b", r"\bsegue\b"]):

        return ParsedCommand(Intent.CONFIRM, confidence=0.9, raw_text=raw, normalized_text=norm)

    if _match_any(norm, [r"\bcancela\b", r"\bcancelar\b", r"\bnão\b", r"\bnao\b", r"\bpara\b", r"\bdeixa\b"]):
        return ParsedCommand(Intent.CANCEL, confidence=0.9, raw_text=raw, normalized_text=norm)

    # Encerrar EVO
    if _match_any(norm, [r"\bfecha\b", r"\bfechar\b", r"\btermina\b", r"\bsair\b", r"\bencerrar\b"]):
        # Evitar confusão com "fecha a janela do browser" etc. (MVP simples)
        if _match_any(norm, [r"\bevo\b", r"\bassistente\b", r"\boperador\b"]):
            return ParsedCommand(Intent.EXIT, confidence=0.85, raw_text=raw, normalized_text=norm)
        # se só disser "fecha" sem contexto, mantemos como EXIT com confiança menor
        return ParsedCommand(Intent.EXIT, confidence=0.6, raw_text=raw, normalized_text=norm)

    # Dormir / Standby
    if _match_any(norm, [r"\bdormir\b", r"\bdorme\b", r"\bsilêncio\b", r"\bsilencio\b"]):
        return ParsedCommand(Intent.SLEEP, confidence=0.85, raw_text=raw, normalized_text=norm)

    # Repetir
    if _match_any(norm, [r"\brepete\b", r"\brepetir\b", r"\bvolta a dizer\b"]):
        return ParsedCommand(Intent.REPEAT, confidence=0.8, raw_text=raw, normalized_text=norm)

    # Ações de energia (não executa, só pede confirmação)
    wants_hibernate = _match_any(norm, [r"\bhiberna\b", r"\bhibernar\b", r"\bhibernação\b", r"\bhibernacao\b"])
    wants_lock = _match_any(norm, [r"\bbloqueia\b", r"\bbloquear\b", r"\btranca\b", r"\block\b"])
    wants_suspend = _match_any(norm, [r"\bsuspende\b", r"\bsuspender\b", r"\bsuspensão\b", r"\bsuspensao\b", r"\bsleep\b"])

    # Tratamento do comando "desligar" conforme política
    if _match_any(norm, [r"\bdesliga\b", r"\bdesligar\b", r"\bpower off\b"]):
        policy = (CONFIG.POWER_OFF_POLICY or "hibernate").lower()
        if policy == "hibernate":
            wants_hibernate = True
        elif policy == "ask":
            # aqui retornamos intenção HIBERNATE mas com baixa confiança e exige confirmação/clareza
            pc = ParsedCommand(
                Intent.HIBERNATE,
                confidence=0.55,
                raw_text=raw,
                normalized_text=norm,
                needs_confirmation=True,
                confirmation_kind="power.ask",
            )
            return pc
        elif policy == "refuse":
            return ParsedCommand(Intent.UNKNOWN, confidence=0.4, raw_text=raw, normalized_text=norm)

    if wants_hibernate:
        return ParsedCommand(
            Intent.HIBERNATE,
            confidence=0.85,
            raw_text=raw,
            normalized_text=norm,
            needs_confirmation=bool(CONFIG.REQUIRE_CONFIRM_FOR_POWER),
            confirmation_kind="power.hibernate" if CONFIG.REQUIRE_CONFIRM_FOR_POWER else None,
        )

    if wants_lock:
        return ParsedCommand(
            Intent.LOCK,
            confidence=0.8,
            raw_text=raw,
            normalized_text=norm,
            needs_confirmation=bool(CONFIG.REQUIRE_CONFIRM_FOR_POWER),
            confirmation_kind="power.lock" if CONFIG.REQUIRE_CONFIRM_FOR_POWER else None,
        )

    if wants_suspend:
        return ParsedCommand(
            Intent.SUSPEND,
            confidence=0.75,
            raw_text=raw,
            normalized_text=norm,
            needs_confirmation=bool(CONFIG.REQUIRE_CONFIRM_FOR_POWER),
            confirmation_kind="power.suspend" if CONFIG.REQUIRE_CONFIRM_FOR_POWER else None,
        )

    # Se chegar aqui, desconhecido
    return ParsedCommand(Intent.UNKNOWN, confidence=0.3, raw_text=raw, normalized_text=norm)
