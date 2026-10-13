# -*- coding: utf-8 -*-
"""Вывод результата анализа в консоль (человекочитаемый отчёт)."""
from __future__ import annotations

import re
import textwrap
from typing import List

from . import ontology as onto
from .engine import (AnalysisResult, VERDICT_MANUAL, VERDICT_SAFE,
                     VERDICT_VIOLATION)

WIDTH = 78
COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "cyan": "\033[36m",
}


def _c(text: str, color: str, enabled: bool) -> str:
    return "%s%s%s" % (COLORS[color], text, COLORS["reset"]) if enabled else text


def _rule_line(char: str = "─") -> str:
    return char * WIDTH


def render_result(result: AnalysisResult, color: bool = True, explain: bool = True,
                  show_text: bool = True) -> str:
    """Собрать текстовое представление результата анализа."""
    lines: List[str] = []
    verdict_color = {
        VERDICT_VIOLATION: "red",
        VERDICT_MANUAL: "yellow",
        VERDICT_SAFE: "green",
    }.get(result.verdict, "cyan")

    lines.append(_rule_line("═"))
    lines.append(" " + _c("ВЕРДИКТ: %s" % result.verdict, verdict_color, color))
    lines.append(" Уверенность вывода: %.2f | Правил сработало: %d | Источник: %s"
                 % (result.confidence,
                    len(result.violations) + len(result.lawful) + len(result.informational),
                    result.source))
    if result.laws:
        lines.append(" Нарушенные законы: " + ", ".join(result.laws))
    lines.append(_rule_line("═"))

    if show_text:
        lines.append("")
        lines.append(_c("ИСХОДНЫЙ ТЕКСТ", "bold", color))
        text = result.text if len(result.text) <= 320 else result.text[:320] + "…"
        for chunk in _wrap(text, WIDTH - 2):
            lines.append("  " + chunk)

    ex = result.extraction
    lines.append("")
    lines.append(_c("ИЗВЛЕЧЁННЫЕ СУЩНОСТИ", "bold", color))
    for label, values in (
        ("субъекты", [_role_label(r) for r in ex.actor_roles]),
        ("объекты", ["%s (уверенность %.2f)" % (onto.OBJECT_LABEL.get(o, o), c)
                     for o, c in sorted(ex.objects.items(), key=lambda kv: -kv[1])]),
        ("действия", [onto.ACTION_LABEL.get(a, a) for a in ex.actions]),
        ("получатели", [_role_label(r) for r in ex.recipient_roles]
            + (["(получатель не назван — принято «третье лицо»)"] if ex.recipient_inferred else [])),
        ("документы", [onto.DOCUMENT_LABEL.get(d, d) for d in ex.documents]),
        ("контекст", ex.contexts),
        ("цели", ex.purposes),
        ("согласие", [("%s — %s" % (ex.consent, ex.consent_evidence)) if ex.consent
                      else "не установлено — %s" % ex.consent_evidence]),
    ):
        if values:
            lines.append("  %-11s: %s" % (label, "; ".join(str(v) for v in values)))

    if result.violations:
        lines.append("")
        lines.append(_c("ВЫЯВЛЕННЫЕ НАРУШЕНИЯ (%d)" % len(result.violations), "red", color))
        for index, item in enumerate(result.violations, start=1):
            lines.append("  [%d] %s — %s" % (index, item.rule_id, item.title))
            lines.append("      Закон    : %s" % (item.law or "—"))
            lines.append("      Статья   : %s" % (item.article or "—"))
            lines.append("      Риск     : %s (уверенность %.2f)" % (item.severity, item.confidence))
            lines.append("      Действие : %s" % item.action)
            if explain:
                for chunk in _wrap("Почему   : " + item.reason, WIDTH - 8):
                    lines.append("      " + chunk)
            lines.append("      Правило  : ЕСЛИ %s" % "; ".join(item.matched))

    if result.lawful:
        lines.append("")
        lines.append(_c("ЗАКОННЫЕ ИСКЛЮЧЕНИЯ / ПРАВОМЕРНЫЕ ДЕЙСТВИЯ (%d)"
                        % len(result.lawful), "green", color))
        for item in result.lawful:
            lines.append("  ✓ %s — %s" % (item.rule_id, item.title))
            lines.append("      Норма: %s; %s" % (item.law, item.article))
            if explain:
                for chunk in _wrap("Почему: " + item.reason, WIDTH - 8):
                    lines.append("      " + chunk)

    if result.informational:
        lines.append("")
        lines.append(_c("СПРАВОЧНО", "cyan", color))
        for item in result.informational:
            lines.append("  · %s — %s" % (item.rule_id, item.title))
            for chunk in _wrap(item.reason, WIDTH - 6):
                lines.append("    " + chunk)

    if result.possible_violations:
        lines.append("")
        lines.append(_c("ВОЗМОЖНЫЕ НАРУШЕНИЯ — ТРЕБУЮТ ПРОВЕРКИ (%d)"
                        % len(result.possible_violations), "yellow", color))
        for item in result.possible_violations:
            lines.append("  ~ %s — %s" % (item.rule_id, item.title))
            if item.law:
                lines.append("      Норма: %s; %s" % (item.law, item.article))
            for chunk in _wrap(item.reason, WIDTH - 8):
                lines.append("      " + chunk)
            for question in item.questions:
                for index, chunk in enumerate(_wrap("• " + question, WIDTH - 8)):
                    lines.append("      " + (chunk if index == 0 else "  " + chunk))

    if result.manual_reviews:
        lines.append("")
        lines.append(_c("ТРЕБУЕТСЯ РУЧНАЯ ПРОВЕРКА (%d)" % len(result.manual_reviews),
                        "yellow", color))
        for item in result.manual_reviews:
            lines.append("  ? %s — %s" % (item.rule_id, item.title))
            for chunk in _wrap(item.reason, WIDTH - 6):
                lines.append("    " + chunk)
            if item.unknowns:
                lines.append("    Не хватает данных: %s" % "; ".join(item.unknowns))
            for question in item.questions:
                for index, chunk in enumerate(_wrap("• " + question, WIDTH - 8)):
                    lines.append("    " + (chunk if index == 0 else "  " + chunk))

    lines.append("")
    lines.append(_c("РЕКОМЕНДУЕМЫЕ ДЕЙСТВИЯ", "bold", color))
    for action in result.actions:
        lines.append("  • %s%s" % (action, _action_comment(action)))

    if result.warnings:
        lines.append("")
        lines.append(_c("ПРЕДУПРЕЖДЕНИЯ", "yellow", color))
        for warning in result.warnings:
            for chunk in _wrap("! " + warning, WIDTH - 4):
                lines.append("  " + chunk)

    if result.log_line:
        lines.append("")
        lines.append(_c("ЖУРНАЛ", "dim", color))
        for chunk in _wrap(result.log_line, WIDTH - 2):
            lines.append("  " + chunk)

    lines.append(_rule_line("═"))
    return "\n".join(chunk for line in lines for chunk in _fit(line))


ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _fit(line: str, width: int = WIDTH) -> List[str]:
    """Перенести слишком длинную строку, сохранив отступ (висячий отступ)."""
    visible = ANSI_RE.sub("", line)
    if len(visible) <= width:
        return [line]
    indent = len(line) - len(line.lstrip())
    hanging = " " * (indent + 2)
    return textwrap.wrap(line, width=width, subsequent_indent=hanging,
                         break_long_words=True, break_on_hyphens=False,
                         replace_whitespace=False) or [line]


def _action_comment(action: str) -> str:
    return {
        "удалить": "  (уничтожить сведения / отозвать публикацию, уведомить ответственного за ПДн)",
        "маскировать": "  (заменить реквизиты, обезличить, ограничить доступ)",
        "ничего не делать": "  (нарушений не выявлено либо действие правомерно)",
    }.get(action, "")


def _role_label(role: str) -> str:
    return {
        "налоговый_орган": "налоговый орган (ФНС)",
        "третье_лицо": "третье лицо",
        "иностранный_орган": "иностранный орган",
        "иностранная_компания": "иностранная компания",
        "росфинмониторинг": "Росфинмониторинг",
        "сотрудник": "сотрудник",
        "клиент": "клиент",
        "пациент": "пациент",
        "врач": "медицинский работник",
        "банк": "банк",
        "конкурент": "конкурент",
        "нотариус": "нотариус",
        "полиция": "органы полиции/следствия",
        "суд": "суд",
        "аудитор": "аудитор",
        "журналист": "журналист/редакция",
        "адвокат": "адвокат",
    }.get(role, role)


def _wrap(text: str, width: int) -> List[str]:
    words = str(text).split()
    lines: List[str] = []
    current = ""
    for word in words:
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


__all__ = ["render_result", "WIDTH"]
