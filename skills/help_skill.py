from __future__ import annotations

from typing import Tuple

from .registry import SkillContext, SkillResult, simple_phrase_matcher


class HelpSkill:
    """
    Skill: ajuda / comandos / capacidades.

    Mantém o tom "operador" e descreve capacidades reais (sem prometer magia).
    """
    name = "help"

    def __init__(self) -> None:
        self._phrases: Tuple[str, ...] = simple_phrase_matcher(
            "ajuda",
            "help",
            "comandos",
            "o que sabes fazer",
            "o que consegues fazer",
            "capacidades",
        )

    def match(self, text: str) -> bool:
        t = (text or "").strip().lower()
        return t in self._phrases

    def handle(self, text: str, ctx: SkillContext) -> SkillResult:
        lines = [
            "Consigo executar comandos diretos e gerir memória local.",
            "Comandos principais:",
            "• fechar / sair / fecha evo",
            "• dormir / suspender",
            "• bloquear",
            "• hibernar (pede confirmação)",
            "Memória (offline):",
            "• memoriza X como Y",
            "• memoriza X: Y",
            "• o que sabes sobre X",
            "• esquece X (pede confirmação)",
        ]

        return SkillResult(
            handled=True,
            speak_text=" ".join(lines),
            hud_text="Ajuda: comandos disponíveis",
            action=None,
        )
