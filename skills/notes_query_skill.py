from __future__ import annotations

import os
import re
from typing import List, Dict, Optional, Tuple

from .registry import SkillContext, SkillResult, simple_phrase_matcher
from ..memory_store import MemoryStore


class NotesQuerySkill:
    """
    Skill: consulta e resumo sobre o que foi guardado em MemoryStore.notes.

    Comandos:
      - "resumo do ultimo" / "resume o ultimo"
      - "procura <termo>" / "pesquisa <termo>"
      - "o que diz sobre <tema>"

    Estratégia (offline, tradicional):
      - Recuperação: procura literal (case-insensitive) nos notes
      - Resumo: heurístico (primeiras frases + linhas com hits)
    """

    name = "notes_query"

    def __init__(self) -> None:
        self._memory = MemoryStore(self._default_memory_path())

        self._summary_phrases: Tuple[str, ...] = simple_phrase_matcher(
            "resumo do ultimo",
            "resumo do último",
            "resume o ultimo",
            "resume o último",
            "resumir o ultimo",
            "resumir o último",
        )

        self._search_prefixes: Tuple[str, ...] = simple_phrase_matcher(
            "procura",
            "pesquisa",
            "buscar",
        )

        # "o que diz sobre X"
        self._about_re = re.compile(r"^o que diz\s+sobre\s+(.+)$", re.IGNORECASE)

    def match(self, text: str) -> bool:
        t = (text or "").strip().lower()
        if t in self._summary_phrases:
            return True
        if any(t.startswith(p + " ") for p in self._search_prefixes):
            return True
        if self._about_re.match(text or ""):
            return True
        return False

    def handle(self, text: str, ctx: SkillContext) -> SkillResult:
        raw = (text or "").strip()
        t = raw.lower().strip()

        notes = self._memory.get_notes(limit=50)  # últimos 50
        if not notes:
            return SkillResult(
                handled=True,
                speak_text="Ainda não tenho notas guardadas. Primeiro usa: 'ler ficheiro C:\\\\...\\\\algo.txt'.",
                hud_text="Notas: vazio",
            )

        # 1) Resumo do último
        if t in self._summary_phrases:
            last = notes[-1]["text"]
            summary = self._summarize_text(last)
            return SkillResult(
                handled=True,
                speak_text=f"Resumo do último: {summary}",
                hud_text="Resumo do último",
            )

        # 2) Procura / pesquisa
        term = self._extract_search_term(raw)
        if term:
            hits = self._search_notes(notes, term, max_hits=3)
            if not hits:
                return SkillResult(
                    handled=True,
                    speak_text=f"Não encontrei '{term}' nas notas recentes.",
                    hud_text=f"Procura sem resultados: {term}",
                )

            # construir resposta: pequenos excertos
            speak = self._format_hits(term, hits)
            return SkillResult(
                handled=True,
                speak_text=speak,
                hud_text=f"Procura: {term} ({len(hits)} resultado(s))",
            )

        # 3) O que diz sobre <tema>
        m = self._about_re.match(raw)
        if m:
            topic = (m.group(1) or "").strip()
            if not topic:
                return SkillResult(
                    handled=True,
                    speak_text="Diz: 'o que diz sobre <tema>'.",
                    hud_text="Notas: falta tema",
                )

            hits = self._search_notes(notes, topic, max_hits=4)
            if not hits:
                return SkillResult(
                    handled=True,
                    speak_text=f"Não encontrei nada sobre '{topic}' nas notas recentes.",
                    hud_text=f"Sem resultados: {topic}",
                )

            combined = "\n".join(h["excerpt"] for h in hits)
            summary = self._summarize_text(combined)
            return SkillResult(
                handled=True,
                speak_text=f"Sobre '{topic}': {summary}",
                hud_text=f"Tema: {topic}",
            )

        # fallback seguro
        return SkillResult(
            handled=True,
            speak_text="Comando reconhecido, mas não consegui processar. Tenta: 'resumo do ultimo' ou 'procura X'.",
            hud_text="Notas: erro",
        )

    # -----------------------------
    # Internals
    # -----------------------------

    @staticmethod
    def _default_memory_path() -> str:
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or os.getcwd()
        return os.path.join(base, "EVO", "memory.json")

    def _extract_search_term(self, raw: str) -> Optional[str]:
        s = raw.strip()
        low = s.lower()
        for p in self._search_prefixes:
            if low.startswith(p + " "):
                return s[len(p):].strip()
        return None

    @staticmethod
    def _search_notes(notes: List[Dict[str, str]], term: str, max_hits: int = 3) -> List[Dict[str, str]]:
        term = (term or "").strip()
        if not term:
            return []

        out: List[Dict[str, str]] = []
        term_low = term.lower()

        # procurar do mais recente para o mais antigo
        for n in reversed(notes):
            text = n.get("text", "")
            if term_low in text.lower():
                excerpt = NotesQuerySkill._excerpt_around(text, term, radius=220)
                out.append({"ts": n.get("ts", ""), "excerpt": excerpt})
                if len(out) >= max_hits:
                    break

        return out

    @staticmethod
    def _excerpt_around(text: str, term: str, radius: int = 200) -> str:
        if not text:
            return ""

        low = text.lower()
        idx = low.find(term.lower())
        if idx < 0:
            return NotesQuerySkill._clean_preview(text, radius)

        start = max(0, idx - radius)
        end = min(len(text), idx + len(term) + radius)
        chunk = text[start:end]
        chunk = chunk.replace("\r", " ")
        chunk = chunk.strip()

        # limpar whitespace
        chunk = " ".join(chunk.split())
        if start > 0:
            chunk = "…" + chunk
        if end < len(text):
            chunk = chunk + "…"
        return chunk

    @staticmethod
    def _summarize_text(text: str) -> str:
        """
        Resumo heurístico:
        - remove header [FILE]
        - escolhe 2-3 frases iniciais e 1-2 linhas com densidade de palavras
        """
        if not text:
            return "vazio."

        # remover cabeçalho file se existir
        lines = [ln for ln in (text or "").splitlines() if ln.strip()]
        if lines and lines[0].startswith("[FILE]"):
            lines = lines[1:]

        clean = " ".join(" ".join(lines).split())
        if not clean:
            return "vazio."

        # dividir em frases simples
        sentences = re.split(r"(?<=[\.\!\?])\s+", clean)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return NotesQuerySkill._clean_preview(clean, 420)

        # pegar primeiras 2 frases (tradicional e confiável)
        head = sentences[:2]

        # se for muito curto, devolver logo
        out = " ".join(head)
        if len(out) < 220 and len(sentences) >= 3:
            out = out + " " + sentences[2]

        # limitar tamanho para TTS/HUD
        return NotesQuerySkill._clean_preview(out, 520)

    @staticmethod
    def _clean_preview(text: str, n: int) -> str:
        t = (text or "").replace("\r", " ")
        t = " ".join(t.split())
        if not t:
            return "vazio."
        if len(t) <= n:
            return t
        return t[:n].rstrip() + "…"

    @staticmethod
    def _format_hits(term: str, hits: List[Dict[str, str]]) -> str:
        parts = [f"Encontrei '{term}' em {len(hits)} nota(s)."]
        for i, h in enumerate(hits, start=1):
            parts.append(f"Resultado {i}: {NotesQuerySkill._clean_preview(h.get('excerpt', ''), 360)}")
        return " ".join(parts)
