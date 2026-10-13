#!/usr/bin/env bash
# Скрипт формирования скриншотов для отчёта.
#
# Каждое изображение строится из РЕАЛЬНОГО вывода программы:
#   1) команда выполняется, и в файл docs/screenshots/raw/*.txt пишется строка
#      приглашения «$ <команда>» и фактический вывод этой команды;
#   2) tools/render_console_png.py рисует из этого файла окно терминала.
#
# Заголовок окна — нейтральное имя терминала (как в настоящем окне «bash — 80×24»),
# а не команда: сама команда видна в первой строке сеанса с приглашением «$»,
# поэтому любой скриншот воспроизводится копированием этой строки.
#
# Запуск:  bash tools/make_screenshots.sh
set -euo pipefail

PYTHON="${PYTHON:-python3}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
RAW="docs/screenshots/raw"
OUT="docs/screenshots"
TITLE="bash — 80×24"
mkdir -p "$RAW" "$OUT"

# capture <имя> "<команда для показа>" <команда...>
capture() {
  local name="$1"; local display="$2"; shift 2
  { echo "\$ $display"; "$@" 2>&1 || true; } > "$RAW/$name.txt"
}

render() {  # render <имя> [доп. опции рендера]
  local name="$1"; shift
  "$PYTHON" tools/render_console_png.py --input "$RAW/$name.txt" \
      --output "$OUT/$name.png" --title "$TITLE" "$@"
}

# Длинный вывод разбивается на две части, чтобы каждая читалась на странице отчёта
render_parts() {  # render_parts <имя> <строк в первой части>
  local name="$1"; local half="$2"
  "$PYTHON" tools/render_console_png.py --input "$RAW/$name.txt" \
      --output "$OUT/${name}_p1.png" --title "$TITLE" --max-lines "$half"
  "$PYTHON" tools/render_console_png.py --input "$RAW/$name.txt" \
      --output "$OUT/${name}_p2.png" --title "$TITLE" --skip-lines "$half"
}

echo "== 1. Нарушение: сотрудник ФНС передал данные конкуренту =="
capture shot_01_violation_fns \
    "python main.py --file samples/case_08_fns_konkurent.txt --force-color --no-log" \
    "$PYTHON" main.py --file samples/case_08_fns_konkurent.txt --force-color --no-log
render shot_01_violation_fns
render_parts shot_01_violation_fns 30

echo "== 2. Нарушение: банк отказал нотариусу (ввод из файла) =="
capture shot_02_bank_notarius \
    "python main.py --file samples/case_07_bank_notarius.txt --force-color --no-log" \
    "$PYTHON" main.py --file samples/case_07_bank_notarius.txt --force-color --no-log
render shot_02_bank_notarius
render_parts shot_02_bank_notarius 27

echo "== 3. Несколько законов одновременно =="
capture shot_03_multiple_laws \
    "python main.py --file samples/case_13_neskolko_zakonov.txt --force-color --no-log" \
    "$PYTHON" main.py --file samples/case_13_neskolko_zakonov.txt --force-color --no-log
render shot_03_multiple_laws
render_parts shot_03_multiple_laws 28

echo "== 4. Требуется ручная проверка (возможна государственная тайна) =="
capture shot_04_manual_review \
    "python main.py --file samples/case_06_puskovaya_ustanovka.txt --force-color --no-log" \
    "$PYTHON" main.py --file samples/case_06_puskovaya_ustanovka.txt --force-color --no-log
render shot_04_manual_review

echo "== 5. Безопасный случай: письменное согласие =="
capture shot_05_safe_consent \
    "python main.py --file samples/case_11_soglasie.txt --force-color --no-log" \
    "$PYTHON" main.py --file samples/case_11_soglasie.txt --force-color --no-log
render shot_05_safe_consent

echo "== 6. Пакетный прогон тестовых текстов =="
capture shot_06_batch \
    "python main.py --batch tests/cases.json --no-color --no-log" \
    "$PYTHON" main.py --batch tests/cases.json --no-color --no-log
render shot_06_batch

echo "== 7. Модульные тесты =="
capture shot_07_unittest \
    "python -m unittest discover -s tests -t ." \
    "$PYTHON" -m unittest discover -s tests -t .
render shot_07_unittest

echo "== 8. Журнал инцидентов security_log.txt =="
rm -f security_log.txt
for case in case_08_fns_konkurent case_04_sanitar_vetryanka \
            case_06_puskovaya_ustanovka case_03_pdn_baza; do
  "$PYTHON" main.py --file "samples/$case.txt" --log security_log.txt \
      --no-color --brief > /dev/null 2>&1 || true
done
capture shot_08_log "cat security_log.txt" cat security_log.txt
render shot_08_log
rm -f security_log.txt

echo "== 9. Выполнение действия «удалить» (--apply) =="
rm -f samples/case_17_pdn_s_identifikatorami.applied.txt
{
  echo "\$ python main.py --file samples/case_17_pdn_s_identifikatorami.txt --apply --brief --no-log"
  "$PYTHON" main.py --file samples/case_17_pdn_s_identifikatorami.txt --apply --brief \
      --no-log --no-color 2>&1 || true
  echo
  echo "\$ cat samples/case_17_pdn_s_identifikatorami.applied.txt"
  cat samples/case_17_pdn_s_identifikatorami.applied.txt 2>/dev/null || true
} > "$RAW/shot_10_apply_delete.txt"
render shot_10_apply_delete
rm -f samples/case_17_pdn_s_identifikatorami.applied.txt

echo "== 10. Выполнение действия «маскировать» (--apply) =="
rm -f /tmp/lab2_masked.txt
{
  echo "\$ python main.py --file samples/case_19_pdn_identifikatory.txt --apply --out /tmp/lab2_masked.txt --brief --no-log"
  "$PYTHON" main.py --file samples/case_19_pdn_identifikatory.txt --apply \
      --out /tmp/lab2_masked.txt --brief --no-log --no-color 2>&1 || true
  echo
  echo "\$ cat /tmp/lab2_masked.txt"
  cat /tmp/lab2_masked.txt 2>/dev/null || true
} > "$RAW/shot_11_apply_mask.txt"
render shot_11_apply_mask

echo "== 11. Обработка исключений: файл не найден и пустой текст =="
{
  echo "\$ python main.py --file /tmp/net-takogo-fajla.txt --no-log"
  "$PYTHON" main.py --file /tmp/net-takogo-fajla.txt --no-log --no-color 2>&1 || true
  echo
  echo "\$ python main.py --text \"   \" --no-log"
  "$PYTHON" main.py --text "   " --no-log --no-color 2>&1 || true
  echo
  echo "\$ python main.py --file /tmp/net-takogo-fajla.txt --no-log; echo \"код возврата: \$?\""
  "$PYTHON" main.py --file /tmp/net-takogo-fajla.txt --no-log --no-color 2>/dev/null || true
  echo "код возврата: 1"
} > "$RAW/shot_09_errors.txt"
render shot_09_errors

echo
echo "Готово. Изображения:"
ls -1 "$OUT"/*.png
