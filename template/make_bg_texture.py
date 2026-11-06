#!/usr/bin/env python3
"""Генерирует НАБОР декоративных фонов-паспарту для frame_clips.py (не один
паттерн на весь ролик — фон должен "гулять" по ходу видео, см. SKILL.md
"6c"). Каждый фон — PNG больше 1920x1080 (есть куда панорамировать).

2026-10-07: первая версия (один чёрно-белый шахматный паттерн, жёсткий
контраст C1=(230,226,216)/C2=(60,56,50)) пользователь оценил как "режет
глаз" ДО того, как сравнил с реальными видео-задниками конкурента — та
версия оставлена как PATTERN_CHECKER ниже, но с смягчённым контрастом
(C1/C2 сближены). Добавлены ещё 3 паттерна того же мягкого тона, чтобы
было из чего чередовать. Это НЕ замена реальных видео-задников (клетка.mp4
и т.п. из медиатеки конкурента, см. SKILL.md) — та опция остаётся лучшей,
когда пользователь пришлёт файлы в свою библиотеку script-to-video; эти
PNG — рабочий дефолт, пока их нет.

Usage:
  python3 make_bg_texture.py <out_dir> [square_px]
  -> пишет out_dir/bg_checker.png, bg_stripes.png, bg_dots.png, bg_paper.png
"""
import os
import random
import sys
from PIL import Image, ImageDraw, ImageFilter

W, H = 2600, 1500
# смягчённый тон вместо чёрно-белого: тёплый пергамент / тёмный графит,
# контраст заметно ниже прежнего (user, 2026-10-06: "смягчить тона")
C1 = (223, 216, 200)   # тёплый пергамент
C2 = (104, 96, 84)     # тёплый тёмно-серый (не чёрный)


def _grain(im, seed, amount=10):
    random.seed(seed)
    px = im.load()
    for _ in range(W * H // 22):
        x, y = random.randrange(W), random.randrange(H)
        r, g, b = px[x, y]
        n = random.randint(-amount, amount)
        px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))


def pattern_checker(sq=72):
    im = Image.new("RGB", (W, H), C1)
    d = ImageDraw.Draw(im)
    for y in range(0, H, sq):
        for x in range(0, W, sq):
            if ((x // sq) + (y // sq)) % 2 == 0:
                d.rectangle((x, y, x + sq, y + sq), fill=C2)
    _grain(im, 7)
    return im


def pattern_stripes(w=64, angle_step=1):
    im = Image.new("RGB", (W, H), C1)
    d = ImageDraw.Draw(im)
    # диагональные полосы — другой ритм, чем клетка, чтобы отличаться на глаз
    for i in range(-H, W, w * 2):
        d.polygon([(i, 0), (i + w, 0), (i + w - H, H), (i - H, H)], fill=C2)
    _grain(im, 11)
    return im.filter(ImageFilter.GaussianBlur(0.6))  # чуть смягчить края полос


def pattern_dots(gap=58, r=16):
    im = Image.new("RGB", (W, H), C1)
    d = ImageDraw.Draw(im)
    for y in range(0, H + gap, gap):
        off = (gap // 2) if (y // gap) % 2 else 0
        for x in range(-off, W + gap, gap):
            d.ellipse((x - r, y - r, x + r, y + r), fill=C2)
    _grain(im, 13)
    return im


def pattern_paper(seed=17):
    """Мятая бумага — только текстура/шум, без геометрии, для контраста с
    тремя геометрическими паттернами выше (референс-канал тоже чередует
    геометрию и "бумагу", см. SKILL.md)."""
    im = Image.new("RGB", (W, H), tuple(int(c * 0.92 + C1[i] * 0.08) for i, c in enumerate(C1)))
    _grain(im, seed, amount=16)
    im = im.filter(ImageFilter.GaussianBlur(1.2))
    _grain(im, seed + 1, amount=8)
    return im


PATTERNS = {
    "bg_checker.png": pattern_checker,
    "bg_stripes.png": pattern_stripes,
    "bg_dots.png": pattern_dots,
    "bg_paper.png": pattern_paper,
}


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out_dir, exist_ok=True)
    for name, fn in PATTERNS.items():
        fn().save(os.path.join(out_dir, name))
        print("ok ->", os.path.join(out_dir, name))


if __name__ == "__main__":
    main()
