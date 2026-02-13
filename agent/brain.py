from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any
import time
import os
import re

from ..memory_store import MemoryStore

from ..skills.registry import SkillRegistry, SkillContext
from ..skills.help_skill import HelpSkill
from ..skills.read_file_skill import ReadFileSkill


# -----------------------------
# Tipos / contratos
# -----------------------------

@dataclass
class BrainDecision:
    """
    Resultado do cérebro: o app.py só precisa ler isto e executar.
    """
    speak_text: str = ""
    hud_text: str = ""
    action: Optional[str] = None          # ex: "app.exit", "power.sleep"
    action_args: Optional[Dict[str, Any]] = None
    needs_confirm: bool = False           # pede confirmação explícita
    should_exit: bool = False             # se o próprio cérebro decide encerrar a app


@dataclass
class PendingAction:
    action: str
    action_args: Dict[str, Any]
    created_at: float
    ttl_s: float = 20.0                   # validade do pedido de confirmação (segundos)

    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) > self.ttl_s


# -----------------------------
# Cérebro
# -----------------------------

class EvoBrain:
    """
    Cérebro do EVO (v1.3):
    - Determinístico, previsível, robusto.
    - Skills Registry para crescer sem virar monólito.
    - Memória offline persistente (JSON) para factos simples + notes.
    """

    def __init__(self):
        self.pending: Optional[PendingAction] = None

        # Memória persistente (offline)
        self.memory = MemoryStore(self._default_memory_path())

        # Skills (ordem importa)
        self.skills = SkillRegistry()
        self.skills.register(HelpSkill())
        self.skills.register(ReadFileSkill())

        # Intents diretos e seguros (sem confirmação)
        self.direct_map = {
            "fecha evo": ("app.exit", {}, "A encerrar."),
            "sair": ("app.exit", {}, "A encerrar."),
            "exit": ("app.exit", {}, "A encerrar."),
            "fecha": ("app.exit", {}, "A encerrar."),  # tolerância
        }

        # Intents de energia / sistema (alguns exigem confirmação)
        self.power_map = {
            "dormir": ("power.sleep", {}, False, "A dormir."),
            "suspender": ("power.sleep", {}, False, "A suspender."),
            "bloquear": ("power.lock", {}, False, "Sessão bloqueada."),
            "hibernar": ("power.hibernate", {}, True, "Confirmas hibernar? Diz 'confirmo' ou 'cancela'."),
        }

        # Frases de confirmação/cancelamento
        self.confirm_words = {"confirmo", "ok", "sim", "confirmar"}
        self.cancel_words = {"cancela", "cancelar", "nao", "não"}

    # -----------------------------
    # API principal
    # -----------------------------

    def decide(self, text: str) -> BrainDecision:
        t = self._norm(text)

        # housekeeping: pending expirado
        if self.pending and self.pending.is_expired():
            self.pending = None
            return BrainDecision(
                speak_text="Confirmação expirou. Repete o pedido.",
                hud_text="Confirmação expirada",
            )

        if not t:
            return BrainDecision(speak_text="Diz um comando.", hud_text="Sem comando")

        # 1) Se há pendente, tratar confirmação/cancelamento
        if self.pending:
            return self._handle_pending(t)

        # 2) Skills primeiro (crescimento limpo)
        skill_res = self.skills.resolve(t, SkillContext(meta={"brain": "EvoBrain"}))
        if skill_res and skill_res.handled:
            return BrainDecision(
                speak_text=skill_res.speak_text or "",
                hud_text=skill_res.hud_text or "",
                action=skill_res.action,
                action_args=skill_res.action_args,
                needs_confirm=bool(skill_res.needs_confirm),
                should_exit=(skill_res.action == "app.exit"),
            )

        # 3) Memória (produto): set/get/delete (delete com confirmação)
        mem_decision = self._try_memory_intents(t)
        if mem_decision:
            return mem_decision

        # 4) Comandos diretos
        if t in self.direct_map:
            action, args, speak = self.direct_map[t]
            return BrainDecision(
                speak_text=speak,
                hud_text=f"Ação: {action}",
                action=action,
                action_args=args,
                needs_confirm=False,
                should_exit=(action == "app.exit"),
            )

        # 5) Energia / sistema
        if t in self.power_map:
            action, args, needs_confirm, speak = self.power_map[t]
            if needs_confirm:
                self.pending = PendingAction(action=action, action_args=args, created_at=time.monotonic())
                return BrainDecision(
                    speak_text=speak,
                    hud_text=f"Pendente: {action}",
                    action=None,
                    needs_confirm=True,
                )
            else:
                return BrainDecision(
                    speak_text=speak,
                    hud_text=f"Ação: {action}",
                    action=action,
                    action_args=args,
                    needs_confirm=False,
                )

        # 6) Fallback controlado
        return BrainDecision(
            speak_text="Ainda não tenho essa capacidade. Podes reformular como um comando direto?",
            hud_text="Desconhecido",
            action=None,
        )

    # -----------------------------
    # Memória (intents)
    # -----------------------------

    def _try_memory_intents(self, t: str) -> Optional[BrainDecision]:
        """
        Comandos suportados (v1):
          - memoriza <chave> como <valor>
          - memoriza <chave>: <valor>
          - o que sabes sobre <chave> / o que sabes de <chave>
          - esquece <chave>   (pede confirmação)
        """

        # SET: "memoriza X como Y"
        m = re.match(r"^memoriza\s+(.+?)\s+como\s+(.+)$", t)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            if not key or not val:
                return BrainDecision(speak_text="Diz: memoriza X como Y.", hud_text="Memória: formato inválido")
            self.memory.set_fact(key, val)
            return BrainDecision(
                speak_text=f"Ok. Memorizei '{key}'.",
                hud_text=f"Memória gravada: {key}",
            )

        # SET alternativa: "memoriza X: Y"
        m = re.match(r"^memoriza\s+(.+?)\s*:\s*(.+)$", t)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            if not key or not val:
                return BrainDecision(speak_text="Diz: memoriza X: Y.", hud_text="Memória: formato inválido")
            self.memory.set_fact(key, val)
            return BrainDecision(
                speak_text=f"Ok. Memorizei '{key}'.",
                hud_text=f"Memória gravada: {key}",
            )

        # GET: "o que sabes sobre X" / "o que sabes de X"
        m = re.match(r"^o que sabes\s+(?:sobre|de)\s+(.+)$", t)
        if m:
            key = m.group(1).strip()
            item = self.memory.get_fact(key)
            if not item:
                return BrainDecision(
                    speak_text=f"Ainda não tenho nada guardado sobre '{key}'.",
                    hud_text=f"Memória vazia: {key}",
                )
            return BrainDecision(
                speak_text=f"Sobre '{key}': {item.value}",
                hud_text=f"Memória: {key}",
            )

        # DELETE: "esquece X" (com confirmação)
        m = re.match(r"^(?:esquece|apaga)\s+(.+)$", t)
        if m:
            key = m.group(1).strip()
            if not key:
                return BrainDecision(speak_text="Diz: esquece X.", hud_text="Memória: formato inválido")

            if not self.memory.get_fact(key):
                return BrainDecision(
                    speak_text=f"Não tenho nada guardado sobre '{key}'.",
                    hud_text=f"Memória inexistente: {key}",
                )

            self.pending = PendingAction(
                action="memory.delete_fact",
                action_args={"key": key},
                created_at=time.monotonic(),
            )
            return BrainDecision(
                speak_text=f"Confirmas apagar a memória de '{key}'? Diz 'confirmo' ou 'cancela'.",
                hud_text=f"Pendente: apagar {key}",
                needs_confirm=True,
            )

        return None

    # -----------------------------
    # Pending confirmation
    # -----------------------------

    def _handle_pending(self, t: str) -> BrainDecision:
        if t in self.confirm_words:
            action = self.pending.action
            args = self.pending.action_args
            self.pending = None

            # Pendentes internos (memória) não passam para o app.py
            if action == "memory.delete_fact":
                key = (args.get("key") or "").strip()
                ok = self.memory.delete_fact(key)
                if ok:
                    return BrainDecision(
                        speak_text=f"Confirmado. Apaguei '{key}'.",
                        hud_text=f"Memória apagada: {key}",
                        action=None,
                        needs_confirm=False,
                    )
                return BrainDecision(
                    speak_text="Confirmado, mas já não encontrei essa memória.",
                    hud_text="Memória já não existia",
                    action=None,
                    needs_confirm=False,
                )

            # Pendentes externos seguem para o app.py
            return BrainDecision(
                speak_text="Confirmado.",
                hud_text=f"Confirmado: {action}",
                action=action,
                action_args=args,
                needs_confirm=False,
            )

        if t in self.cancel_words:
            self.pending = None
            return BrainDecision(
                speak_text="Ok. Cancelado.",
                hud_text="Cancelado",
                action=None,
                needs_confirm=False,
            )

        return BrainDecision(
            speak_text="Preciso de confirmação. Diz 'confirmo' ou 'cancela'.",
            hud_text="A aguardar confirmação",
            action=None,
            needs_confirm=True,
        )

    # -----------------------------
    # Utils
    # -----------------------------

    @staticmethod
    def _default_memory_path() -> str:
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or os.getcwd()
        return os.path.join(base, "EVO", "memory.json")

    @staticmethod
    def _norm(s: str) -> str:
        s = (s or "").strip().lower()
        s = " ".join(s.split())

        replacements = {
            "não": "nao",
            "ç": "c",
            "á": "a",
            "à": "a",
            "ã": "a",
            "â": "a",
            "é": "e",
            "ê": "e",
            "í": "i",
            "ó": "o",
            "ô": "o",
            "õ": "o",
            "ú": "u",
        }
        for a, b in replacements.items():
            s = s.replace(a, b)

        return s
