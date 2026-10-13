# -*- coding: utf-8 -*-
"""Механизм логического вывода экспертной системы.

Алгоритм:

1. **Извлечение сущностей** (:mod:`privacy_expert.extractor`) — текст
   превращается в набор фактов рабочей памяти.
2. **Прямой вывод (forward chaining)** — правила базы знаний применяются к
   рабочей памяти до достижения неподвижной точки: сработавшее правило
   добавляет новые факты, которые могут включить другие правила (например,
   «нотариус + наследство + запрос» → «есть нотариальный запрос» → «передача
   банковской тайны нотариусу законна»).
3. **Объяснение** — для каждого сработавшего правила сохраняется цепочка:
   какие факты и какие фрагменты текста его включили.
4. **Обработка неполноты** — если правило почти сработало, но для вывода не
   хватает данных, формируется запись «Требуется ручная проверка» со списком
   уточняющих вопросов.
5. **Разрешение конфликтов и агрегация** — если одновременно выявлены
   нарушение и законное исключение по одному закону, система сообщает о спорной
   ситуации; если нарушено несколько законов, выводятся все составы, а
   приоритетное действие выбирается по уровню риска.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import ontology as onto
from .errors import EmptyInputError, RuleBaseError
from .extractor import Extraction, Extractor
from .facts import WorkingMemory
from .logger import LEVEL_MANUAL, LEVEL_SAFE, LEVEL_VIOLATION, LogRecord, SecurityLogger
from .masking import mask_text
from .rules import MATCH, UNKNOWN, Rule, build_rule_base

VERDICT_VIOLATION = "НАРУШЕНИЕ"
VERDICT_MANUAL = "ТРЕБУЕТСЯ РУЧНАЯ ПРОВЕРКА"
VERDICT_SAFE = "НАРУШЕНИЙ НЕ ВЫЯВЛЕНО"

SLOT_QUESTIONS: Dict[str, str] = {
    "объект": "О каких именно сведениях идёт речь: ПДн, коммерческая тайна, "
              "налоговая, банковская или врачебная тайна?",
    "действие": "Какое действие совершено со сведениями: передача, разглашение, "
                "публикация, запрос или отказ?",
    "получатель": "Кому именно переданы сведения и наделён ли получатель законным "
                  "доступом к ним?",
    "согласие": "Давал ли субъект данных письменное согласие на передачу сведений "
                "(с указанием получателя, цели и срока)?",
    "документ": "Каким документом оформлено основание передачи: письменный запрос, "
                "нотариальный запрос, согласие субъекта, соглашение о конфиденциальности?",
}


@dataclass
class Conclusion:
    """Правовой вывод, полученный сработавшим правилом."""

    rule_id: str
    title: str
    verdict: str
    law: str
    article: str
    reason: str
    action: str
    severity: str
    priority: int
    confidence: float
    matched: List[str] = field(default_factory=list)
    source_rules: List[str] = field(default_factory=list)
    remedy: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "rule": self.rule_id,
            "title": self.title,
            "verdict": self.verdict,
            "law": self.law,
            "article": self.article,
            "reason": self.reason,
            "action": self.action,
            "severity": self.severity,
            "confidence": round(self.confidence, 2),
            "matched": self.matched,
            "remedy": self.remedy,
        }


@dataclass
class ManualReviewItem:
    """Запись «Требуется ручная проверка» с уточняющими вопросами."""

    rule_id: str
    title: str
    reason: str
    law: str = ""
    article: str = ""
    matched: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "rule": self.rule_id,
            "title": self.title,
            "reason": self.reason,
            "law": self.law,
            "article": self.article,
            "matched": self.matched,
            "unknowns": self.unknowns,
            "questions": self.questions,
        }


@dataclass
class AnalysisResult:
    """Итог анализа текста."""

    text: str
    masked_text: str
    verdict: str
    extraction: Extraction
    violations: List[Conclusion] = field(default_factory=list)
    lawful: List[Conclusion] = field(default_factory=list)
    manual_reviews: List[ManualReviewItem] = field(default_factory=list)
    possible_violations: List[ManualReviewItem] = field(default_factory=list)
    informational: List[Conclusion] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    laws: List[str] = field(default_factory=list)
    confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)
    log_line: Optional[str] = None
    facts: Dict[str, List[str]] = field(default_factory=dict)
    source: str = "cli"

    @property
    def exit_code(self) -> int:
        from .errors import EXIT_MANUAL, EXIT_OK, EXIT_VIOLATION
        if self.violations:
            return EXIT_VIOLATION
        if self.manual_reviews:
            return EXIT_MANUAL
        return EXIT_OK

    @property
    def primary(self) -> Optional[Conclusion]:
        return self.violations[0] if self.violations else None

    def as_dict(self) -> Dict[str, object]:
        return {
            "verdict": self.verdict,
            "source": self.source,
            "confidence": round(self.confidence, 2),
            "laws": self.laws,
            "actions": self.actions,
            "violations": [c.as_dict() for c in self.violations],
            "lawful": [c.as_dict() for c in self.lawful],
            "informational": [c.as_dict() for c in self.informational],
            "manual_reviews": [m.as_dict() for m in self.manual_reviews],
            "possible_violations": [m.as_dict() for m in self.possible_violations],
            "questions": self.questions,
            "warnings": self.warnings,
            "entities": {
                "objects": self.extraction.objects,
                "actions": self.extraction.actions,
                "actor_roles": self.extraction.actor_roles,
                "recipient_roles": self.extraction.recipient_roles,
                "documents": self.extraction.documents,
                "contexts": self.extraction.contexts,
                "purposes": self.extraction.purposes,
                "consent": self.extraction.consent,
            },
            "masked_text": self.masked_text,
        }


class ExpertSystem:
    """Экспертная система анализа конфиденциальности."""

    def __init__(self, rules: Optional[Sequence[Rule]] = None,
                 logger: Optional[SecurityLogger] = None,
                 extractor: Optional[Extractor] = None) -> None:
        self.rules: List[Rule] = list(rules) if rules is not None else build_rule_base()
        self._validate_rules()
        self.logger = logger
        self.extractor = extractor or Extractor()

    # ------------------------------------------------------------------
    def _validate_rules(self) -> None:
        seen = set()
        for rule in self.rules:
            if rule.rid in seen:
                raise RuleBaseError("Дубликат идентификатора правила: %s" % rule.rid)
            seen.add(rule.rid)
            if not rule.conditions:
                raise RuleBaseError("Правило %s не имеет условий" % rule.rid)

    # ------------------------------------------------------------------
    def extract(self, text: str) -> Extraction:
        """Только извлечение сущностей (без логического вывода)."""
        if text is None or not text.strip():
            raise EmptyInputError("извлечение сущностей")
        return self.extractor.extract(text.strip())

    # ------------------------------------------------------------------
    def analyze(self, text: str, source: str = "cli", log: bool = True) -> AnalysisResult:
        """Проанализировать текст и вернуть результат логического вывода."""
        if text is None or not text.strip():
            raise EmptyInputError(source)
        text = text.strip()

        extraction = self.extractor.extract(text)
        wm = self._build_working_memory(extraction)
        conclusions, partials = self._forward_chain(wm)
        result = self._aggregate(text, extraction, wm, conclusions, partials, source)

        if log and self.logger is not None:
            result.log_line = self._write_log(result)
        return result

    # ------------------------------------------------------------------
    def _build_working_memory(self, ex: Extraction) -> WorkingMemory:
        wm = WorkingMemory()
        for value, confidence in ex.objects.items():
            evidence = ", ".join(ex.object_evidences.get(value, [])[:2])
            wm.assert_fact("object", value, confidence, "extractor", evidence)
        for action in ex.actions:
            wm.assert_fact("action", action, 1.0, "extractor", action)
        for role in ex.actor_roles:
            wm.assert_fact("actor_role", role)
        for role in ex.recipient_roles:
            wm.assert_fact("recipient_role", role,
                           0.9 if ex.recipient_inferred else 1.0,
                           "extractor",
                           "получатель не назван — принято «третье лицо»"
                           if ex.recipient_inferred else "")
        for role in ex.data_subject_roles:
            wm.assert_fact("data_subject_role", role)
        for document in ex.documents:
            wm.assert_fact("document", document)
        for context in ex.contexts:
            wm.assert_fact("context", context)
        for purpose in ex.purposes:
            wm.assert_fact("purpose", purpose)
        if ex.consent:
            wm.assert_fact("consent", ex.consent, 1.0, "extractor", ex.consent_evidence)
        for flag in ex.flags:
            wm.assert_fact("flag", flag)
        # законное основание подтверждается ссылкой на закон в тексте
        if "законное_основание" in ex.contexts:
            wm.assert_fact("context", "законное_основание")
        return wm

    # ------------------------------------------------------------------
    def _forward_chain(self, wm: WorkingMemory):
        """Прямой вывод до неподвижной точки."""
        fired: Dict[str, Conclusion] = {}
        partials: Dict[str, ManualReviewItem] = {}
        changed = True
        iterations = 0
        while changed and iterations < 20:
            changed = False
            iterations += 1
            for rule in sorted(self.rules, key=lambda r: -r.priority):
                if rule.rid in fired:
                    continue
                status, matched_conditions, unknown_conditions = rule.evaluate(wm)
                if status == MATCH:
                    keys: List[Tuple[str, str]] = []
                    for cond in matched_conditions:
                        keys.extend(cond.matched_keys(wm))
                        for fact_key in cond.matched_keys(wm):
                            fact = wm.get(*fact_key)
                            if fact is not None:
                                wm.assert_fact(fact.predicate, fact.value, fact.confidence,
                                               rule.rid, fact.evidence)
                    confidence = wm.min_confidence(keys) if keys else 1.0
                    # Низкая уверенность распознавания — не обвиняем, а просим
                    # ручную проверку (защита от ложных срабатываний).
                    if rule.verdict == "нарушение" and confidence < rule.min_confidence:
                        partials[rule.rid] = ManualReviewItem(
                            rule_id=rule.rid,
                            title="Возможно нарушение: %s (низкая уверенность распознавания)"
                                  % rule.title,
                            reason="Формальные условия правила выполнены, но сведения "
                                   "распознаны по косвенным признакам (уверенность %.2f ниже "
                                   "порога %.2f). Автоматическая квалификация по %s "
                                   "невозможна — требуется ручная проверка."
                                   % (confidence, rule.min_confidence,
                                      rule.article or rule.law or "закону"),
                            law=rule.law,
                            article=rule.article,
                            matched=[c.describe() for c in matched_conditions],
                            unknowns=["достоверность категории сведений"],
                            questions=_dedupe(
                                list(rule.questions.values()) + rule.soft_questions
                                + ["Подтвердите категорию сведений: относится ли информация к "
                                   "охраняемой законом тайне (%s)?" % (rule.law or rule.title)]),
                        )
                        continue
                    for predicate, value in rule.conclusions:
                        wm.assert_fact(predicate, value, 1.0, rule.rid)
                    fired[rule.rid] = Conclusion(
                        rule_id=rule.rid,
                        title=rule.title,
                        verdict=rule.verdict,
                        law=rule.law,
                        article=rule.article,
                        reason=rule.build_reason(wm, matched_conditions),
                        action=rule.action,
                        severity=rule.severity,
                        priority=rule.priority,
                        confidence=confidence,
                        matched=[c.describe() for c in matched_conditions],
                        remedy=rule.remedy,
                    )
                    changed = True
                elif status == UNKNOWN:
                    questions = [cond.question for cond in unknown_conditions if cond.question]
                    for slot in rule.questions:
                        questions.append(rule.questions[slot])
                    partials[rule.rid] = ManualReviewItem(
                        rule_id=rule.rid,
                        title=rule.title,
                        reason="Правило %s почти применимо, но для юридической квалификации "
                               "не хватает данных." % rule.rid,
                        law=rule.law,
                        article=rule.article,
                        matched=[c.describe() for c in matched_conditions],
                        unknowns=[c.describe() for c in unknown_conditions],
                        questions=questions,
                    )
        return fired, partials

    # ------------------------------------------------------------------
    def _aggregate(self, text: str, ex: Extraction, wm: WorkingMemory,
                   fired: Dict[str, Conclusion],
                   partials: Dict[str, ManualReviewItem],
                   source: str) -> AnalysisResult:
        conclusions = list(fired.values())
        violations = sorted([c for c in conclusions if c.verdict == "нарушение"],
                            key=lambda c: (-c.priority, -c.confidence, c.rule_id))
        lawful = sorted([c for c in conclusions if c.verdict == "законно"],
                        key=lambda c: (-c.priority, c.rule_id))
        informational = sorted([c for c in conclusions if c.verdict in ("информация",)],
                               key=lambda c: (-c.priority, c.rule_id))
        unfired = [p for p in partials.values() if p.rule_id not in fired]
        # «Возможно нарушение» — гипотезы с низкой уверенностью распознавания:
        # показываются всегда, но не подменяют установленный вердикт.
        possible_violations = [p for p in unfired if p.title.startswith("Возможно нарушение")]
        manual_from_rules = [p for p in unfired if p not in possible_violations]

        manual_reviews: List[ManualReviewItem] = []
        if not violations:
            manual_reviews.extend(manual_from_rules)
        # если нарушение найдено, вопросы всё равно полезны, но не меняют вердикт
        questions: List[str] = []
        for item in manual_reviews + possible_violations:
            questions.extend(item.questions)

        for conclusion in violations:
            rule = next((r for r in self.rules if r.rid == conclusion.rule_id), None)
            if rule is not None:
                questions.extend(rule.soft_questions)

        # правило/признак «ручная проверка» (например, возможная гостайна)
        for rule in self.rules:
            if rule.verdict == "ручная_проверка" and rule.rid in fired:
                item = ManualReviewItem(
                    rule_id=rule.rid,
                    title=rule.title,
                    reason=rule.reason,
                    law=rule.law,
                    article=rule.article,
                    matched=list(fired[rule.rid].matched),
                    unknowns=[],
                    questions=[q for q in rule.questions.values()],
                )
                manual_reviews.append(item)
                questions.extend(item.questions)

        # недостаточно данных для любого вывода
        if not conclusions and not manual_reviews:
            manual_reviews.append(ManualReviewItem(
                rule_id="GAP-01",
                title="Недостаточно данных для логического вывода",
                reason="В тексте не удалось уверенно определить объект охраны и (или) "
                       "юридически значимые обстоятельства.",
                matched=[],
                unknowns=ex.unknowns,
                questions=[SLOT_QUESTIONS[slot] for slot in ex.unknowns if slot in SLOT_QUESTIONS],
            ))
            questions.extend(manual_reviews[-1].questions)

        # конфликты: по одному закону одновременно «нарушение» и «законно»
        warnings_list: List[str] = []
        if ex.contradictions:
            warnings_list.append("Обнаружено противоречие в исходных данных: "
                                 + "; ".join(ex.contradictions)
                                 + ". Требуется ручная проверка.")
        for violation in violations:
            for ok in lawful:
                if violation.law and ok.law and _law_key(violation.law) == _law_key(ok.law):
                    note = ("Спорная ситуация: по %s одновременно применимы нарушение (%s) "
                            "и законное исключение (%s). Требуется ручная проверка."
                            % (_law_key(violation.law), violation.rule_id, ok.rule_id))
                    if note not in warnings_list:
                        warnings_list.append(note)
                    manual_reviews.append(ManualReviewItem(
                        rule_id="CONFLICT-%s-%s" % (violation.rule_id, ok.rule_id),
                        title="Конфликт правил",
                        reason=note,
                        law=violation.law,
                        article=violation.article,
                        matched=violation.matched,
                        unknowns=[],
                        questions=["Уточните юридически значимые обстоятельства: "
                                   "какое основание передачи действует в действительности?"],
                    ))

        if ex.contradictions and not manual_reviews:
            manual_reviews.append(ManualReviewItem(
                rule_id="GAP-02",
                title="Противоречивые сведения о согласии",
                reason="; ".join(ex.contradictions),
                questions=[SLOT_QUESTIONS["согласие"]],
            ))

        # несколько законов одновременно
        laws = _unique_laws(violations)
        multiple_laws = len(laws) > 1
        if multiple_laws:
            msg = ("Одновременно выявлены нарушения нескольких федеральных законов: %s. "
                   "Каждый состав квалифицируется самостоятельно, действия назначаются "
                   "по наиболее строгому режиму." % "; ".join(laws))
            warnings_list.append(msg)

        # приоритетное действие
        actions = _priority_actions(violations)

        # вердикт и уверенность
        if violations:
            verdict = VERDICT_VIOLATION
            confidence = max(0.0, min(v.confidence for v in violations))
        elif manual_reviews or ex.contradictions:
            verdict = VERDICT_MANUAL
            confidence = 0.5
        else:
            verdict = VERDICT_SAFE
            confidence = min([c.confidence for c in lawful] or [1.0])

        answer_questions = _dedupe(questions)
        if not violations and not answer_questions:
            answer_questions = [SLOT_QUESTIONS[slot] for slot in ex.unknowns
                                if slot in SLOT_QUESTIONS]

        result = AnalysisResult(
            text=text,
            masked_text=mask_text(text, limit=300),
            verdict=verdict,
            extraction=ex,
            violations=violations,
            lawful=lawful,
            informational=informational,
            manual_reviews=manual_reviews,
            possible_violations=possible_violations,
            questions=answer_questions,
            actions=actions,
            laws=laws,
            confidence=confidence,
            warnings=_dedupe(warnings_list),
            facts=wm.snapshot(),
            source=source,
        )
        return result

    # ------------------------------------------------------------------
    def _write_log(self, result: AnalysisResult) -> Optional[str]:
        assert self.logger is not None
        if result.violations:
            level = LEVEL_VIOLATION
            law = "; ".join("%s — %s" % (v.law, v.article) for v in result.violations)
        elif result.manual_reviews:
            level = LEVEL_MANUAL
            law = "; ".join(_dedupe([m.law for m in result.manual_reviews if m.law]))
        else:
            level = LEVEL_SAFE
            law = "; ".join("%s — %s" % (c.law, c.article) for c in result.lawful)
        entities = _entities_line(result.extraction)
        record = LogRecord(
            level=level,
            law=law or "—",
            entities=entities,
            action=", ".join(result.actions) or "ничего не делать",
            source=result.source,
            text=result.text,
            confidence=result.confidence,
            rules=", ".join([c.rule_id for c in result.violations]
                            + [m.rule_id for m in result.manual_reviews]) or "—",
        )
        return self.logger.log(record)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def _law_key(law: str) -> str:
    for token in ("152-ФЗ", "146-ФЗ", "98-ФЗ", "395-1", "323-ФЗ", "5485-1", "115-ФЗ", "127-ФЗ"):
        if token in law:
            return token
    return law


def _unique_laws(violations: Sequence[Conclusion]) -> List[str]:
    laws: List[str] = []
    for violation in violations:
        key = _law_key(violation.law)
        if key and key not in laws:
            laws.append(key)
    return laws


def _priority_actions(violations: Sequence[Conclusion]) -> List[str]:
    order = {"удалить": 3, "маскировать": 2, "ничего не делать": 1}
    if not violations:
        return ["ничего не делать"]
    best = max(order.get(v.action, 1) for v in violations)
    actions = [a for a, rank in order.items() if rank == best]
    if best == 1:
        return ["ничего не делать"]
    return actions


def _entities_line(ex: Extraction) -> str:
    parts = []
    if ex.objects:
        parts.append("объект=%s" % ", ".join(onto.OBJECT_LABEL.get(o, o) for o in ex.objects))
    if ex.actions:
        parts.append("действие=%s" % ", ".join(onto.ACTION_LABEL.get(a, a) for a in ex.actions))
    if ex.actor_roles:
        parts.append("субъект(источник)=%s" % ", ".join(ex.actor_roles))
    if ex.recipient_roles:
        parts.append("получатель=%s" % ", ".join(ex.recipient_roles))
    if ex.documents:
        parts.append("документ=%s" % ", ".join(ex.documents))
    if ex.consent:
        parts.append("согласие=%s" % ex.consent)
    if ex.contexts:
        parts.append("контекст=%s" % ", ".join(ex.contexts))
    return "; ".join(parts)


def _dedupe(items: Sequence[str]) -> List[str]:
    out: List[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


__all__ = [
    "ExpertSystem", "AnalysisResult", "Conclusion", "ManualReviewItem",
    "VERDICT_VIOLATION", "VERDICT_MANUAL", "VERDICT_SAFE", "SLOT_QUESTIONS",
]
