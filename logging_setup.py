"""
EVO - Enhanced Virtual Operator
Logging Setup

Objetivo:
- Criar logs consistentes (ficheiro + consola)
- Facilitar debug e auditoria
- Evitar prints espalhados pelo projeto
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(app_name: str = "EVO") -> None:
    """
    Configura logging global:
    - consola (INFO)
    - ficheiro rotativo (INFO), em ./logs/evo.log
    """
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    log_file = logs_dir / "evo.log"

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Limpar handlers para evitar duplicação quando reinicias a app em dev
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Consola
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    # Ficheiro rotativo (mantém 3 backups)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(fmt)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    logging.getLogger(app_name).info("Logging iniciado.")
