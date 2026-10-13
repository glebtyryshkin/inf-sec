# -*- coding: utf-8 -*-
"""Экспертная система анализа конфиденциальности (лабораторная работа № 2).

Пример использования::

    from privacy_expert import ExpertSystem, SecurityLogger

    system = ExpertSystem(logger=SecurityLogger("security_log.txt"))
    result = system.analyze("Сотрудник ФНС передал данные конкуренту.")
    print(result.verdict)
    for conclusion in result.violations:
        print(conclusion.law, conclusion.article, conclusion.reason)
"""
from __future__ import annotations

from .actions import ACTION_DELETE, ACTION_MASK, ACTION_NONE, ActionApplier, AppliedAction
from .engine import (VERDICT_MANUAL, VERDICT_SAFE, VERDICT_VIOLATION, AnalysisResult,
                     Conclusion, ExpertSystem, ManualReviewItem)
from .errors import (EXIT_ERROR, EXIT_MANUAL, EXIT_OK, EXIT_VIOLATION, EmptyInputError,
                     EncodingError, ExpertSystemError, InputFileNotFound, RuleBaseError)
from .extractor import Extraction, Extractor
from .logger import LEVEL_MANUAL, LEVEL_SAFE, LEVEL_VIOLATION, LogRecord, SecurityLogger
from .masking import mask_document, mask_text
from .report import render_result
from .rules import build_rule_base

__version__ = "1.0.0"

__all__ = [
    "ExpertSystem", "AnalysisResult", "Conclusion", "ManualReviewItem",
    "Extractor", "Extraction", "SecurityLogger", "LogRecord", "build_rule_base",
    "render_result", "mask_text", "mask_document",
    "ActionApplier", "AppliedAction", "ACTION_DELETE", "ACTION_MASK", "ACTION_NONE",
    "VERDICT_VIOLATION", "VERDICT_MANUAL", "VERDICT_SAFE",
    "LEVEL_VIOLATION", "LEVEL_MANUAL", "LEVEL_SAFE",
    "ExpertSystemError", "InputFileNotFound", "EmptyInputError", "EncodingError",
    "RuleBaseError", "EXIT_OK", "EXIT_ERROR", "EXIT_VIOLATION", "EXIT_MANUAL",
    "__version__",
]
