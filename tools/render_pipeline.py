#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Схема конвейера логического вывода для отчёта (PNG).

Рисует блок-схему: текст → извлечение сущностей → рабочая память → прямой вывод →
объяснение/агрегация → вердикт, действия, журнал.
"""
from __future__ import annotations

import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

REGULAR = "/System/Library/Fonts/Supplemental/Times New Roman.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"

BG = (255, 255, 255)
BOX_BG = (240, 244, 250)
BOX_EDGE = (60, 90, 140)
ACCENT_BG = (232, 245, 233)
ACCENT_EDGE = (46, 125, 50)
ARROW = (90, 100, 115)

STEPS = [
    ("Ввод текста\n(клавиатура / файл)", BOX_BG, BOX_EDGE),
    ("Извлечение сущностей\nонтология + падежные эвристики\n(субъекты, объекты, действия, контекст)", BOX_BG, BOX_EDGE),
    ("Рабочая память\nфакты вида предикат(значение)\nс коэффициентом уверенности", BOX_BG, BOX_EDGE),
    ("Прямой логический вывод\nправила применяются до неподвижной\nточки (26 правил базы знаний)", BOX_BG, BOX_EDGE),
    ("Объяснение и агрегация\nзакон, статья, цепочка условий;\nконфликты, неполнота данных", BOX_BG, BOX_EDGE),
    ("Вердикт, рекомендуемые действия,\nжурнал security_log.txt", ACCENT_BG, ACCENT_EDGE),
]


def render(width: int = 1500) -> Image.Image:
    regular = ImageFont.truetype(REGULAR, 26)
    bold = ImageFont.truetype(BOLD, 28)
    box_w = int(width * 0.62)
    box_h = 118
    gap = 54
    margin_x = (width - box_w) // 2
    top = 40
    note_h = 128
    height = top + len(STEPS) * box_h + (len(STEPS) - 1) * gap + note_h + 30
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)

    y = top
    for index, (text, fill, edge) in enumerate(STEPS):
        draw.rounded_rectangle([margin_x, y, margin_x + box_w, y + box_h],
                               radius=16, fill=fill, outline=edge, width=3)
        lines = text.split("\n")
        total = len(lines) * 34
        ty = y + (box_h - total) // 2
        for line_index, line in enumerate(lines):
            font = bold if (line_index == 0 and len(lines) > 1) else regular
            tw = draw.textlength(line, font=font)
            draw.text((margin_x + (box_w - tw) / 2, ty), line, font=font,
                      fill=(25, 30, 40))
            ty += 34
        if index < len(STEPS) - 1:
            cx = width // 2
            draw.line([cx, y + box_h, cx, y + box_h + gap], fill=ARROW, width=4)
            draw.polygon([(cx - 11, y + box_h + gap - 14), (cx + 11, y + box_h + gap - 14),
                          (cx, y + box_h + gap)], fill=ARROW)
        y += box_h + gap

    # боковая сноска про обратную связь (новые факты включают другие правила)
    note_font = ImageFont.truetype(REGULAR, 22)
    note = "Сработавшее правило добавляет\nновые факты — они включают\nследующие правила (цепочка вывода)"
    note_lines = note.split("\n")
    nx, ny = margin_x, height - note_h - 10
    draw.rounded_rectangle([nx, ny, nx + box_w, ny + note_h - 10], radius=12,
                           fill=(255, 249, 230), outline=(190, 150, 40), width=2)
    for i, line in enumerate(note_lines):
        text_width = draw.textlength(line, font=note_font)
        draw.text((nx + (box_w - text_width) / 2, ny + 18 + i * 32), line,
                  font=note_font, fill=(90, 70, 20))
    return image


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Схема конвейера вывода (PNG)")
    parser.add_argument("--output", default="docs/screenshots/scheme_pipeline.png")
    parser.add_argument("--width", type=int, default=1500)
    args = parser.parse_args(argv)
    image = render(args.width)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    image.save(args.output)
    print("%s — %dx%d" % (args.output, image.width, image.height))
    return 0


if __name__ == "__main__":
    sys.exit(main())
