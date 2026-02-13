"""
EVO - Enhanced Virtual Operator
Máquina de Estados (State Machine)

Responsabilidade:
- Controlar o modo atual do EVO
- Fazer transições seguras entre modos
- Gerir timeout de conversa
"""

from enum import Enum, auto
import time


class EvoMode(Enum):
    STANDBY = auto()
    CONVERSATION = auto()
    SLEEP = auto()
    EXIT = auto()


class StateMachine:
    def __init__(self, conversation_timeout_s: int):
        self.mode: EvoMode = EvoMode.STANDBY
        self._timeout_s: int = int(conversation_timeout_s)
        self._conversation_deadline: float = 0.0

    # ---- Transições principais ----

    def enter_standby(self) -> None:
        self.mode = EvoMode.STANDBY
        self._conversation_deadline = 0.0

    def enter_conversation(self) -> None:
        self.mode = EvoMode.CONVERSATION
        self._conversation_deadline = time.time() + self._timeout_s

    def refresh_conversation(self) -> None:
        """Renova o tempo de conversa enquanto o utilizador está a falar."""
        if self.mode == EvoMode.CONVERSATION:
            self._conversation_deadline = time.time() + self._timeout_s

    def enter_sleep(self) -> None:
        self.mode = EvoMode.SLEEP
        self._conversation_deadline = 0.0

    def request_exit(self) -> None:
        self.mode = EvoMode.EXIT
        self._conversation_deadline = 0.0

    # ---- Ciclo ----

    def tick(self) -> None:
        """
        Deve ser chamado regularmente.
        Responsabilidade: voltar a STANDBY quando a conversa expira.
        """
        if self.mode == EvoMode.CONVERSATION:
            if time.time() > self._conversation_deadline:
                self.enter_standby()

    # ---- Utilitários ----

    def is_conversation_active(self) -> bool:
        return self.mode == EvoMode.CONVERSATION
