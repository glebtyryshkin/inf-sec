# -*- coding: utf-8 -*-
"""Модульные тесты экспертной системы анализа конфиденциальности.

Запуск::

    python -m unittest discover -s tests -v          # из корня проекта
    python -m unittest tests.test_engine -v
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import main as cli                                            # noqa: E402
from privacy_expert import (ActionApplier, ExpertSystem, SecurityLogger,  # noqa: E402
                            mask_document, mask_text, render_result)
from privacy_expert.engine import (VERDICT_MANUAL, VERDICT_SAFE,  # noqa: E402
                                   VERDICT_VIOLATION)
from privacy_expert.actions import DELETE_MARK                      # noqa: E402
from privacy_expert.errors import EmptyInputError, InputFileNotFound  # noqa: E402
from privacy_expert.logger import LEVEL_MANUAL, LEVEL_VIOLATION       # noqa: E402
from privacy_expert.rules import build_rule_base                      # noqa: E402

CASES_PATH = os.path.join(ROOT, "tests", "cases.json")
with open(CASES_PATH, encoding="utf-8") as _handle:
    CASES = json.load(_handle)


class TestAssignmentCases(unittest.TestCase):
    """Не менее 10 тестовых текстов из задания, включая спорные."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.system = ExpertSystem()

    def _analyze(self, case_id: str):
        case = next(c for c in CASES if c["id"] == case_id)
        return case, self.system.analyze(case["text"], source="unittest", log=False)

    def _check(self, case_id: str) -> None:
        case, result = self._analyze(case_id)
        self.assertEqual(case["expected_verdict"], result.verdict,
                         "Несовпадение вердикта для %s" % case_id)
        for law in case["expected_laws"]:
            self.assertTrue(
                any(law in (v.law + " " + v.article) for v in result.violations),
                "В выводе %s нет нормы %s" % (case_id, law))

    def test_T01_formula_with_nda_is_safe(self) -> None:
        case, result = self._analyze("T01")
        self.assertEqual(VERDICT_SAFE, result.verdict)
        self.assertTrue(result.lawful, "Ожидалось законное исключение (NDA + аудит)")

    def test_T02_formula_without_nda_violates_98fz(self) -> None:
        self._check("T02")

    def test_T03_pdn_database_for_mailing(self) -> None:
        case, result = self._analyze("T03")
        self._check("T03")
        hypotheses = " ".join(m.title + m.reason for m in result.possible_violations)
        self.assertIn("98-ФЗ", hypotheses + " ".join(result.laws))

    def test_T04_medical_secret_disclosure(self) -> None:
        self._check("T04")

    def test_T05_tax_secret_via_fns_relative(self) -> None:
        self._check("T05")

    def test_T06_state_secret_requires_manual_review(self) -> None:
        case, result = self._analyze("T06")
        self.assertEqual(VERDICT_MANUAL, result.verdict)
        self.assertTrue(result.manual_reviews, "Ожидалась ручная проверка")
        self.assertIn("государственн", result.manual_reviews[0].reason.lower())

    def test_T07_bank_refused_notary(self) -> None:
        self._check("T07")

    def test_T08_fns_employee_leaked_to_competitor(self) -> None:
        self._check("T08")

    def test_T09_doctor_police_oral_request(self) -> None:
        self._check("T09")

    def test_T10_due_diligence_after_failed_deal(self) -> None:
        self._check("T10")

    def test_T11_written_consent_is_safe(self) -> None:
        self._check("T11")

    def test_T12_doctor_police_written_request_is_lawful(self) -> None:
        self._check("T12")
        case, result = self._analyze("T12")
        self.assertFalse(result.violations, "Письменный запрос — законное основание")

    def test_T13_multiple_laws_at_once(self) -> None:
        case, result = self._analyze("T13")
        self._check("T13")
        self.assertGreaterEqual(len(result.laws), 2, "Ожидалось несколько законов")
        self.assertTrue(any("нескольких федеральных законов" in w for w in result.warnings))

    def test_T14_contradiction_is_flagged(self) -> None:
        case, result = self._analyze("T14")
        self._check("T14")
        self.assertTrue(any("противоречие" in w.lower() for w in result.warnings)
                        or result.manual_reviews, "Противоречие должно быть отмечено")

    def test_T15_notary_request_by_inheritance_is_lawful(self) -> None:
        self._check("T15")

    def test_T16_empty_text_raises(self) -> None:
        with self.assertRaises(EmptyInputError):
            self.system.analyze("   ", log=False)


class TestAllCasesDataDriven(unittest.TestCase):
    """Сквозная проверка всех кейсов из cases.json."""

    def test_all_cases_match_expectations(self) -> None:
        system = ExpertSystem()
        failed = []
        for case in CASES:
            try:
                result = system.analyze(case["text"], source="unittest", log=False)
            except EmptyInputError:
                ok = case["expected_verdict"] == "ОШИБКА"
                if not ok:
                    failed.append(case["id"])
                continue
            laws_ok = all(any(law in (v.law + " " + v.article) for v in result.violations)
                          for law in case["expected_laws"])
            if result.verdict != case["expected_verdict"] or not laws_ok:
                failed.append(case["id"])
        self.assertEqual([], failed, "Не прошли кейсы: %s" % failed)


class TestRuleBase(unittest.TestCase):
    """Требования задания к базе правил."""

    def test_at_least_ten_rules(self) -> None:
        rules = build_rule_base()
        self.assertGreaterEqual(len(rules), 10, "В базе должно быть не менее 10 правил")

    def test_unique_ids_and_legal_references(self) -> None:
        rules = build_rule_base()
        ids = [r.rid for r in rules]
        self.assertEqual(len(ids), len(set(ids)), "Идентификаторы правил должны быть уникальны")
        violations = [r for r in rules if r.verdict == "нарушение"]
        self.assertGreaterEqual(len(violations), 10,
                                "Правил квалификации нарушений должно быть не менее 10")
        for rule in violations:
            self.assertTrue(rule.law, "У правила %s не указан закон" % rule.rid)
            self.assertTrue(rule.article, "У правила %s не указана статья" % rule.rid)
            self.assertTrue(rule.reason, "У правила %s нет обоснования" % rule.rid)
            self.assertIn(rule.action, ("удалить", "маскировать", "ничего не делать"))

    def test_every_rule_has_remedy_or_law(self) -> None:
        for rule in build_rule_base():
            self.assertTrue(rule.law or rule.verdict in ("ручная_проверка", "информация"),
                            "Правило %s без правовой нормы" % rule.rid)


class TestEntities(unittest.TestCase):
    """Проверка извлечения сущностей четырёх типов."""

    def setUp(self) -> None:
        self.system = ExpertSystem()

    def test_all_entity_types_extracted(self) -> None:
        text = ("Сотрудник ФНС по секрету передал конкуренту данные о налоговых платежах "
                "клиента без согласия, суд проверку не проводил.")
        ex = self.system.extract(text)
        self.assertIn("налоговая_тайна", ex.objects)
        self.assertIn("передал", ex.actions)
        self.assertIn("налоговый_орган", ex.actor_roles)
        self.assertIn("конкурент", ex.recipient_roles)
        self.assertIn("по_секрету", ex.contexts)
        self.assertEqual("нет", ex.consent)

    def test_negation_is_recognised(self) -> None:
        ex = self.system.extract("Сотрудник не передавал данные клиентов третьим лицам.")
        self.assertNotIn("передал", ex.actions, "Отрицание не должно давать действие «передал»")

    def test_word_forms_are_recognised(self) -> None:
        ex = self.system.extract(
            "Планируется передача сведений, составляющих коммерческую тайну, "
            "и публикация исходного кода продукта.")
        self.assertIn("коммерческая_тайна", ex.objects)
        self.assertIn("передал", ex.actions)
        self.assertIn("опубликовал", ex.actions)


class TestInference(unittest.TestCase):
    """Логический вывод: цепочки, объяснения, неполнота данных."""

    def setUp(self) -> None:
        self.system = ExpertSystem()

    def test_forward_chaining_derives_intermediate_facts(self) -> None:
        # «нотариус + наследство + запрос» → «нотариальный запрос» → законное исключение
        result = self.system.analyze(
            "Нотариус запросил у банка сведения о вкладах умершего клиента "
            "по наследственному делу, банк предоставил справку.", log=False)
        self.assertEqual(VERDICT_SAFE, result.verdict)
        self.assertTrue(any(c.rule_id == "R-08" for c in result.lawful),
                        "Ожидалось срабатывание правила R-08 (нотариальный запрос)")

    def test_explanation_contains_law_article_and_reason(self) -> None:
        result = self.system.analyze("Сотрудник ФНС передал данные о налоговых платежах "
                                     "компании её конкуренту.", log=False)
        self.assertTrue(result.violations)
        primary = result.violations[0]
        self.assertIn("146-ФЗ", primary.law)
        self.assertIn("102", primary.article)
        self.assertIn("Основания вывода", primary.reason)
        self.assertTrue(primary.matched, "Должны быть перечислены сработавшие условия")

    def test_incomplete_data_asks_questions(self) -> None:
        result = self.system.analyze("Я передал сведения о клиенте.", log=False)
        self.assertIn(result.verdict, (VERDICT_MANUAL, VERDICT_VIOLATION))
        self.assertTrue(result.questions, "Ожидался список уточняющих вопросов")

    def test_low_confidence_is_not_a_verdict(self) -> None:
        result = self.system.analyze(
            "Скидываю тебе базу Пдн наших клиентов, посмотри, может пригодятся для рассылки.",
            log=False)
        self.assertEqual(VERDICT_VIOLATION, result.verdict)
        # слабый признак коммерческой тайны не должен давать жёсткий вывод
        self.assertTrue(all(v.confidence >= 0.7 for v in result.violations))


class TestActions(unittest.TestCase):
    """Рекомендуемые действия: удалить / маскировать / ничего не делать."""

    def setUp(self) -> None:
        self.system = ExpertSystem()

    def test_violation_recommends_delete(self) -> None:
        result = self.system.analyze("Сотрудник ФНС передал данные конкуренту.", log=False)
        self.assertEqual(["удалить"], result.actions)

    def test_lawful_case_recommends_nothing(self) -> None:
        result = self.system.analyze("Клиент дал письменное согласие на передачу его "
                                     "данных третьему лицу.", log=False)
        self.assertEqual(["ничего не делать"], result.actions)

    def test_action_vocabulary_is_limited(self) -> None:
        allowed = {"удалить", "маскировать", "ничего не делать"}
        for case in CASES:
            try:
                result = self.system.analyze(case["text"], log=False)
            except EmptyInputError:
                continue
            self.assertTrue(set(result.actions) <= allowed,
                            "Недопустимое действие в %s: %s" % (case["id"], result.actions))


class TestMasking(unittest.TestCase):
    """Частичное маскирование перед записью в журнал."""

    def test_account_and_phone_are_masked(self) -> None:
        masked = mask_text("Счёт 40817810000001234567, телефон +7 913 555-35-35, "
                           "Иванов И. И.")
        self.assertNotIn("40817810000001234567", masked)
        self.assertIn("4081", masked)
        self.assertNotIn("555-35-35", masked.replace("***-**-35", ""))

    def test_full_text_is_not_stored_verbatim(self) -> None:
        text = ("Клиент Иванов И. И., счёт 42306810500007654321, остаток 500 250,30 руб. "
                "Данные переданы третьему лицу.")
        masked = mask_text(text)
        self.assertNotIn("42306810500007654321", masked)
        self.assertNotIn("500 250,30", masked)

    def test_long_text_is_truncated(self) -> None:
        masked = mask_text("слово " * 200, limit=80)
        self.assertLessEqual(len(masked), 82)


class TestLogging(unittest.TestCase):
    """Журнал инцидентов security_log.txt."""

    def test_incident_is_logged_with_masked_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, "security_log.txt")
            system = ExpertSystem(logger=SecurityLogger(log_path))
            system.analyze("Клиент Иванов И. И. сообщил, что сотрудник передал конкуренту "
                           "данные о налоговых платежах компании без согласия "
                           "налогоплательщика.", source="unittest")
            self.assertTrue(os.path.exists(log_path))
            with open(log_path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("НАРУШЕНИЕ", content)
            self.assertIn("146-ФЗ", content)
            self.assertIn("Ива***", content)
            self.assertNotIn("Иванов И. И. сообщил", content)

    def test_safe_case_is_not_logged_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, "security_log.txt")
            system = ExpertSystem(logger=SecurityLogger(log_path))
            system.analyze("Клиент дал письменное согласие на передачу его данных "
                           "третьему лицу.", source="unittest")
            self.assertFalse(os.path.exists(log_path),
                             "Безопасные случаи не пишутся в журнал без --log-all")

    def test_manual_review_is_logged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, "security_log.txt")
            logger = SecurityLogger(log_path)
            system = ExpertSystem(logger=logger)
            system.analyze("Дружище, я видел, как разворачивают пусковую установку, "
                           "фотку скину.", source="unittest")
            with open(log_path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn(LEVEL_MANUAL, content)

    def test_log_all_writes_safe_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, "security_log.txt")
            system = ExpertSystem(logger=SecurityLogger(log_path, log_safe=True))
            system.analyze("Клиент дал письменное согласие на передачу его данных "
                           "третьему лицу.", source="unittest")
            with open(log_path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("БЕЗОПАСНО", content)


class TestExceptions(unittest.TestCase):
    """Обработка исключений: файл не найден, пустой текст, несколько законов."""

    def test_missing_file(self) -> None:
        with self.assertRaises(InputFileNotFound) as ctx:
            cli.read_text_file("/tmp/definitely-missing-file-lab2.txt")
        self.assertIn("файл не найден", ctx.exception.message.lower())

    def test_file_with_only_spaces(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as handle:
            handle.write("   \n  \n")
            path = handle.name
        try:
            text = cli.read_text_file(path)
            with self.assertRaises(EmptyInputError):
                ExpertSystem().analyze(text, log=False)
        finally:
            os.unlink(path)

    def test_multiple_laws_are_reported_separately(self) -> None:
        result = ExpertSystem().analyze(
            "Сотрудник банка по просьбе конкурента передал сведения о счетах и вкладах "
            "клиента, а также его паспортные данные.", log=False)
        self.assertGreaterEqual(len(result.laws), 2)
        self.assertTrue(any("нескольких федеральных законов" in w for w in result.warnings))

    def test_cli_exit_codes(self) -> None:
        buffer = io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(errors):
            self.assertEqual(2, cli.main(["--text", "Сотрудник ФНС передал данные конкуренту.",
                                          "--no-log", "--no-color"]))
            self.assertEqual(0, cli.main(["--text", "Клиент дал письменное согласие на "
                                                    "передачу его данных третьему лицу.",
                                          "--no-log", "--no-color"]))
            self.assertEqual(3, cli.main(["--text", "Дружище, я видел, как разворачивают "
                                                    "пусковую установку, фотку скину.",
                                          "--no-log", "--no-color"]))
            self.assertEqual(1, cli.main(["--file", "/tmp/no-such-file-42.txt", "--no-log",
                                          "--no-color"]))

    def test_cli_prints_explanation(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["--text", "Врач передал данные о пациенте в полицию по устному запросу.",
                      "--no-log", "--no-color"])
        output = buffer.getvalue()
        self.assertIn("ВЫЯВЛЕННЫЕ НАРУШЕНИЯ", output)
        self.assertIn("323-ФЗ", output)
        self.assertIn("Статья", output)

    def test_cli_json_output(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["--text", "Сотрудник ФНС передал данные конкуренту.", "--json",
                      "--no-log"])
        payload = json.loads(buffer.getvalue())
        self.assertEqual(VERDICT_VIOLATION, payload["verdict"])
        self.assertTrue(payload["violations"])
        self.assertIn("entities", payload)


class TestReportRendering(unittest.TestCase):
    """Содержание текстового отчёта."""

    def test_report_contains_law_article_and_action(self) -> None:
        result = ExpertSystem().analyze("Банк отказал нотариусу в предоставлении данных "
                                        "о счетах умершего клиента.", log=False)
        text = render_result(result, color=False)
        self.assertIn("395-1", text)
        self.assertIn("РЕКОМЕНДУЕМЫЕ ДЕЙСТВИЯ", text)
        self.assertIn("ВЕРДИКТ", text)


class TestApplyAction(unittest.TestCase):
    """Режим --apply: система не только рекомендует действие, но и выполняет его."""

    PDN_TEXT = ("Клиент Иванов И. И., телефон +7 913 555-35-35, "
                "счёт 40817810000001234567.\n\nХранится в общей папке отдела.\n")
    VIOLATION_TEXT = "Сотрудник ФНС передал данные о налоговых платежах компании её конкуренту.\n"
    LAWFUL_TEXT = "Клиент дал письменное согласие на передачу его данных третьему лицу.\n"

    def setUp(self) -> None:
        self.system = ExpertSystem()

    def _write(self, directory: str, name: str, text: str) -> str:
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_delete_replaces_text_with_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "case.txt", self.VIOLATION_TEXT)
            result = self.system.analyze(self.VIOLATION_TEXT, log=False)
            self.assertEqual(["удалить"], result.actions)
            applied = ActionApplier().apply(result, self.VIOLATION_TEXT, source_path=path)
            self.assertTrue(applied.written)
            with open(applied.path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn(DELETE_MARK, content)
            self.assertNotIn("Сотрудник ФНС передал", content)
            self.assertIn("146-ФЗ", content)
            # исходный файл не изменяется без --in-place
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(self.VIOLATION_TEXT, handle.read())

    def test_mask_saves_depersonalized_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "pdn.txt", self.PDN_TEXT)
            result = self.system.analyze(self.PDN_TEXT, log=False)
            self.assertEqual(["маскировать"], result.actions)
            applied = ActionApplier().apply(result, self.PDN_TEXT, source_path=path)
            with open(applied.path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertNotIn("40817810000001234567", content)
            self.assertNotIn("+7 913 555-35-35", content)
            self.assertNotIn("Иванов И. И.", content)
            self.assertIn("4081", content)          # часть номера сохранена
            self.assertIn("Ива***", content)
            self.assertNotIn(DELETE_MARK, content)  # маскирование, а не удаление
            self.assertIn("\n\n", content)          # структура текста сохранена

    def test_nothing_action_writes_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "ok.txt", self.LAWFUL_TEXT)
            result = self.system.analyze(self.LAWFUL_TEXT, log=False)
            self.assertEqual(["ничего не делать"], result.actions)
            applied = ActionApplier().apply(result, self.LAWFUL_TEXT, source_path=path)
            self.assertFalse(applied.written)
            self.assertFalse(os.path.exists(os.path.join(tmp, "ok.applied.txt")))

    def test_in_place_overwrites_and_backs_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "case.txt", self.VIOLATION_TEXT)
            result = self.system.analyze(self.VIOLATION_TEXT, log=False)
            applied = ActionApplier(in_place=True).apply(result, self.VIOLATION_TEXT,
                                                         source_path=path)
            self.assertEqual(path, applied.path)
            self.assertTrue(applied.backup_path and os.path.exists(applied.backup_path))
            with open(path, encoding="utf-8") as handle:
                self.assertIn(DELETE_MARK, handle.read())
            with open(applied.backup_path, encoding="utf-8") as handle:
                self.assertEqual(self.VIOLATION_TEXT, handle.read())

    def test_explicit_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "custom", "result.txt")
            result = self.system.analyze(self.VIOLATION_TEXT, log=False)
            applied = ActionApplier().apply(result, self.VIOLATION_TEXT, out_path=out)
            self.assertEqual(out, applied.path)
            self.assertTrue(os.path.exists(out))

    def test_cli_apply_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "case.txt", self.VIOLATION_TEXT)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["--file", path, "--apply", "--no-log", "--no-color"])
            self.assertEqual(2, code)
            self.assertIn("ПРИМЕНЕНИЕ ДЕЙСТВИЯ", buffer.getvalue())
            self.assertTrue(os.path.exists(os.path.join(tmp, "case.applied.txt")))

    def test_cli_flag_validation(self) -> None:
        errors = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(errors):
            self.assertEqual(1, cli.main(["--text", "текст", "--in-place", "--no-log"]))
            self.assertEqual(1, cli.main(["--text", "текст", "--out", "/tmp/x.txt", "--no-log"]))
        self.assertIn("--in-place", errors.getvalue())

    def test_mask_document_keeps_layout(self) -> None:
        text = "Строка 1: Иванов И. И.\n\nСтрока 2: счёт 40817810000001234567\n"
        masked = mask_document(text)
        self.assertIn("Ива***", masked)
        self.assertIn("4081 **** **** 4567", masked)
        self.assertEqual(text.count("\n"), masked.count("\n"))


class TestActionCoverage(unittest.TestCase):
    """Все три действия из методички должны быть достижимы."""

    def test_rule_base_uses_all_three_actions(self) -> None:
        actions = {rule.action for rule in build_rule_base()}
        self.assertEqual({"удалить", "маскировать", "ничего не делать"}, actions)

    def test_depersonalized_data_is_lawful_and_masked(self) -> None:
        result = ExpertSystem().analyze(
            "Передаю обезличенные данные клиентов для аналитики.", log=False)
        self.assertEqual(VERDICT_SAFE, result.verdict)
        self.assertEqual(["маскировать"], result.actions)
        self.assertTrue(any(c.rule_id == "R-23" for c in result.lawful))

    def test_unknown_category_recommends_precautionary_masking(self) -> None:
        result = ExpertSystem().analyze("Обсудили с коллегой рабочие вопросы.", log=False)
        self.assertEqual(VERDICT_MANUAL, result.verdict)
        self.assertEqual(["маскировать"], result.actions)

    def test_state_secret_requires_deletion(self) -> None:
        result = ExpertSystem().analyze(
            "Дружище, я видел, как разворачивают пусковую установку, фотку скину.", log=False)
        self.assertEqual(["удалить"], result.actions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
