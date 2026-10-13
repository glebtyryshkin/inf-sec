# -*- coding: utf-8 -*-
"""Журнал инцидентов информационной безопасности (``security_log.txt``).

Формат строки журнала::

    2026-10-13 14:22:31 | НАРУШЕНИЕ | 146-ФЗ ст. 102 НК РФ; ст. 183 УК РФ |
    объект=налоговая тайна; получатель=конкурент | действие=удалить |
    источник=cli | текст: «Сотрудник Ф*** перед*** данные о нал*** …»

Всегда пишется: дата и время, тип нарушения (или «требуется ручная проверка»),
норма права, извлечённые сущности, рекомендуемое действие, источник ввода и
частично замаскированный исходный текст.  Файл открывается в режиме добавления.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .masking import mask_text

LOG_HEADER = (
    "# security_log.txt — журнал инцидентов экспертной системы анализа конфиденциальности\n"
    "# Формат: дата и время | тип | норма права | сущности | действие | источник | текст (маскирован)\n"
)

LEVEL_VIOLATION = "НАРУШЕНИЕ"
LEVEL_MANUAL = "РУЧНАЯ ПРОВЕРКА"
LEVEL_SAFE = "БЕЗОПАСНО"


@dataclass
class LogRecord:
    """Одна запись журнала."""

    level: str
    law: str
    entities: str
    action: str
    source: str
    text: str
    confidence: float = 1.0
    rules: str = ""
    timestamp: Optional[datetime] = None

    def formatted(self, mask_limit: int = 180) -> str:
        ts = (self.timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        return " | ".join([
            ts,
            self.level,
            self.law or "—",
            self.entities or "—",
            "действие=%s" % self.action,
            "источник=%s" % self.source,
            "правила=%s" % (self.rules or "—"),
            "уверенность=%.2f" % self.confidence,
            "текст: «%s»" % mask_text(self.text, limit=mask_limit),
        ])


class SecurityLogger:
    """Простой файловый журнал инцидентов."""

    def __init__(self, path: str = "security_log.txt", enabled: bool = True,
                 log_safe: bool = False) -> None:
        self.path = path
        self.enabled = enabled
        self.log_safe = log_safe
        self.written: List[str] = []

    def _ensure_file(self) -> None:
        if not os.path.exists(self.path):
            directory = os.path.dirname(os.path.abspath(self.path))
            if directory and not os.path.isdir(directory):
                os.makedirs(directory, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as handle:
                handle.write(LOG_HEADER)

    def log(self, record: LogRecord) -> Optional[str]:
        if not self.enabled:
            return None
        if record.level == LEVEL_SAFE and not self.log_safe:
            return None
        self._ensure_file()
        line = record.formatted()
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        self.written.append(line)
        return line

    def tail(self, count: int = 10) -> List[str]:
        """Последние строки журнала (для демонстрации в отчёте)."""
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as handle:
            lines = [line.rstrip("\n") for line in handle if line.strip()]
        return lines[-count:]


__all__ = ["SecurityLogger", "LogRecord", "LOG_HEADER",
           "LEVEL_VIOLATION", "LEVEL_MANUAL", "LEVEL_SAFE"]
