# -*- coding: utf-8 -*-
"""Исполнение рекомендуемых действий: удалить / маскировать / ничего не делать.

Методичка к лабораторной работе формулирует действия как «удалить; заменить
(маскировать); ничего не делать», поэтому система не только рекомендует
действие, но и умеет его выполнить (режим ``--apply``):

* **удалить** — исходный текст заменяется пометкой ``[удалено]`` и служебной
  шапкой с указанием причины (закон, статья, правило);
* **маскировать** — сохраняется копия текста, в которой прямые идентификаторы
  (ФИО, счета, карты, телефоны, e-mail, ИНН/СНИЛС, суммы) частично скрыты,
  а структура текста (переносы строк, абзацы) сохранена;
* **ничего не делать** — файл не создаётся: нарушений не выявлено либо
  действие правомерно.

Запись по умолчанию идёт в НОВЫЙ файл (``<имя>.applied.<расширение>``), исходный
документ не изменяется. Перезапись исходного файла возможна только явным
флагом ``--in-place``, при этом рядом создаётся резервная копия ``.bak``.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .engine import AnalysisResult
from .masking import mask_document

DELETE_MARK = "[удалено]"
DEFAULT_OUTPUT = "applied_output.txt"

ACTION_DELETE = "удалить"
ACTION_MASK = "маскировать"
ACTION_NONE = "ничего не делать"


@dataclass
class AppliedAction:
    """Результат применения действия к тексту."""

    action: str
    path: Optional[str] = None
    written: bool = False
    bytes_written: int = 0
    backup_path: Optional[str] = None
    note: str = ""
    header: List[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.written

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "written": self.written,
            "path": self.path,
            "bytes": self.bytes_written,
            "backup": self.backup_path,
            "note": self.note,
        }


class ActionApplier:
    """Применение рекомендованного действия к анализируемому тексту."""

    def __init__(self, in_place: bool = False, header: bool = True,
                 backup: bool = True) -> None:
        self.in_place = in_place
        self.header = header
        self.backup = backup

    # ------------------------------------------------------------------
    def default_output_path(self, source_path: Optional[str]) -> str:
        """Куда писать результат, если путь не задан явно."""
        if source_path:
            stem, extension = os.path.splitext(source_path)
            return "%s.applied%s" % (stem, extension or ".txt")
        return DEFAULT_OUTPUT

    # ------------------------------------------------------------------
    def apply(self, result: AnalysisResult, text: str,
              out_path: Optional[str] = None,
              source_path: Optional[str] = None) -> AppliedAction:
        """Выполнить действие, рекомендованное системой."""
        action = (result.actions or [ACTION_NONE])[0]

        if action == ACTION_NONE:
            return AppliedAction(
                action=action,
                written=False,
                note="Нарушений не выявлено — изменения в файл не вносятся.",
            )

        header = self._build_header(result, source_path) if self.header else []

        if action == ACTION_DELETE:
            body = DELETE_MARK
            note = ("Текст заменён пометкой «%s»: сведения удалены из документа."
                    % DELETE_MARK)
        elif action == ACTION_MASK:
            body = mask_document(text)
            note = ("Сохранена маскированная копия: прямые идентификаторы частично "
                    "скрыты, структура текста сохранена.")
        else:  # неизвестное действие — трактуем как «ничего не делать»
            return AppliedAction(action=action, written=False,
                                 note="Действие «%s» не требует изменения файла." % action)

        content = "\n".join(header + [body]) if header else body
        if not content.endswith("\n"):
            content += "\n"

        target = out_path or self.default_output_path(source_path)
        backup_path = None
        if self.in_place and source_path:
            target = source_path
            if self.backup and os.path.exists(source_path):
                backup_path = source_path + ".bak"
                shutil.copy2(source_path, backup_path)

        directory = os.path.dirname(os.path.abspath(target))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(content)

        return AppliedAction(
            action=action,
            path=target,
            written=True,
            bytes_written=len(content.encode("utf-8")),
            backup_path=backup_path,
            note=note,
            header=header,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _build_header(result: AnalysisResult, source_path: Optional[str]) -> List[str]:
        """Служебная шапка с причиной обработки (не является частью документа)."""
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = ["# --- экспертная система анализа конфиденциальности ---"]
        if result.violations:
            primary = result.violations[0]
            lines.append("# Действие: %s (нарушение %s)" % (result.actions[0], primary.law))
            lines.append("# Норма: %s" % primary.article)
            lines.append("# Правило: %s — %s" % (primary.rule_id, primary.title))
        elif result.actions == [ACTION_MASK]:
            laws = "; ".join(c.law for c in result.lawful) or "требуется ручная проверка"
            lines.append("# Действие: маскировать (предупредительная мера)")
            lines.append("# Основание: %s" % laws)
        else:
            lines.append("# Действие: %s" % result.actions[0])
        lines.append("# Вердикт: %s; уверенность %.2f" % (result.verdict, result.confidence))
        lines.append("# Источник: %s" % (source_path or result.source))
        lines.append("# Дата обработки: %s" % stamp)
        lines.append("# ---")
        return lines


__all__ = ["ActionApplier", "AppliedAction", "DELETE_MARK",
           "ACTION_DELETE", "ACTION_MASK", "ACTION_NONE", "DEFAULT_OUTPUT"]
