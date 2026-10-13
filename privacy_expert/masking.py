# -*- coding: utf-8 -*-
"""Частичное маскирование конфиденциальных реквизитов перед записью в журнал.

В ``security_log.txt`` запрещено писать исходный текст целиком: журнал сам
становится носителем тайны.  Поэтому все прямые идентификаторы (ФИО, телефоны,
адреса электронной почты, номера счетов и карт, суммы, ИНН/СНИЛС) заменяются
на частично скрытые формы: «Ива*** И. И.», «+7 913 ***-**-35»,
«4081 **** **** 4567».
"""
from __future__ import annotations

import re
from typing import List, Tuple

MaskRule = Tuple[re.Pattern, str]


def _mask_tail(value: str, keep_head: int = 3, keep_tail: int = 2, filler: str = "*") -> str:
    if len(value) <= keep_head + keep_tail:
        return value[0] + filler * max(0, len(value) - 1)
    return value[:keep_head] + filler * (len(value) - keep_head - keep_tail) + value[-keep_tail:]


def _mask_account(match: re.Match) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return "%s **** **** %s" % (digits[:4], digits[-4:])


def _mask_card(match: re.Match) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return "%s **** **** %s" % (digits[:4], digits[-4:])


def _mask_phone(match: re.Match) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    if len(digits) < 10:
        return "*" * len(match.group(0))
    return "+%s %s ***-**-%s" % (digits[0], digits[1:4], digits[-2:])


def _mask_email(match: re.Match) -> str:
    local, _, domain = match.group(0).partition("@")
    return "%s***@%s" % (local[0], domain)


def _mask_money(match: re.Match) -> str:
    parts = match.group(0).split()
    unit = parts[-1] if parts else ""
    return "*** %s" % unit


def _mask_fio_initials(match: re.Match) -> str:
    """«Иванов И. И.» → «Ива*** И. И.» (фамилия скрывается частично)."""
    surname = match.group(1)
    head = surname[:3]
    return "%s%s %s. %s." % (head, "*" * max(3, len(surname) - 3),
                             match.group(2), match.group(3))


RULES: List[MaskRule] = [
    # ФИО с инициалами: «Иванов И. И.», «Петров П. П.»
    (re.compile(r"\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ])\.\s?([А-ЯЁ])\."), _mask_fio_initials),
    # Полное ФИО из трёх слов: «Иван Петрович Сидоров»
    (re.compile(r"\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{2,})\b"),
     r"\1 \2 \3***"),
    # Номера банковских счетов (20 цифр)
    (re.compile(r"\b\d{20}\b"), _mask_account),
    # Номера банковских карт (16 цифр, возможно с пробелами/дефисами)
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), _mask_card),
    # Телефоны
    (re.compile(r"\+?\d[\d\s\-()]{9,}\d"), _mask_phone),
    # E-mail
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), _mask_email),
    # СНИЛС
    (re.compile(r"\b\d{3}-\d{3}-\d{3}\s?\d{2}\b"), lambda m: "***-***-*** **"),
    # ИНН (10 или 12 цифр)
    (re.compile(r"\b\d{10}(?:\d{2})?\b"), lambda m: _mask_tail(m.group(0), 4, 2)),
    # Денежные суммы
    (re.compile(r"\d[\d\s]*(?:[.,]\d{2})?\s*(?:руб\w*|₽)"), _mask_money),
]


def mask_text(text: str, limit: int = 200, ellipsis: str = "…") -> str:
    """Вернуть частично замаскированный фрагмент текста для журнала."""
    if not text:
        return ""
    masked = text.strip()
    for pattern, repl in RULES:
        masked = pattern.sub(repl, masked)
    masked = re.sub(r"\s+", " ", masked)
    if len(masked) > limit:
        masked = masked[:limit].rstrip() + ellipsis
    return masked


def mask_entities(values: List[str]) -> List[str]:
    """Замаскировать список значений (ФИО, счета и т.п.) для вывода в отчёте."""
    return [mask_text(v, limit=60) for v in values]


__all__ = ["mask_text", "mask_entities", "RULES"]
