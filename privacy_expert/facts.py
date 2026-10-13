# -*- coding: utf-8 -*-
"""Рабочая память экспертной системы: факты и вывод фактов из фактов.

Модель знаний — продукционная.  Факт имеет вид предикат(значение) с
коэффициентом уверенности и ссылкой на источник (лингвистический маркер или
правило вывода).  Правила проверяют условия на рабочей памяти и добавляют в неё
новые факты; цикл повторяется до достижения неподвижной точки (прямой вывод,
forward chaining).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class Fact:
    """Единица знания: предикат(значение)."""

    predicate: str          # object / recipient_role / action / consent / ...
    value: str              # налоговая_тайна / конкурент / передал / нет / ...
    confidence: float = 1.0  # уверенность 0..1
    source: str = "extractor"  # "extractor" или идентификатор правила
    evidence: str = ""       # фрагмент текста или пояснение

    @property
    def key(self) -> Tuple[str, str]:
        return (self.predicate, self.value)

    def __str__(self) -> str:
        return "%s=%s" % (self.predicate, self.value)


@dataclass
class WorkingMemory:
    """Набор фактов с поддержкой монотонного добавления."""

    facts: Dict[Tuple[str, str], Fact] = field(default_factory=dict)

    # -- запись -----------------------------------------------------------
    def add(self, fact: Fact) -> bool:
        """Добавить факт.  Возвращает True, если память изменилась."""
        old = self.facts.get(fact.key)
        if old is not None:
            # усиливаем уверенность, если пришёл более надёжный источник
            if fact.confidence > old.confidence:
                self.facts[fact.key] = fact
                return True
            return False
        self.facts[fact.key] = fact
        return True

    def assert_fact(self, predicate: str, value: str, confidence: float = 1.0,
                    source: str = "extractor", evidence: str = "") -> bool:
        return self.add(Fact(predicate, value, confidence, source, evidence))

    # -- чтение -----------------------------------------------------------
    def holds(self, predicate: str, value: str) -> bool:
        return (predicate, value) in self.facts

    def values(self, predicate: str) -> List[str]:
        return [f.value for f in self.facts.values() if f.predicate == predicate]

    def get(self, predicate: str, value: str) -> Optional[Fact]:
        return self.facts.get((predicate, value))

    def has_predicate(self, predicate: str) -> bool:
        return any(f.predicate == predicate for f in self.facts.values())

    def all(self) -> Iterable[Fact]:
        return self.facts.values()

    def by_predicate(self, predicate: str) -> List[Fact]:
        return [f for f in self.facts.values() if f.predicate == predicate]

    def min_confidence(self, keys: Iterable[Tuple[str, str]]) -> float:
        """Минимальная уверенность среди указанных фактов (для наследования)."""
        values = [self.facts[k].confidence for k in keys if k in self.facts]
        return min(values) if values else 1.0

    def explain(self, keys: Iterable[Tuple[str, str]]) -> List[str]:
        out = []
        for key in keys:
            fact = self.facts.get(key)
            if fact is not None:
                out.append(str(fact))
        return out

    def snapshot(self) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for fact in self.facts.values():
            result.setdefault(fact.predicate, []).append(fact.value)
        return result
