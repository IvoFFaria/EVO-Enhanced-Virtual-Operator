from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple


@dataclass
class SkillContext:
    """
    Contexto que o runtime (ou Brain) pode fornecer às skills.
    Mantemos isto mínimo e extensível.
    """
    # Podes adicionar depois: memory, logger, config, system_actions, etc.
    meta: Dict[str, Any] = None

    def __post_init__(self):
        if self.meta is None:
            self.meta = {}


@dataclass
class SkillResult:
    """
    Resultado uniforme para o Brain/app consumirem.
    """
    handled: bool = False
    speak_text: str = ""
    hud_text: str = ""
    action: Optional[str] = None
    action_args: Optional[Dict[str, Any]] = None
    needs_confirm: bool = False

    # Caso a skill queira pedir confirmação com payload interno
    pending_intent: Optional[str] = None
    pending_args: Optional[Dict[str, Any]] = None


class Skill(Protocol):
    """
    Contrato de Skill:
    - name: identificador
    - match(): diz se a skill pode tratar o input normalizado
    - handle(): devolve SkillResult
    """
    name: str

    def match(self, text: str) -> bool: ...
    def handle(self, text: str, ctx: SkillContext) -> SkillResult: ...


class SkillRegistry:
    """
    Registry simples e previsível (ordem importa).
    - Skills registadas por ordem: a primeira que fizer match, trata.
    """
    def __init__(self) -> None:
        self._skills: List[Skill] = []

    def register(self, skill: Skill) -> None:
        self._skills.append(skill)

    def list(self) -> List[str]:
        return [getattr(s, "name", s.__class__.__name__) for s in self._skills]

    def resolve(self, text: str, ctx: Optional[SkillContext] = None) -> SkillResult:
        if ctx is None:
            ctx = SkillContext()

        for s in self._skills:
            try:
                if s.match(text):
                    res = s.handle(text, ctx)
                    # segurança: se a skill diz que tratou, devolve
                    if res and res.handled:
                        return res
            except Exception as e:
                # Em produto real: logar erro. Aqui: falhar fechado e continuar.
                continue

        return SkillResult(handled=False)


# -----------------------------
# Helpers opcionais
# -----------------------------

def simple_phrase_matcher(*phrases: str) -> Tuple[str, ...]:
    """
    Helper para skills baseadas em frases fixas.
    """
    return tuple(p.strip().lower() for p in phrases if p and p.strip())
