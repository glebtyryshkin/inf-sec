#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Рендер консольного вывода в PNG (скриншот терминальной сессии).

Скрипт используется только для оформления отчёта: он берёт ФАЙЛ с реальным
выводом программы (полученным командой вида ``python main.py ... > out.txt``)
и рисует его как окно терминала.  Содержимое картинки полностью совпадает с
фактическим выводом, ничего не дорисовывается.

Запуск::

    python tools/render_console_png.py --input out.txt --output shot.png \
        --title "python main.py --file samples/case_08_fns_konkurent.txt" \
        [--font-size 15] [--max-lines 60]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

FONT_REGULAR = "/System/Library/Fonts/Menlo.ttc"
FONT_BOLD = "/System/Library/Fonts/Menlo.ttc"
FONT_FALLBACK = "/System/Library/Fonts/Supplemental/Courier New.ttf"

BG = (24, 26, 32)
BAR = (42, 45, 54)
FG = (222, 226, 233)
THEME = {
    "30": (110, 116, 128), "31": (255, 108, 105), "32": (140, 220, 120),
    "33": (240, 200, 90), "34": (120, 170, 255), "35": (220, 140, 255),
    "36": (110, 220, 220), "37": (222, 226, 233), "90": (130, 136, 150),
}

ANSI_RE = re.compile(r"\033\[([0-9;]*)m")


def load_fonts(size: int) -> Tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    try:
        regular = ImageFont.truetype(FONT_REGULAR, size)
        bold = ImageFont.truetype(FONT_BOLD, size)
    except OSError:
        regular = ImageFont.truetype(FONT_FALLBACK, size)
        bold = regular
    return regular, bold


def parse_line(line: str, default_color):
    """Разобрать ANSI-последовательности строки в список (текст, цвет, bold)."""
    spans: List[Tuple[str, Tuple[int, int, int], bool]] = []
    color = default_color
    bold = False
    position = 0
    for match in ANSI_RE.finditer(line):
        if match.start() > position:
            spans.append((line[position:match.start()], color, bold))
        codes = [code for code in match.group(1).split(";") if code]
        for code in codes:
            if code == "0":
                color, bold = default_color, False
            elif code == "1":
                bold = True
            elif code == "2":
                color = THEME["90"]
            elif code in THEME:
                color = THEME[code]
        position = match.end()
    if position < len(line):
        spans.append((line[position:], color, bold))
    return spans or [("", default_color, False)]


def wrap_line(line: str, width: int) -> List[str]:
    """Визуально перенести длинную строку (данные не теряются)."""
    plain = ANSI_RE.sub("", line)
    if width <= 0 or len(plain) <= width:
        return [line]
    out, current = [], ""
    visible = 0
    for chunk in line.split(" "):
        piece = ANSI_RE.sub("", chunk)
        if visible and visible + 1 + len(piece) > width:
            out.append(current)
            current, visible = "      " + chunk, 6 + len(piece)
        else:
            current = (current + " " + chunk) if current else chunk
            visible += (1 if current != chunk else 0) + len(piece)
    if current:
        out.append(current)
    return out


def render(text: str, title: str, font_size: int = 15, padding: int = 22,
           max_lines: int = 0, line_height: int = 0, char_width: int = 0,
           wrap: int = 120, skip_lines: int = 0) -> Image.Image:
    regular, bold = load_fonts(font_size)
    lines = [piece for line in text.replace("\t", "    ").split("\n")
             for piece in wrap_line(line, wrap)]
    lines = [line.rstrip() for line in lines]
    if lines and lines[-1] == "":
        lines = lines[:-1]
    if skip_lines:
        lines = lines[skip_lines:]
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines] + ["… (вывод сокращён)"]

    ascent, descent = regular.getmetrics()
    line_h = line_height or (ascent + descent + 4)
    char_w = char_width or regular.getlength("M")
    width_chars = max([len(ANSI_RE.sub("", line)) for line in lines] + [len(title) + 12, 60])
    win_w = int(char_w * width_chars) + padding * 2
    title_h = 34
    win_h = title_h + padding + line_h * len(lines) + padding

    image = Image.new("RGB", (win_w, win_h), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, win_w, title_h], fill=BAR)

    # «кнопки» окна
    for index, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = 20 + index * 20
        draw.ellipse([cx - 6, title_h // 2 - 6, cx + 6, title_h // 2 + 6], fill=color)
    draw.text((20 + 3 * 20 + 12, title_h // 2 - font_size // 2 - 1), title,
              font=regular, fill=(200, 205, 215))

    y = title_h + padding // 2
    for line in lines:
        x = padding
        for chunk, color, is_bold in parse_line(line, FG):
            if not chunk:
                continue
            draw.text((x, y), chunk, font=(bold if is_bold else regular), fill=color)
            x += regular.getlength(chunk)
        y += line_h
    return image


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Рендер консольного вывода в PNG")
    parser.add_argument("--input", required=True, help="файл с реальным выводом программы")
    parser.add_argument("--output", required=True, help="куда сохранить PNG")
    parser.add_argument("--title", default="Терминал", help="заголовок окна")
    parser.add_argument("--font-size", type=int, default=15)
    parser.add_argument("--max-lines", type=int, default=0,
                        help="обрезать вывод до N строк (0 — без обрезки)")
    parser.add_argument("--wrap", type=int, default=120,
                        help="визуально переносить строки длиннее N символов")
    parser.add_argument("--skip-lines", type=int, default=0,
                        help="пропустить первые N строк (для разбиения длинного вывода)")
    args = parser.parse_args(argv)

    if not os.path.exists(args.input):
        print("Нет файла с выводом: %s" % args.input, file=sys.stderr)
        return 1
    with open(args.input, "r", encoding="utf-8") as handle:
        text = handle.read()
    if not text.strip():
        print("Файл вывода пуст: %s" % args.input, file=sys.stderr)
        return 1
    image = render(text, args.title, font_size=args.font_size,
                   max_lines=args.max_lines, wrap=args.wrap,
                   skip_lines=args.skip_lines)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    image.save(args.output)
    print("%s — %dx%d" % (args.output, image.width, image.height))
    return 0


if __name__ == "__main__":
    sys.exit(main())
