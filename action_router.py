"""
EVO - Enhanced Virtual Operator
Action Router (MVP)

Responsabilidade:
- Receber ParsedCommand (intenção)
- Decidir transições de estado (StateMachine)
- Gerir ações críticas com confirmação (pending action)
- Devolver mensagens para HUD e para voz (TTS no futuro)

Nota:
- Este módulo NÃO executa comandos do Windows.
- Apenas decide e prepara o que deve acontecer.
"""

from dataclasses import dataclass
from typing import Optional

from .config import CONFIG
from .state_machine import StateMachine
from .commands import ParsedCommand, Intent


@dataclass
class RouteResult:
    """
    Resultado da decisão para a camada superior (app).
    """
    hud_text: str
    speak_text: str
    pending_action: Optional[str] = None   # ex: "power.hibernate"
    should_exit: bool = False


class ActionRouter:
    def __init__(self, sm: StateMachine):
        self.sm = sm
        self._pending_action: Optional[str] = None

    @property
    def pending_action(self) -> Optional[str]:
        return self._pending_action

    def clear_pending(self) -> None:
        self._pending_action = None

    def route(self, cmd: ParsedCommand) -> RouteResult:
        """
        Decide o que fazer com base na intenção.
        """
        # 1) Se existe uma ação pendente, a prioridade é CONFIRM/CANCEL
        if self._pending_action:
            if cmd.intent == Intent.CONFIRM:
                action = self._pending_action
                self.clear_pending()
                # Aqui ainda não executamos - apenas sinalizamos ao sistema superior
                return RouteResult(
                    hud_text=f"{CONFIG.APP_NAME}: Confirmado",
                    speak_text="Confirmado.",
                    pending_action=action,  # devolve para execução posterior (noutro módulo)
                )

            if cmd.intent == Intent.CANCEL:
                self.clear_pending()
                return RouteResult(
                    hud_text=f"{CONFIG.APP_NAME}: Cancelado",
                    speak_text="Cancelado.",
                )

            # Se o utilizador disse outra coisa enquanto há pendente
            return RouteResult(
                hud_text=f"{CONFIG.APP_NAME}: A aguardar confirmação",
                speak_text="Estou à espera da tua confirmação. Diz: confirmo, ou cancela.",
            )

        # 2) Sem pendente: processar intenção normal
        if cmd.intent == Intent.UNKNOWN:
            return RouteResult(
                hud_text=f"{CONFIG.APP_NAME}: Não percebi",
                speak_text="Não percebi. Repete de forma mais direta.",
            )

        if cmd.intent == Intent.REPEAT:
            # No futuro, isto repete a última resposta TTS
            return RouteResult(
                hud_text=f"{CONFIG.APP_NAME}: Repetir",
                speak_text="Ok. No modo atual, ainda não tenho histórico de repetição.",
            )

        if cmd.intent == Intent.SLEEP:
            self.sm.enter_sleep()
            return RouteResult(
                hud_text=f"{CONFIG.APP_NAME}: Dormir",
                speak_text="A entrar em modo dormir.",
            )

        if cmd.intent == Intent.EXIT:
            self.sm.request_exit()
            return RouteResult(
                hud_text=f"{CONFIG.APP_NAME}: A encerrar",
                speak_text="A encerrar.",
                should_exit=True,
            )

        # 3) Ações críticas: preparar confirmação
        if cmd.intent in (Intent.HIBERNATE, Intent.LOCK, Intent.SUSPEND):
            if cmd.needs_confirmation and cmd.confirmation_kind:
                self._pending_action = cmd.confirmation_kind
                # Mensagem humana, simples
                if cmd.confirmation_kind == "power.hibernate":
                    question = "Queres que eu hiberne o PC agora? Diz: confirmo, ou cancela."
                    hud = f"{CONFIG.APP_NAME}: Confirmar hibernação"
                elif cmd.confirmation_kind == "power.lock":
                    question = "Queres bloquear a sessão agora? Diz: confirmo, ou cancela."
                    hud = f"{CONFIG.APP_NAME}: Confirmar bloqueio"
                elif cmd.confirmation_kind == "power.suspend":
                    question = "Queres suspender o PC agora? Diz: confirmo, ou cancela."
                    hud = f"{CONFIG.APP_NAME}: Confirmar suspensão"
                elif cmd.confirmation_kind == "power.ask":
                    question = "Queres hibernar ou encerrar? Para segurança, diz: hibernar, ou cancela."
                    hud = f"{CONFIG.APP_NAME}: Clarificar energia"
                else:
                    question = "Confirma a ação. Diz: confirmo, ou cancela."
                    hud = f"{CONFIG.APP_NAME}: Confirmar"

                return RouteResult(hud_text=hud, speak_text=question)

            # Se não exigir confirmação (não recomendado), devolver para execução
            kind = {
                Intent.HIBERNATE: "power.hibernate",
                Intent.LOCK: "power.lock",
                Intent.SUSPEND: "power.suspend",
            }[cmd.intent]

            return RouteResult(
                hud_text=f"{CONFIG.APP_NAME}: Ação pronta",
                speak_text="Ok.",
                pending_action=kind,
            )

        # 4) Caso especial: “acordar” (wake) pode simplesmente entrar em conversa
        if cmd.intent == Intent.WAKE:
            self.sm.enter_conversation()
            return RouteResult(
                hud_text=f"{CONFIG.APP_NAME}: Conversa ativa",
                speak_text="Sim?",
            )

        # fallback seguro
        return RouteResult(
            hud_text=f"{CONFIG.APP_NAME}: Não suportado",
            speak_text="Esse comando ainda não está disponível.",
        )
