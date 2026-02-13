from __future__ import annotations

import os
import re
from typing import Tuple, Optional

from .registry import SkillContext, SkillResult, simple_phrase_matcher
from ..memory_store import MemoryStore


class ReadFileSkill:
    """
    Skill: leitura de ficheiros locais (offline) + armazenamento em memória (notes).

    Comandos suportados:
      - "ler ficheiro <caminho>"
      - "le ficheiro <caminho>"
      - "abre <caminho>"
      - "abrir <caminho>"

    Regras:
      - só lê extensões seguras: .txt .md .json .log .csv
      - limite de tamanho (para não bloquear UI): 200 KB por defeito
      - guarda o conteúdo como NOTE na memória local (auditável)
    """

    name = "read_file"

    _allowed_ext = {".txt", ".md", ".json", ".log", ".csv"}
    _max_bytes = 200_000  # 200 KB: suficiente para já, sem arriscar bloqueios

    def __init__(self) -> None:
        self._verbs: Tuple[str, ...] = simple_phrase_matcher(
            "ler ficheiro",
            "le ficheiro",
            "lê ficheiro",
            "abre",
            "abrir",
        )

        self._memory = MemoryStore(self._default_memory_path())

    def match(self, text: str) -> bool:
        t = (text or "").strip().lower()
        return any(t.startswith(v) for v in self._verbs)

    def handle(self, text: str, ctx: SkillContext) -> SkillResult:
        raw = (text or "").strip()
        path = self._extract_path(raw)

        if not path:
            return SkillResult(
                handled=True,
                speak_text="Indica o caminho. Exemplo: 'ler ficheiro C:\\\\Users\\\\Ivo\\\\Desktop\\\\nota.txt'",
                hud_text="Leitura: falta caminho",
            )

        # Expandir ~ e env vars (Windows-friendly)
        path = os.path.expandvars(path)
        path = os.path.expanduser(path)

        # Se vier entre aspas, já limpamos na extração. Aqui normalizamos.
        path = path.strip()

        if not os.path.isabs(path):
            # permitir relativo ao cwd (tradicional)
            path = os.path.abspath(path)

        if not os.path.exists(path):
            return SkillResult(
                handled=True,
                speak_text="Esse ficheiro não existe.",
                hud_text=f"Leitura: não existe",
            )

        if os.path.isdir(path):
            return SkillResult(
                handled=True,
                speak_text="Isso é uma pasta. Para já só leio ficheiros.",
                hud_text="Leitura: é pasta",
            )

        ext = os.path.splitext(path)[1].lower()
        if ext not in self._allowed_ext:
            return SkillResult(
                handled=True,
                speak_text=f"Para já só leio: {', '.join(sorted(self._allowed_ext))}.",
                hud_text=f"Leitura: extensão não suportada ({ext})",
            )

        try:
            size = os.path.getsize(path)
        except Exception:
            size = None

        if size is not None and size > self._max_bytes:
            return SkillResult(
                handled=True,
                speak_text="O ficheiro é grande demais para ler de uma vez. Divide-o ou diz-me o excerto.",
                hud_text=f"Leitura: demasiado grande ({size} bytes)",
            )

        try:
            content = self._read_text_file(path)
        except UnicodeDecodeError:
            return SkillResult(
                handled=True,
                speak_text="Não consegui ler o ficheiro por causa da codificação. Guarda em UTF-8 e tenta novamente.",
                hud_text="Leitura: erro de codificação",
            )
        except Exception:
            return SkillResult(
                handled=True,
                speak_text="Falhei a ler o ficheiro. Verifica permissões e tenta novamente.",
                hud_text="Leitura: erro ao ler",
            )

        # Guardar em notes (conhecimento bruto)
        # Mantemos auditável: cabeçalho + conteúdo
        header = f"[FILE] {path}"
        note_payload = header + "\n" + content
        self._memory.add_note(note_payload)

        # Resposta curta e útil
        lines = content.count("\n") + (1 if content else 0)
        chars = len(content)
        preview = self._preview(content, 420)

        speak = (
            f"Li o ficheiro. {lines} linhas, {chars} caracteres. "
            f"Guardei em memória. Pré-visualização: {preview}"
        )

        return SkillResult(
            handled=True,
            speak_text=speak,
            hud_text=f"Lido e guardado: {os.path.basename(path)}",
        )

    # -----------------------------
    # Internals
    # -----------------------------

    @staticmethod
    def _default_memory_path() -> str:
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or os.getcwd()
        return os.path.join(base, "EVO", "memory.json")

    @staticmethod
    def _extract_path(raw: str) -> Optional[str]:
        """
        Extrai caminho após o verbo.
        Aceita com ou sem aspas.
        Exemplos:
          ler ficheiro "C:\\Users\\Ivo\\Desktop\\a.txt"
          abre C:\\temp\\b.md
        """
        s = raw.strip()

        # Remover o verbo inicial
        lowered = s.lower()
        prefixes = ["ler ficheiro", "le ficheiro", "lê ficheiro", "abre", "abrir"]
        for p in prefixes:
            if lowered.startswith(p):
                s = s[len(p):].strip()
                break

        if not s:
            return None

        # Se vier entre aspas
        m = re.match(r'^[\'"](.+)[\'"]$', s)
        if m:
            return m.group(1).strip()

        return s.strip()

    @staticmethod
    def _read_text_file(path: str) -> str:
        # tenta UTF-8 primeiro; fallback latin-1 (muito comum em Windows)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as f:
                return f.read()

    @staticmethod
    def _preview(text: str, n: int) -> str:
        t = (text or "").strip().replace("\r", " ")
        t = " ".join(t.split())
        if not t:
            return "vazio."
        if len(t) <= n:
            return t
        return t[:n].rstrip() + "…"
