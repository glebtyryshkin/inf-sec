#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI экспертной системы анализа конфиденциальности.

Примеры запуска::

    python main.py                                  # ввод с клавиатуры
    python main.py --text "Врач передал диагноз соседу"
    python main.py --file samples/case_01.txt
    python main.py --batch tests/cases.json         # прогон набора тестов
    python main.py --demo                           # 10 примеров из задания
    python main.py --file case.txt --json           # машиночитаемый вывод

Коды возврата:

* 0 — нарушений не выявлено;
* 1 — ошибка ввода-вывода (файл не найден, пустой текст и т.п.);
* 2 — выявлено нарушение;
* 3 — требуется ручная проверка.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from privacy_expert import (ACTION_NONE, EXIT_ERROR, ActionApplier, ExpertSystem,
                            SecurityLogger, __version__, render_result)
from privacy_expert.errors import ExpertSystemError, InputFileNotFound
from privacy_expert.engine import VERDICT_MANUAL, VERDICT_SAFE, VERDICT_VIOLATION

DEFAULT_LOG = "security_log.txt"
ENCODINGS = ("utf-8", "utf-8-sig", "cp1251")


# ---------------------------------------------------------------------------
# Ввод
# ---------------------------------------------------------------------------
def read_text_file(path: str) -> str:
    """Прочитать текст из файла, перебирая поддерживаемые кодировки."""
    if not os.path.exists(path):
        raise InputFileNotFound(path)
    if os.path.isdir(path):
        raise ExpertSystemError("Ошибка ввода: %s — это каталог, а не файл." % path,
                                "укажите путь к текстовому файлу.")
    last_error: Optional[Exception] = None
    for encoding in ENCODINGS:
        try:
            with open(path, "r", encoding=encoding) as handle:
                return handle.read()
        except UnicodeDecodeError as error:  # пробуем следующую кодировку
            last_error = error
        except OSError as error:
            raise ExpertSystemError("Ошибка чтения файла %s: %s" % (path, error))
    from privacy_expert.errors import EncodingError
    raise EncodingError(path, ", ".join(ENCODINGS))


def read_interactive() -> str:
    """Многострочный ввод с клавиатуры (завершение — строка ``/end``)."""
    print("Введите текст для анализа. Для завершения введите /end в отдельной строке.")
    print("-" * 60)
    lines: List[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() in ("/end", "/конец"):
            break
        lines.append(line)
    print("-" * 60)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Печать
# ---------------------------------------------------------------------------
def print_result(result, color: bool, explain: bool, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_result(result, color=color, explain=explain))


def print_application(applied, color: bool, as_json: bool) -> None:
    """Показать, что именно сделала программа в режиме --apply."""
    if as_json:
        print(json.dumps({"applied": applied.as_dict()}, ensure_ascii=False, indent=2))
        return
    def paint(text, code):
        return "\033[%sm%s\033[0m" % (code, text) if color else text
    print()
    print(paint("ПРИМЕНЕНИЕ ДЕЙСТВИЯ", "1"))
    print("  Действие : %s" % applied.action)
    print("  Результат: %s" % applied.note)
    if applied.written and applied.path:
        print("  Файл     : %s (%d байт)" % (applied.path, applied.bytes_written))
    if applied.backup_path:
        print("  Резервная копия: %s" % applied.backup_path)


def print_error(error: ExpertSystemError) -> None:
    print("\n[ОШИБКА] " + error.user_message(), file=sys.stderr)


# ---------------------------------------------------------------------------
# Режимы
# ---------------------------------------------------------------------------
def run_batch(system: ExpertSystem, path: str, color: bool, explain: bool,
              as_json: bool) -> int:
    """Прогон набора тестовых текстов с проверкой ожиданий."""
    if not os.path.exists(path):
        raise InputFileNotFound(path)
    with open(path, "r", encoding="utf-8") as handle:
        cases = json.load(handle)

    passed = 0
    rows: List[Dict[str, object]] = []
    for case in cases:
        expected_laws = case.get("expected_laws", [])
        expected_verdict = case.get("expected_verdict", "")
        try:
            result = system.analyze(case["text"], source="test:%s" % case.get("id", "?"))
        except ExpertSystemError as error:
            ok = expected_verdict == "ОШИБКА"
            passed += 1 if ok else 0
            rows.append({
                "id": case.get("id"), "ok": ok, "verdict": "ОШИБКА (обработана)",
                "laws": [], "primary": error.message.split(":")[0],
                "questions": 0, "expected_verdict": expected_verdict,
                "expected_laws": expected_laws,
            })
            if not as_json:
                print("[%s] %-8s %-32s %s" % ("PASS" if ok else "FAIL", case.get("id", "?"),
                                              "ОШИБКА (обработана)", error.message[:48]))
            continue
        laws_ok = all(any(law in (c.law + " " + c.article) for c in result.violations)
                      for law in expected_laws)
        verdict_ok = (not expected_verdict) or result.verdict == expected_verdict
        ok = laws_ok and verdict_ok
        passed += 1 if ok else 0
        rows.append({
            "id": case.get("id"),
            "ok": ok,
            "verdict": result.verdict,
            "laws": result.laws,
            "primary": result.violations[0].article if result.violations else "—",
            "questions": len(result.questions),
            "expected_verdict": expected_verdict,
            "expected_laws": expected_laws,
        })
        if not as_json:
            mark = "PASS" if ok else "FAIL"
            print("[%s] %-8s %-32s %s" % (mark, case.get("id", "?"), result.verdict,
                                          ", ".join(result.laws) or "—"))

    summary = {"total": len(cases), "passed": passed, "failed": len(cases) - passed,
               "rows": rows}
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("-" * 72)
        print("ИТОГО: %d из %d тестов пройдено (%d ошибок)"
              % (passed, len(cases), len(cases) - passed))
        failed = [row for row in rows if not row["ok"]]
        for row in failed:
            print("  FAIL %s: получено «%s» %s, ожидалось «%s» %s"
                  % (row["id"], row["verdict"], row["laws"], row["expected_verdict"],
                     row["expected_laws"]))
    return 0 if passed == len(cases) else 1


def run_demo(system: ExpertSystem, color: bool, explain: bool, as_json: bool) -> int:
    """Демонстрация: 10 сложных текстов из задания."""
    cases_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "cases.json")
    if not os.path.exists(cases_path):
        raise InputFileNotFound(cases_path)
    with open(cases_path, "r", encoding="utf-8") as handle:
        cases = json.load(handle)
    demo = [case for case in cases if case.get("demo", True)]
    worst = 0
    for index, case in enumerate(demo, start=1):
        print("\n" + "#" * 78)
        print("# ПРИМЕР %d/%d — %s" % (index, len(demo), case.get("title", case.get("id"))))
        print("# Ожидание: %s" % case.get("expectation", "—"))
        print("#" * 78)
        result = system.analyze(case["text"], source="demo:%s" % case.get("id", index))
        print_result(result, color, explain, as_json)
        worst = max(worst, result.exit_code if result.exit_code != EXIT_ERROR else 0)
    return 0


# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="privacy-expert",
        description="Экспертная система анализа конфиденциальности: логический вывод "
                    "о наличии нарушения законодательства РФ (98-ФЗ, 146-ФЗ, 152-ФЗ, "
                    "395-1-ФЗ, 323-ФЗ, УК РФ, КоАП РФ).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Коды возврата: 0 — нарушений нет, 1 — ошибка ввода, 2 — нарушение, "
               "3 — требуется ручная проверка.")
    parser.add_argument("--file", "-f", help="прочитать анализируемый текст из файла")
    parser.add_argument("--text", "-t", help="передать текст одной строкой")
    parser.add_argument("--batch", "-b", help="прогнать набор тестовых текстов из JSON")
    parser.add_argument("--demo", action="store_true", help="показать 10 примеров из задания")
    parser.add_argument("--json", action="store_true", help="вывести результат в формате JSON")
    parser.add_argument("--log", default=DEFAULT_LOG, help="путь к журналу (по умолчанию %s)"
                                                           % DEFAULT_LOG)
    parser.add_argument("--no-log", action="store_true", help="не писать журнал инцидентов")
    parser.add_argument("--log-all", action="store_true",
                        help="писать в журнал и безопасные случаи")
    parser.add_argument("--no-color", action="store_true", help="отключить цветной вывод")
    parser.add_argument("--force-color", action="store_true",
                        help="включить цветной вывод даже при перенаправлении в файл")
    parser.add_argument("--brief", action="store_true", help="без подробных объяснений")
    parser.add_argument("--apply", action="store_true",
                        help="выполнить рекомендованное действие: «удалить» — заменить текст "
                             "пометкой [удалено], «маскировать» — сохранить маскированную копию")
    parser.add_argument("--out", help="куда записать результат действия (по умолчанию "
                                      "<имя файла>.applied.<расширение>)")
    parser.add_argument("--in-place", action="store_true",
                        help="перезаписать исходный файл (только вместе с --file; создаётся "
                             "резервная копия .bak)")
    parser.add_argument("--no-backup", action="store_true",
                        help="не создавать резервную копию при --in-place")
    parser.add_argument("--no-header", action="store_true",
                        help="не добавлять служебную шапку с причиной обработки")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    color = (not args.no_color) and (sys.stdout.isatty() or args.force_color)

    if args.in_place and not args.file:
        print("[ОШИБКА] Флаг --in-place применим только вместе с --file: перезаписывать "
              "нечего.", file=sys.stderr)
        return EXIT_ERROR
    if args.out and not args.apply:
        print("[ОШИБКА] Флаг --out имеет смысл только вместе с --apply.", file=sys.stderr)
        return EXIT_ERROR

    logger = SecurityLogger(args.log, enabled=not args.no_log, log_safe=args.log_all)
    system = ExpertSystem(logger=logger)

    try:
        if args.batch:
            return run_batch(system, args.batch, color, not args.brief, args.json)
        if args.demo:
            return run_demo(system, color, not args.brief, args.json)
        if args.file:
            text, source = read_text_file(args.file), "file:%s" % args.file
        elif args.text:
            text, source = args.text, "cli:--text"
        else:
            text, source = read_interactive(), "cli:stdin"
        result = system.analyze(text, source=source)
        print_result(result, color, not args.brief, args.json)

        if args.apply:
            applier = ActionApplier(in_place=args.in_place, header=not args.no_header,
                                    backup=not args.no_backup)
            applied = applier.apply(result, text, out_path=args.out,
                                    source_path=args.file)
            print_application(applied, color, args.json)
        return result.exit_code
    except ExpertSystemError as error:
        print_error(error)
        return error.exit_code or EXIT_ERROR
    except KeyboardInterrupt:
        print("\nПрервано пользователем.", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
