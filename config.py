"""
EVO - Enhanced Virtual Operator
Configuração central do sistema.

Objetivo:
- Centralizar parâmetros de comportamento (timeouts, modos)
- Centralizar políticas de segurança (confirmações obrigatórias)
- Permitir alterações fáceis sem tocar no resto do código
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvoConfig:
    # Identidade
    APP_NAME: str = "EVO"
    VERSION: str = "0.1.0"

    # Conversa / Estados
    # Tempo (segundos) que o EVO fica em modo conversa após acordar
    CONVERSATION_TIMEOUT_S: int = 20

    # Tempo máximo (segundos) à espera de confirmação para ações críticas
    CONFIRM_TIMEOUT_S: int = 8

    # Áudio
    # Se True, o EVO só entra em conversa após wake word
    WAKE_WORD_REQUIRED: bool = True

    # Se True, o EVO responde por voz por defeito
    VOICE_DEFAULT_ON: bool = True

    # HUD / Texto
    # Se True, texto apenas quando necessário (fallback/erros/listas)
    HUD_TEXT_MINIMAL: bool = True

    # Segurança — ações críticas
    # Ações como hibernar/bloquear/suspender exigem confirmação verbal
    REQUIRE_CONFIRM_FOR_POWER: bool = True

    # Interpretação do comando “desligar”
    # "hibernate" = tratar “desligar” como hibernar
    # "ask"       = perguntar (hibernar vs encerrar)
    # "refuse"    = recusar e pedir comando explícito
    POWER_OFF_POLICY: str = "hibernate"


CONFIG = EvoConfig()
