# -*- coding: utf-8 -*-
"""Извлечение сущностей из текста: субъекты, объекты, действия, контекст.

Извлечение опирается на онтологию (:mod:`privacy_expert.ontology`) и на
позиционные правила русского языка:

* действующее лицо (субъект) — упоминание роли перед сказуемым-действием;
* получатель сведений — упоминание роли в дательном падеже либо после
  предлога «в/к/на/для/перед» и после сказуемого;
* субъект данных («о ком/о чём») — упоминание после маркеров «данные о»,
  «сведения о», «база» и т.п.; такое упоминание не считается получателем.

Дополнительно распознаются отрицания («не передавал»), противоречия
(одновременно «согласие подписано» и «без согласия») и контекстные флаги
(«возможна государственная тайна», «сделка не состоялась» и др.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from . import ontology as onto

# Слова-маркеры и падежные окончания
DATIVE_MARKERS = ("в ", "во ", "к ", "ко ", "на ", "для ", "перед ", "по ")
DATIVE_ENDINGS = ("у", "ю", "ам", "ям", "ому", "ему", "ой", "ым", "им", "ии")
#: Дательный падеж личных местоимений — адресат передачи
DATIVE_PRONOUNS = ("тебе", "вам", "мне", "ему", "ей", "нам", "им")
#: Минимальная оценка структурной близости, при которой роль считается адресатом
RECIPIENT_THRESHOLD = 2
#: Маркеры того, что упоминание роли относится к СУБЪЕКТУ данных («данные о
#: пациенте», «сведения о счетах клиента»), а не к получателю сведений.
DATA_SUBJECT_RE = re.compile(
    r"(?:данн|сведени|информац|баз|счет|счёт|вклад|паспорт|документ|запис|"
    r"выписк|истори|карт|\bо\b|\bоб\b|\bпро\b|насчёт|насчет|касательно)",
    re.IGNORECASE,
)
NEGATION_PREFIX = re.compile(r"(?:^|[\s,(])(?:не|никогда не|ни разу не)\s+$", re.IGNORECASE)


@dataclass
class Mention:
    """Упоминание сущности в тексте."""

    kind: str          # role / object / action / document / context / purpose
    value: str
    start: int
    end: int
    text: str
    confidence: float = 1.0
    strong: bool = True

    def __str__(self) -> str:
        return "%s:%s«%s»" % (self.kind, self.value, self.text)


@dataclass
class Extraction:
    """Результат извлечения сущностей."""

    text: str = ""
    mentions: List[Mention] = field(default_factory=list)
    objects: Dict[str, float] = field(default_factory=dict)
    object_evidences: Dict[str, List[str]] = field(default_factory=dict)
    actions: List[str] = field(default_factory=list)
    actor_roles: List[str] = field(default_factory=list)
    recipient_roles: List[str] = field(default_factory=list)
    data_subject_roles: List[str] = field(default_factory=list)
    documents: List[str] = field(default_factory=list)
    contexts: List[str] = field(default_factory=list)
    purposes: List[str] = field(default_factory=list)
    consent: Optional[str] = None            # "да" | "нет" | None (неизвестно)
    consent_evidence: str = ""
    flags: Set[str] = field(default_factory=set)
    recipient_inferred: bool = False
    contradictions: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def has(self, kind: str, value: str) -> bool:
        return any(m.kind == kind and m.value == value for m in self.mentions)


class Extractor:
    """Извлекатель сущностей (без состояния, может переиспользоваться)."""

    def extract(self, text: str) -> Extraction:
        result = Extraction(text=text)
        if not text or not text.strip():
            return result

        self._collect_roles(text, result)
        self._collect_objects(text, result)
        self._collect_actions(text, result)
        self._collect_documents(text, result)
        self._collect_contexts(text, result)
        self._collect_purposes(text, result)
        self._collect_consent(text, result)
        self._resolve_actor_and_recipient(text, result)
        self._set_flags(result)
        self._find_unknowns(result)
        return result

    # ------------------------------------------------------------------
    # Сбор упоминаний
    # ------------------------------------------------------------------
    @staticmethod
    def _matches(pattern: re.Pattern, text: str) -> List[Tuple[int, int, str]]:
        out: List[Tuple[int, int, str]] = []
        for m in pattern.finditer(text):
            out.append((m.start(), m.end(), m.group(0)))
        return out

    def _collect_roles(self, text: str, res: Extraction) -> None:
        for value, pattern in onto.ROLE_CUES.items():
            for start, end, chunk in self._matches(pattern, text):
                res.mentions.append(Mention("role", value, start, end, chunk))

    def _collect_objects(self, text: str, res: Extraction) -> None:
        for value, pattern in onto.OBJECT_STRONG_CUES.items():
            for start, end, chunk in self._matches(pattern, text):
                res.mentions.append(Mention("object", value, start, end, chunk, 1.0, True))
                self._bump_object(res, value, 1.0, chunk)
        for value, pattern in onto.OBJECT_WEAK_CUES.items():
            for start, end, chunk in self._matches(pattern, text):
                # слабый маркер не повышает уверенность, если уже найден сильный
                if value in res.objects and res.objects[value] >= 1.0:
                    continue
                res.mentions.append(Mention("object", value, start, end, chunk, 0.6, False))
                self._bump_object(res, value, 0.6, chunk)

    @staticmethod
    def _bump_object(res: Extraction, value: str, conf: float, chunk: str) -> None:
        res.objects[value] = max(res.objects.get(value, 0.0), conf)
        evidences = res.object_evidences.setdefault(value, [])
        if chunk not in evidences:
            evidences.append(chunk)

    def _collect_actions(self, text: str, res: Extraction) -> None:
        found: List[Tuple[int, str, str]] = []
        for value, pattern in onto.ACTION_CUES.items():
            for start, end, chunk in self._matches(pattern, text):
                if self._is_negated(text, start):
                    continue
                found.append((start, value, chunk))
        found.sort(key=lambda item: item[0])
        for start, value, chunk in found:
            if value not in res.actions:
                res.actions.append(value)
            res.mentions.append(Mention("action", value, start, start + len(chunk), chunk))

    @staticmethod
    def _is_negated(text: str, start: int) -> bool:
        prefix = text[max(0, start - 15):start]
        return bool(NEGATION_PREFIX.search(prefix))

    def _collect_documents(self, text: str, res: Extraction) -> None:
        for value, pattern in onto.DOCUMENT_CUES.items():
            for start, end, chunk in self._matches(pattern, text):
                if value not in res.documents:
                    res.documents.append(value)
                res.mentions.append(Mention("document", value, start, end, chunk))

    def _collect_contexts(self, text: str, res: Extraction) -> None:
        for value, pattern in onto.CONTEXT_CUES.items():
            chunks = self._matches(pattern, text)
            if not chunks:
                continue
            if value not in res.contexts:
                res.contexts.append(value)
            for start, end, chunk in chunks:
                res.mentions.append(Mention("context", value, start, end, chunk))

    def _collect_purposes(self, text: str, res: Extraction) -> None:
        for value, pattern in onto.PURPOSE_CUES.items():
            for start, end, chunk in self._matches(pattern, text):
                if value not in res.purposes:
                    res.purposes.append(value)
                res.mentions.append(Mention("purpose", value, start, end, chunk))

    def _collect_consent(self, text: str, res: Extraction) -> None:
        yes = onto.CONSENT_YES_CUES.search(text)
        no = onto.CONSENT_NO_CUES.search(text)
        if yes and no:
            res.contradictions.append(
                "противоречие о согласии: одновременно «%s» и «%s»" % (yes.group(0), no.group(0))
            )
            res.consent = None
            res.consent_evidence = "«%s» / «%s»" % (yes.group(0), no.group(0))
            return
        if yes:
            res.consent = "да"
            res.consent_evidence = yes.group(0)
        elif no:
            res.consent = "нет"
            res.consent_evidence = no.group(0)
        else:
            res.consent = None
            res.consent_evidence = "прямых указаний на согласие не найдено"

    # ------------------------------------------------------------------
    # Роли: кто действует и кто получает
    # ------------------------------------------------------------------
    def _resolve_actor_and_recipient(self, text: str, res: Extraction) -> None:
        role_mentions = [m for m in res.mentions if m.kind == "role"]
        if not role_mentions:
            return
        role_mentions.sort(key=lambda m: m.start)

        action_positions = [m.start for m in res.mentions if m.kind == "action"]
        first_action = min(action_positions) if action_positions else len(text)
        if action_positions:
            first_action = self._action_position(text, res)

        # --- действующее лицо -------------------------------------------
        # Субъект — упоминание роли перед сказуемым.  Берём первое упоминание
        # (подлежащее) и, дополнительно, «хранителей тайны» для найденных
        # объектов («сотрудник банка» → и сотрудник, и банк).  Роль
        # «третье_лицо» действующим лицом быть не может по определению.
        keepers = set()
        for obj in res.objects:
            keepers.update(onto.KEEPER_ROLES.get(obj, []))
        actors: List[str] = []
        for m in role_mentions:
            if m.start >= first_action or self._is_vocative(text, m):
                continue
            if m.value == "третье_лицо":
                continue
            if not actors or m.value in keepers:
                if m.value not in actors:
                    actors.append(m.value)
        res.actor_roles = actors

        # --- субъект данных и получатель --------------------------------
        recipients: List[str] = []
        data_subjects: List[str] = []
        for m in role_mentions:
            if m.value in actors and m.start < first_action:
                continue
            score, reason = self._recipient_score(text, m, first_action)
            if score < RECIPIENT_THRESHOLD:
                if m.value not in data_subjects:
                    data_subjects.append(m.value)
                continue
            if m.value not in recipients:
                recipients.append(m.value)
            res.mentions.append(Mention("recipient", m.value, m.start, m.end, m.text,
                                        confidence=min(1.0, 0.5 + 0.15 * score)))
        res.recipient_roles = recipients
        res.data_subject_roles = data_subjects

        # Запрос: получателем сведений является сам запрашивающий, если он
        # наделён законным доступом к соответствующей тайне и НЕ является её
        # хранителем («нотариус запросил у банка сведения о вкладах» →
        # получатель сведений — нотариус; «врач передал данные» → врач хранитель).
        if "запросил" in res.actions and res.objects:
            keeper_roles = set()
            for obj in res.objects:
                keeper_roles.update(onto.KEEPER_ROLES.get(obj, []))
            for role in actors:
                if role in keeper_roles:
                    continue
                if any(role in onto.LAWFUL_ACCESS_ROLES.get(obj, []) for obj in res.objects):
                    res.recipient_roles = [role]
                    res.data_subject_roles = [r for r in res.data_subject_roles if r != role]
                    res.notes.append(
                        "Получателем сведений признан запрашивающий: %s — он наделён "
                        "законным доступом к соответствующей тайне." % role)
                    recipients = [role]
                    break

        # Получатель не назван, но сведения кому-то раскрыты → «третье лицо»
        if not recipients and any(a in onto.DISCLOSURE_ACTIONS for a in res.actions):
            if res.objects:
                res.recipient_roles = ["третье_лицо"]
                res.recipient_inferred = True
                res.notes.append(
                    "Получатель сведений в тексте не назван: по умолчанию принято «третье лицо» "
                    "(лицо, не наделённое законным доступом к тайне)."
                )

    @staticmethod
    def _action_position(text: str, res: Extraction) -> int:
        """Позиция первого действия-разглашения (иначе — первого действия)."""
        disclosure = [m.start for m in res.mentions
                      if m.kind == "action" and m.value in onto.DISCLOSURE_ACTIONS]
        if disclosure:
            return min(disclosure)
        positions = [m.start for m in res.mentions if m.kind == "action"]
        return min(positions) if positions else len(text)

    @staticmethod
    def _is_vocative(text: str, m: Mention) -> bool:
        """Обращение («Коллеги, ...», «Дружище!») — это адресат, а не субъект."""
        tail = text[m.end:m.end + 2].strip()
        return tail.startswith(",") or tail.startswith("!") or tail.startswith(":")

    @staticmethod
    def _recipient_score(text: str, m: Mention, first_action: int) -> Tuple[int, str]:
        """Оценить, является ли упоминание роли адресатом передачи сведений.

        Учитываются только структурные признаки русской речи: дательный падеж
        («конкуренту», «нотариусу», «тебе»), предлог при группе («в полицию»,
        «для внешнего аудита»); позиция «после сказуемого» сама по себе
        адресатом не делает.  Упоминания после маркеров «данные о», «сведения
        о», «счёт», «вклад» относятся к субъекту данных и получателем не
        считаются.
        """
        score = 0
        prefix = text[max(0, m.start - 30):m.start]
        lowered = prefix.lower()
        word = m.text.lower()
        if word in DATIVE_PRONOUNS:
            score += 3
        if any(lowered.endswith(marker) for marker in DATIVE_MARKERS):
            score += 3
        if word.endswith(DATIVE_ENDINGS):
            score += 2
        if word.endswith(("ого", "его", "ой", "ых", "их", "ов", "ев")):
            score -= 2                     # родительный падеж — скорее субъект данных
        if lowered.rstrip().endswith(("что", "чтобы", "который", "которая")):
            score -= 3                     # придаточное предложение: далее идёт подлежащее
        if DATA_SUBJECT_RE.search(lowered):
            score -= 3
        if lowered.rstrip().endswith(("у", "из", "от", "с")):
            score -= 2                     # «у твоего соседа», «из компании»
        return score, prefix

    # ------------------------------------------------------------------
    # Флаги и пробелы в данных
    # ------------------------------------------------------------------
    @staticmethod
    def _set_flags(res: Extraction) -> None:
        if "гос_тайна" in res.contexts:
            res.flags.add("возможна_государственная_тайна")
        if "due_diligence" in res.contexts and "сделка_не_состоялась" in res.contexts:
            res.flags.add("нарушение_обязательств_конфиденциальности")
        if "соглашение_о_конфиденциальности" in res.documents:
            res.flags.add("есть_соглашение_о_конфиденциальности")
        if "устный_запрос" in res.documents:
            res.flags.add("отсутствует_письменный_запрос")
        if "открытый_код" in res.contexts:
            res.flags.add("открытый_исходный_код")
        if res.consent == "нет":
            res.flags.add("согласие_отсутствует")
        if res.consent == "да":
            res.flags.add("согласие_получено")
        if "наследство" in res.contexts and "нотариус" in res.recipient_roles:
            res.flags.add("нотариальный_запрос_по_наследству")

    @staticmethod
    def _find_unknowns(res: Extraction) -> None:
        """Зафиксировать незаполненные слоты — основа для уточняющих вопросов."""
        slots = {
            "объект": res.objects,
            "действие": res.actions,
            "получатель": res.recipient_roles,
            "согласие": res.consent,
            "документ": res.documents,
        }
        res.unknowns = [name for name, value in slots.items() if not value]


__all__ = ["Mention", "Extraction", "Extractor"]
