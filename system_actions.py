"""
EVO - Enhanced Virtual Operator
System Actions (Windows)

Responsabilidade:
- Executar ações reais do sistema operativo (Windows)
- Manter isto isolado para segurança e manutenção
- Nunca decidir "quando" executar: só executa quando chamado

Ações:
- Hibernar
- Bloquear sessão
- Suspender (sleep)
"""

import logging
import subprocess
import platform

log = logging.getLogger("EVO.SystemActions")


def _ensure_windows() -> None:
    if platform.system().lower() != "windows":
        raise RuntimeError("Estas ações de sistema estão implementadas apenas para Windows.")


def can_hibernate() -> bool:
    """
    Verifica se hibernação está disponível.
    Usa 'powercfg /a' para listar estados de energia suportados.
    """
    _ensure_windows()
    try:
        p = subprocess.run(
            ["powercfg", "/a"],
            capture_output=True,
            text=True,
            check=False,
        )
        out = (p.stdout or "") + "\n" + (p.stderr or "")
        # Se aparecer "Hibernação" como disponível, assume True
        # Nota: a saída pode variar por idioma, então fazemos match simples.
        return ("Hiberna" in out) or ("Hibernate" in out)
    except Exception:
        return False


def enable_hibernate() -> bool:
    """
    Tenta ativar a hibernação.
    Pode exigir permissões dependendo do sistema.
    """
    _ensure_windows()
    try:
        p = subprocess.run(
            ["powercfg", "/hibernate", "on"],
            capture_output=True,
            text=True,
            check=False,
        )
        ok = p.returncode == 0
        log.info("Ativar hibernação: %s", "OK" if ok else "FALHOU")
        return ok
    except Exception as e:
        log.exception("Erro ao ativar hibernação: %s", e)
        return False


def hibernate() -> None:
    """
    Hiberna o PC imediatamente.
    """
    _ensure_windows()
    log.info("A executar hibernação (shutdown /h).")
    subprocess.run(["shutdown", "/h"], check=False)


def lock_session() -> None:
    """
    Bloqueia a sessão do Windows.
    """
    _ensure_windows()
    log.info("A bloquear sessão (rundll32 user32.dll,LockWorkStation).")
    subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=False)


def suspend() -> None:
    """
    Suspende (sleep) o sistema.
    Nota: 'rundll32 powrprof.dll,SetSuspendState 0,1,0' pode variar.
    Se a hibernação estiver ativa, alguns sistemas podem hibernar em vez de suspender.
    """
    _ensure_windows()
    log.info("A suspender sistema (SetSuspendState).")
    subprocess.run(
        ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
        check=False
    )
