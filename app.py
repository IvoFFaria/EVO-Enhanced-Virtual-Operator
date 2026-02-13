import logging
import threading
import queue
from typing import Optional, List

import numpy as np
from PySide6 import QtCore, QtWidgets

from .config import CONFIG
from .logging_setup import setup_logging
from .state_machine import StateMachine, EvoMode
from .hud.overlay import EvoOverlay

from .commands import parse_command
from .action_router import ActionRouter
from . import system_actions

from .audio_engine import AudioEngine, AudioConfig
from .wakeword import WakeWordConfig

from .tts_engine import TTSEngine, TTSConfig
from .stt_engine import create_stt_engine, STTConfig, BaseSTTEngine

from .agent.brain import EvoBrain, BrainDecision

log = logging.getLogger("EVO")


class ConsoleInputThread(threading.Thread):
    def __init__(self, out_queue: "queue.Queue[str]"):
        super().__init__(daemon=True)
        self.out_queue = out_queue

    def run(self):
        while True:
            try:
                line = input()
                self.out_queue.put(line)
            except EOFError:
                break
            except Exception:
                break


def _execute_system_action(action_kind: str) -> tuple[bool, str]:
    """
    Executor simples para as ações canónicas do Brain.
    Mantém tudo local e previsível.
    """
    try:
        if action_kind == "power.hibernate":
            if not system_actions.can_hibernate():
                if not system_actions.enable_hibernate():
                    return False, "Não consigo ativar a hibernação neste sistema."
            system_actions.hibernate()
            return True, "A hibernar."

        if action_kind == "power.lock":
            system_actions.lock_session()
            return True, "Sessão bloqueada."

        if action_kind == "power.sleep":
            # no teu projeto já existe suspend(); se o nome diferir, ajustamos depois
            system_actions.suspend()
            return True, "A suspender o PC."

        return False, "Ação desconhecida."
    except Exception as e:
        log.exception("Erro ao executar ação %s: %s", action_kind, e)
        return False, "Ocorreu um erro ao executar a ação."


class EvoApp(QtCore.QObject):
    def __init__(self, overlay: EvoOverlay, sm: StateMachine):
        super().__init__()
        self.overlay = overlay
        self.sm = sm
        self.router = ActionRouter(sm)
        self.brain = EvoBrain()

        # ---- TTS ----
        self.tts = TTSEngine(
            TTSConfig(
                enabled=CONFIG.VOICE_DEFAULT_ON,
                rate=0,
                volume=100,
                voice_name="Microsoft Zira Desktop",
                voice_culture_hint="pt-PT",
            )
        )

        # ---- STT (offline) ----
        stt_cfg = STTConfig(language="pt", model="small", device="cpu", compute_type="int8")
        self.stt: BaseSTTEngine = create_stt_engine(stt_cfg)

        # ---- Consola ----
        self.input_queue: "queue.Queue[str]" = queue.Queue()
        self.input_thread = ConsoleInputThread(self.input_queue)
        self.input_thread.start()

        # ---- Overlay input ----
        try:
            self.overlay.command_submitted.connect(self.on_overlay_command)
        except Exception as e:
            log.warning("Não foi possível ligar o command_submitted do overlay: %s", e)

        # ---- Áudio (wake word + VAD) ----
        self.audio_cfg = AudioConfig(
            sample_rate=16000,
            block_size=512,
            channels=1,
            vad_threshold=0.012,
            vad_hangover_ms=450,
        )

        wake_cfg = WakeWordConfig(
            keyword="EVO",
            sensitivity=0.6,
            sample_rate=self.audio_cfg.sample_rate,
        )

        self.audio_engine = AudioEngine(
            cfg=self.audio_cfg,
            wake_cfg=wake_cfg,
            on_wake=self.on_wake,
            on_voice_start=self.on_voice_start,
            on_voice_end=self.on_voice_end,
            on_audio_chunk=self.on_audio_chunk,
        )
        self.audio_engine.start()

        # ---- Buffer áudio pós-wake ----
        self._listening_for_command = False
        self._audio_chunks: List[np.ndarray] = []

        # ---- Timer Qt ----
        self.timer = QtCore.QTimer()
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start()

        self.overlay.set_status(f"{CONFIG.APP_NAME}: Standby")
        log.info("EVO iniciado (Brain + router + overlay + consola + STT/TTS).")

        print(
            "\n[EVO] Ativo.\n"
            "- Voz: diz 'EVO' -> 'Sim?' -> comando.\n"
            "- Texto (overlay ou consola):\n"
            "  evo\n"
            "  evo dormir\n"
            "  evo bloquear\n"
            "  evo hibernar (pede confirmação)\n"
            "  confirmo / cancela\n"
            "  evo fecha evo\n"
        )
        self.say("EVO iniciado. Estou em standby.")

        app = QtWidgets.QApplication.instance()
        app.aboutToQuit.connect(self.on_quit)

    # ---------------- Util ----------------

    def say(self, text: str) -> None:
        if text:
            print(f"[EVO] {text}")
            self.tts.speak(text)
            self.overlay.set_last_message(text)


    # ---------------- Overlay ----------------

    @QtCore.Slot(str)
    def on_overlay_command(self, text: str) -> None:
        t = (text or "").strip()
        if not t:
            return
        print(f"[OVERLAY] {t}")
        self._handle_text_input(t)

    # ---------------- Áudio/STT ----------------

    def _reset_audio_buffer(self):
        self._audio_chunks.clear()

    def _append_audio(self, samples: np.ndarray):
        if self._listening_for_command:
            self._audio_chunks.append(samples)

    def _transcribe_buffer(self) -> str:
        if not self._audio_chunks:
            return ""
        audio = np.concatenate(self._audio_chunks).astype(np.float32, copy=False)
        self._reset_audio_buffer()
        return (self.stt.transcribe_float32(audio, self.audio_cfg.sample_rate) or "").strip()

    def on_wake(self):
        if self.sm.mode == EvoMode.SLEEP:
            log.info("WAKE ignorado (modo dormir).")
            return

        self.sm.enter_conversation()
        self.overlay.set_status(f"{CONFIG.APP_NAME}: Conversa ativa")
        self._listening_for_command = True
        self._reset_audio_buffer()

        log.info("WAKE detetado -> CONVERSATION (a ouvir comando)")
        self.say("Sim?")

    def on_voice_start(self):
        if self.sm.mode == EvoMode.CONVERSATION and self._listening_for_command:
            self.sm.refresh_conversation()

    def on_voice_end(self):
        if self.sm.mode != EvoMode.CONVERSATION:
            return
        if not self._listening_for_command:
            return

        text = self._transcribe_buffer()
        if not text:
            self.say("Não apanhei. Repete.")
            return

        print(f"[STT] {text}")
        self._handle_brain_or_fallback(text, source="stt")

        # por defeito, sai do modo conversa após 1 comando
        self._listening_for_command = False
        self.sm.enter_standby()

    def on_audio_chunk(self, samples):
        self._append_audio(samples)

    # ---------------- Tick / consola ----------------

    def on_tick(self):
        self.sm.tick()

        if self.sm.mode == EvoMode.STANDBY:
            self.overlay.set_status(f"{CONFIG.APP_NAME}: Standby")
        elif self.sm.mode == EvoMode.CONVERSATION:
            self.overlay.set_status(f"{CONFIG.APP_NAME}: Conversa ativa")
        elif self.sm.mode == EvoMode.SLEEP:
            self.overlay.set_status(f"{CONFIG.APP_NAME}: Dormir")
        elif self.sm.mode == EvoMode.EXIT:
            self.overlay.set_status(f"{CONFIG.APP_NAME}: A encerrar")
            QtWidgets.QApplication.quit()
            return

        self._drain_input_queue()

    def _drain_input_queue(self):
        while True:
            try:
                line = self.input_queue.get_nowait()
            except queue.Empty:
                break

            line = (line or "").strip()
            if not line:
                continue
            self._handle_text_input(line)

    # ---------------- Entrada por TEXTO ----------------

    def _handle_text_input(self, line: str):
        raw = (line or "").strip()
        lower = raw.lower()

        # Regra de “wake” por texto para segurança e previsibilidade
        # (exceto quando há pending confirmation no Brain)
        if self.brain.pending is None and self.sm.mode in (EvoMode.STANDBY, EvoMode.SLEEP):
            if lower != "evo" and not lower.startswith("evo "):
                print("[EVO] (ignorado) Diz 'evo' antes do comando.")
                return

        # Prefixo evo -> entra em conversa e aceita comando
        if lower == "evo":
            if self.sm.mode != EvoMode.SLEEP:
                self.sm.enter_conversation()
                self.overlay.set_status(f"{CONFIG.APP_NAME}: Conversa ativa")
            self.say("Sim?")
            return

        if lower.startswith("evo "):
            if self.sm.mode != EvoMode.SLEEP:
                self.sm.enter_conversation()
                self.overlay.set_status(f"{CONFIG.APP_NAME}: Conversa ativa")
            cmd_text = raw[3:].strip()
            self._handle_brain_or_fallback(cmd_text, source="text")
            return

        # confirmação/cancelamento sem prefixo (quando existe pendente)
        self._handle_brain_or_fallback(raw, source="text")

    # ---------------- Brain + Fallback ----------------

    def _handle_brain_or_fallback(self, text: str, source: str):
        # 1) Brain primeiro
        decision: BrainDecision = self.brain.decide(text)

        if decision.hud_text:
            self.overlay.set_status(decision.hud_text)

        if decision.speak_text:
            self.say(decision.speak_text)

        if decision.action:
            self._execute_brain_action(decision)
            return

        # 2) Se o Brain não sabe e não há pendente, faz fallback para o pipeline atual
        # (mantém compatibilidade com o teu parse_command/router)
        if self.brain.pending is None and decision.hud_text == "Desconhecido":
            self._handle_command_text_fallback(text)

    def _execute_brain_action(self, decision: BrainDecision):
        action = decision.action or ""

        if action == "app.exit":
            # encerra o EVO
            self.sm.request_exit()
            return

        ok, msg = _execute_system_action(action)
        if msg:
            self.say(msg)

        # se a ação for executada, volta a standby
        if ok:
            self.sm.enter_standby()

    def _handle_command_text_fallback(self, text: str):
        parsed = parse_command(text)
        log.info("FALLBACK CMD: text='%s' -> intent=%s conf=%.2f", text, parsed.intent.name, parsed.confidence)

        result = self.router.route(parsed)

        if result.hud_text:
            self.overlay.set_status(result.hud_text)

        if result.speak_text:
            self.say(result.speak_text)

        if result.pending_action:
            ok, msg = _execute_system_action(result.pending_action)
            if msg:
                self.say(msg)
            if ok:
                self.sm.enter_standby()

        if result.should_exit:
            self.sm.request_exit()

    # ---------------- Quit ----------------

    def on_quit(self):
        try:
            self.audio_engine.stop()
        except Exception:
            pass

        try:
            self.tts.stop()
        except Exception:
            pass

        log.info("EVO: áudio/TTS parados e aplicação a sair.")


def main():
    setup_logging(CONFIG.APP_NAME)
    app = QtWidgets.QApplication([])

    overlay = EvoOverlay(CONFIG.APP_NAME)
    sm = StateMachine(CONFIG.CONVERSATION_TIMEOUT_S)

    _ = EvoApp(overlay, sm)
    app.exec()


if __name__ == "__main__":
    main()
