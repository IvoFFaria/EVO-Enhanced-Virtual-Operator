"""
EVO - Enhanced Virtual Operator
Memory Store (offline, local)

Objetivo:
- Persistir memória em JSON (auditável, simples, tradicional)
- Ser seguro contra corrupção: escrita atómica
- Ser thread-safe dentro do processo (lock)
- Não depende de serviços externos

Estrutura (v1):
{
  "schema_version": 1,
  "created_at": "...",
  "updated_at": "...",
  "facts": { "chave": {"value": "...", "updated_at": "..."} },
  "notes": [ {"text": "...", "ts": "..."} ]
}
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, List


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass
class MemoryItem:
    value: Any
    updated_at: str


class MemoryStore:
    """
    Store de memória persistente em JSON.

    - Thread-safe (lock)
    - Escrita atómica: escreve para .tmp e faz replace
    - Tolerante a ficheiro inexistente/corrompido (faz bootstrap)
    """

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        self._load_or_init()

    # ---------------- Public API ----------------

    def get_fact(self, key: str) -> Optional[MemoryItem]:
        k = (key or "").strip().lower()
        if not k:
            return None
        with self._lock:
            facts = self._data.get("facts", {})
            item = facts.get(k)
            if not item:
                return None
            return MemoryItem(value=item.get("value"), updated_at=item.get("updated_at", ""))

    def set_fact(self, key: str, value: Any) -> None:
        k = (key or "").strip().lower()
        if not k:
            return
        with self._lock:
            self._ensure_shape()
            self._data["facts"][k] = {"value": value, "updated_at": _now_iso()}
            self._touch()
            self._save_locked()

    def delete_fact(self, key: str) -> bool:
        k = (key or "").strip().lower()
        if not k:
            return False
        with self._lock:
            self._ensure_shape()
            facts = self._data["facts"]
            if k in facts:
                del facts[k]
                self._touch()
                self._save_locked()
                return True
            return False

    def list_fact_keys(self) -> List[str]:
        with self._lock:
            facts = self._data.get("facts", {})
            return sorted(list(facts.keys()))

    def add_note(self, text: str) -> None:
        t = (text or "").strip()
        if not t:
            return
        with self._lock:
            self._ensure_shape()
            self._data["notes"].append({"text": t, "ts": _now_iso()})
            self._touch()
            self._save_locked()

    def get_notes(self, limit: int = 10) -> List[Dict[str, str]]:
        with self._lock:
            notes = self._data.get("notes", [])
            if limit <= 0:
                return []
            return list(notes[-limit:])

    def snapshot(self) -> Dict[str, Any]:
        """Cópia do estado atual (para debug/telemetria local)."""
        with self._lock:
            return json.loads(json.dumps(self._data))

    # ---------------- Internals ----------------

    def _load_or_init(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

        if not os.path.exists(self.path):
            self._data = self._bootstrap()
            self._save_atomic(self._data)
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            self._ensure_shape()
        except Exception:
            # ficheiro corrompido: renomeia e recria
            try:
                bad = self.path + ".corrupted"
                os.replace(self.path, bad)
            except Exception:
                pass
            self._data = self._bootstrap()
            self._save_atomic(self._data)

    def _bootstrap(self) -> Dict[str, Any]:
        now = _now_iso()
        return {
            "schema_version": 1,
            "created_at": now,
            "updated_at": now,
            "facts": {},
            "notes": [],
        }

    def _ensure_shape(self) -> None:
        if not isinstance(self._data, dict):
            self._data = self._bootstrap()
            return

        self._data.setdefault("schema_version", 1)
        self._data.setdefault("created_at", _now_iso())
        self._data.setdefault("updated_at", _now_iso())

        if "facts" not in self._data or not isinstance(self._data["facts"], dict):
            self._data["facts"] = {}

        if "notes" not in self._data or not isinstance(self._data["notes"], list):
            self._data["notes"] = []

    def _touch(self) -> None:
        self._data["updated_at"] = _now_iso()

    def _save_locked(self) -> None:
        # assume lock já adquirido
        self._save_atomic(self._data)

    def _save_atomic(self, data: Dict[str, Any]) -> None:
        tmp = self.path + ".tmp"
        payload = json.dumps(data, ensure_ascii=False, indent=2)

        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)

        os.replace(tmp, self.path)
