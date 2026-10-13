# -*- coding: utf-8 -*-
"""Исключения экспертной системы и коды возврата CLI."""
from __future__ import annotations

# Коды возврата процесса
EXIT_OK = 0            # нарушений не выявлено
EXIT_ERROR = 1         # ошибка ввода-вывода / некорректные данные
EXIT_VIOLATION = 2     # выявлено нарушение
EXIT_MANUAL = 3        # требуется ручная проверка


class ExpertSystemError(Exception):
    """Базовое исключение системы."""

    exit_code = EXIT_ERROR

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def user_message(self) -> str:
        text = self.message
        if self.hint:
            text += "\n  Подсказка: " + self.hint
        return text


class InputFileNotFound(ExpertSystemError):
    """Файл с анализируемым текстом не найден."""

    def __init__(self, path: str) -> None:
        super().__init__(
            "Ошибка ввода: файл не найден — %s" % path,
            "проверьте путь к файлу или запустите программу в режиме ввода с клавиатуры.",
        )
        self.path = path


class EmptyInputError(ExpertSystemError):
    """Пустой текст (или текст, состоящий из пробелов) — анализировать нечего."""

    def __init__(self, source: str = "ввод") -> None:
        super().__init__(
            "Ошибка ввода: получен пустой текст (%s)." % source,
            "передайте непустой текст: с клавиатуры, через --text или --file.",
        )


class EncodingError(ExpertSystemError):
    """Не удалось прочитать файл ни в одной из поддерживаемых кодировок."""

    def __init__(self, path: str, encodings: str) -> None:
        super().__init__(
            "Ошибка чтения файла %s: не удалось определить кодировку (%s)." % (path, encodings),
            "сохраните файл в UTF-8 и повторите запуск.",
        )


class RuleBaseError(ExpertSystemError):
    """Некорректная база правил (дубликаты идентификаторов, пустые условия и т.п.)."""


class MultipleViolationsWarning(UserWarning):
    """Одновременно выявлено несколько нарушений разных законов.

    Это не ошибка: система обязана показать все составы и выбрать приоритетное
    действие.  Предупреждение выводится пользователю отдельной строкой.
    """


__all__ = [
    "ExpertSystemError",
    "InputFileNotFound",
    "EmptyInputError",
    "EncodingError",
    "RuleBaseError",
    "MultipleViolationsWarning",
    "EXIT_OK",
    "EXIT_ERROR",
    "EXIT_VIOLATION",
    "EXIT_MANUAL",
]
