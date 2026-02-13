# EVO — Enhanced Virtual Operator

EVO (Enhanced Virtual Operator) is a local-first intelligent assistant for Windows, built with a modular and deterministic architecture.

It is inspired by the concept of a personal AI operator, but engineered using traditional software design principles: predictability, separation of concerns, and offline control.

⚠️ This project is under active development.

---

## Vision

EVO is designed to be:

* Fully offline-capable
* Deterministic at its core
* Modular through a Skill Registry system
* Extensible without becoming monolithic
* Safe by design (explicit confirmation for critical actions)

The goal is not to build a chatbot.
The goal is to build an operator.

---

## Architecture Overview

EVO follows a layered decision architecture:

```
Input (Text / STT)
        ↓
EvoBrain (Decision Engine)
        ↓
Skill Registry (Modular Capabilities)
        ↓
System Actions / Memory / Overlay
```

### Core Components

* `EvoBrain` — central decision engine
* `SkillRegistry` — modular capability system
* `MemoryStore` — persistent local JSON storage
* `Overlay (PySide6)` — real-time visual HUD
* `TTS (System.Speech)` — offline voice output
* `STT (Vosk)` — offline speech recognition

---

## Current Capabilities

* Live overlay with state feedback
* Text-based command control
* Modular skill system
* Persistent local memory
* File ingestion (TXT / MD / JSON / CSV)
* Note search & heuristic summarization (offline)
* Explicit confirmation system for sensitive actions

---

## Running the Project

### 1️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

### 2️⃣ Download Vosk model (not included in repository)

Due to size constraints, speech recognition models are not included.

Place the Portuguese Vosk model inside:

```
models/vosk-pt/
```

### 3️⃣ Run EVO

```bash
python -m EVO.app
```

---

## Project Structure

```
EVO/
├── agent/
│   └── brain.py
├── skills/
│   ├── registry.py
│   ├── help_skill.py
│   ├── read_file_skill.py
│   └── notes_query_skill.py
├── hud/
│   └── overlay.py
├── memory_store.py
├── system_actions.py
└── app.py
```

---

## Design Philosophy

* Deterministic core before probabilistic AI layers
* Explicit decision boundaries
* Separation between interpretation and execution
* Offline-first engineering
* Predictability over hype

---

## Roadmap

Planned improvements:

* Enhanced natural language interpretation layer
* Optional local LLM integration (non-core layer)
* Advanced document indexing
* Context-aware long-term memory
* Plugin-based external skill ecosystem
* Structured logging & observability

---

## Author

**Ivo Ferreira Faria**

---

## License

MIT License
