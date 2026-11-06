#!/usr/bin/env python3
"""Единый генератор субтитров и "динамических вставок" (акцентные
заголовки, термометр-индикатор, кружки-сравнение) — всё по одному
JSON-конфигу, блоки включаются/выключаются независимо.

Собрано 2026-10-05 на тесте про льва (документальный формат): пользователю
нравятся — верхние акцентные заголовки с подчёркиванием, кружки-сравнение
по краям кадра, попапы-иллюстрации (те — через build_overlays.py отдельно).

ВАЖНО про субтитры: если видео склеено через xfade_assemble.py (клипы уже
удлинены extend_for_xfade.py), тайминги субтитров тут берутся ПРЯМО из SRT
без коррекции — это специально, коррекция после xfade была ошибкой сессии
2026-10-05 (см. xfade_assemble.py докстринг).

Usage:
  python3 build_dynamics.py <config.json> <out.ass> [out_compare.png]
                            [--burn <in.mp4> <out.mp4>]

config.json:
{
  "srt": "caption.srt",                 // для блока captions
  "width": 1920, "height": 1080,        // опционально, дефолт 1920x1080
  "blocks": {
    "captions": true,                   // true = обычные подписи снизу из srt
    "accents": [                        // список акцентных заголовков
      {"start": 10.2, "end": 13.4, "text": "1990-Е · СЕРЕНГЕТИ"}
    ],
    "quotes": [                         // цитата-плашка: спокойное всплытие
      {"start": 108.5, "end": 116.5,    // снизу-центра, кавычки, serif-италик —
       "text": "Чем темнее грива, тем выше тестостерон",  // для сильных выводов
       "author": ""}                    // сюжета, НЕ для дат/цифр (те — accents)
    ],
    "labels": [                         // короткая подпись-наименование сбоку
      {"start": 14.0, "end": 19.0, "text": "ТЁМНАЯ ГРИВА", "side": "left"}
    ],                                  // называет то, что уже видно в кадре
    "thermometer": {                    // наливающийся/краснеющий индикатор
      "start": 36.9, "end": 43.7, "label": "ТЕМПЕРАТУРА"
    },
    "comparison": {                     // кружки слева/справа + анимированные буквы
      "start": 20.0, "end": 33.3,
      "left":  {"photo": "a.jpg", "label": "ТЁМНАЯ ГРИВА",  "detail": "выше тестостерон\nхуже переносит жару", "color": "FF5A5A"},
      "right": {"photo": "b.jpg", "label": "СВЕТЛАЯ ГРИВА", "detail": "легче охотится\nменьше статус",         "color": "FFD250"}
    }
  }
}

"comparison.left/right.photo" — если задано, скрипт ТАКЖЕ рендерит PNG с
кружками: сами фотографии в субтитровый слой не поместить, туда идут только
подписи и кольца. Раньше PNG надо было накладывать РУКАМИ отдельным
ffmpeg-проходом, и если этого не сделать — на экране оставались пустые
кольца (в арсенале это значилось как «кружки требуют второго прохода»).
С 20.10.2026 скрипт делает проход САМ: добавьте `--burn <in.mp4> <out.mp4>`,
и на выходе будет готовое видео с субтитрами, накладками и кружками. Окно
показа кружков пишется рядом в `<out.ass>.compare.json` — на случай, если
наложение всё-таки делается чужим конвейером.

2026-10-07: каждый экземпляр accents/quotes/labels теперь визуально
отличается от соседних того же типа (шрифт/цвет линии-акцента чередуются
по индексу) — см. SKILL.md "6c", пункт про шаблонность. `build_labels`
также анимирует текст ПОБУКВЕННО (bounce, тот же паттерн, что у кружков-
сравнения), а не целым блоком через fad. Скрипт ДОПОЛНИТЕЛЬНО пишет
`<out_ass>.sfx.json` — список {"at", "role"} на каждый триггер — читает
`build_sfx_track.py`, который сводит это в звуковую дорожку с РАЗНЫМИ
звуками по типу (whoosh/pop/ding/zatvor из библиотеки пользователя, не
один sfx на всё).
"""
import json
import os
import re
import sys


# ---------- время ----------

def ass_time(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    cs = round(s * 100)
    if cs >= 6000:
        cs -= 6000; m += 1
    return f"{h:01d}:{m:02d}:{cs//100:02d}.{cs%100:02d}"


def parse_srt(path):
    cues = []
    blocks = open(path, encoding="utf-8-sig").read().strip().split("\n\n")
    for b in blocks:
        lines = b.strip().split("\n")
        if len(lines) < 2:
            continue
        m = re.search(r"(\d\d):(\d\d):(\d\d),(\d+)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d+)", lines[1])
        if not m:
            continue
        text = " ".join(x.strip() for x in lines[2:]).strip()
        st = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000
        en = int(m.group(5)) * 3600 + int(m.group(6)) * 60 + int(m.group(7)) + int(m.group(8)) / 1000
        cues.append([st, en, text])
    return cues


# ---------- блок: обычные подписи ----------

def build_captions(srt_path):
    cues = parse_srt(srt_path)
    groups, cur = [], None
    for st, en, tx in cues:
        if cur is None:
            cur = [st, en, tx]
        else:
            cur[1] = en
            cur[2] = (cur[2] + " " + tx).strip()
        dur = cur[1] - cur[0]
        if dur >= 2.6 or len(cur[2]) >= 38:
            groups.append(cur)
            cur = None
    if cur:
        groups.append(cur)
    # защита: границы фраз из живого SRT и так монотонны, но если SRT
    # редактировали руками и где-то слепили внахлёст — не даём ASS мигать
    for i in range(1, len(groups)):
        if groups[i][0] < groups[i - 1][1]:
            shift = groups[i - 1][1] - groups[i][0]
            groups[i][0] += shift
            groups[i][1] += shift

    lines = []
    for st, en, tx in groups:
        lines.append(f"Dialogue: 0,{ass_time(st)},{ass_time(en)},Caption,,0,0,0,,{tx.strip().upper()}")
    return lines


# ---------- блок: акцентные заголовки (наезд+масштаб, не просто fade) ----------

# 2026-10-07: переписан с нуля — целая строка, просто вылетающая
# scale-поп'ом, читалась как "примитивное говно" (user, дословно: "буквы
# красивые шрифты красивые цвета красивые линии красивые эффекты красивые
# блин всегда динамика"). Теперь буквы выскакивают по одной (тот же
# bounce-паттерн, что у лейблов/сравнения — не изобретаем четвёртый вид
# анимации), нарядный Playfair Display с мягким свечением вместо
# Arial Black, подчёркивание "дорисовывается" слева направо, а не просто
# схлопывается по центру. Цвета — тёплая новогодняя палитра (золото/
# тёплый красный/кремовый), не произвольный teal из документалки про льва.
# ---------- палитра и шрифты, общие с дашбордом (2026-10-17) ----------
# Ровно те же пять цветов и шесть шрифтов, что кнопками в обычном дашборде
# всплывашек (review.py: TEXT_COLORS / TEXT_FONTS, файлы в
# news-video/template/fonts). Нажатая кнопка должна означать то же самое в
# кадре, иначе дашборд врёт. Ключ не задан — работает прежнее чередование
# цветов/шрифтов по индексу, вид роликов не меняется.
PALETTE_BGR = {"white": "FFFFFF", "yellow": "00E8FF", "red": "1C22FF",
               "green": "5ED62E", "orange": "0A92FF"}
_NV_FONT_DIR = "/home/andrey/.claude/skills/news-video/template/fonts"
FONT_FAMILY = {"default": "", "arial": "Arimo", "times": "Tinos",
               "oswald": "Oswald", "montserrat": "Montserrat",
               "roboto": "Roboto Condensed"}
FONT_FILE = {"arial": _NV_FONT_DIR + "/Arimo-Bold.ttf",
             "times": _NV_FONT_DIR + "/Tinos-Bold.ttf",
             "oswald": _NV_FONT_DIR + "/Oswald-Bold.ttf",
             "montserrat": _NV_FONT_DIR + "/Montserrat-Bold.ttf",
             "roboto": _NV_FONT_DIR + "/RobotoCondensed-Bold.ttf"}


def _ckey(spec):
    return str(spec.get("color", "") or "").lower()


def _col(spec, default_bgr):
    """Цвет элемента из палитры дашборда; нет ключа — прежний цвет."""
    return PALETTE_BGR.get(_ckey(spec), default_bgr)


def _fnt(spec, default_tag=""):
    key = str(spec.get("font", "") or "").lower()
    if key not in FONT_FAMILY:
        return default_tag
    fam = FONT_FAMILY[key]
    return f"\\fn{fam}" if fam else ""


def _measure_font(spec, size, default_path):
    """PIL-шрифт для измерения ширины. Обязан совпадать с тем, которым
    рисует ASS, иначе побуквенная раскладка расползётся."""
    from PIL import ImageFont
    path = FONT_FILE.get(str(spec.get("font", "") or "").lower(), default_path)
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(default_path, size)


_ACCENT_GLOW_COLORS = ["D9A441", "C0392B", "EDC9A0"]   # золото / тёплый красный / кремовый
_ACCENT_CHAR_STAGGER = 0.035


def build_accents(accents, sfx=None):
    FADE_OUT = 220
    _PLAYFAIR = ("/home/andrey/.claude/skills/script-to-video/template/fonts/"
                 "PlayfairDisplay-Regular.ttf")
    lines = []
    for i, a in enumerate(accents):
        st, en, text = a["start"], a["end"], a["text"]
        glow = _col(a, _ACCENT_GLOW_COLORS[i % len(_ACCENT_GLOW_COLORS)])
        txt_col = glow if _ckey(a) in PALETTE_BGR else "FFFFFF"
        fn = _fnt(a, "\\fnPlayfair Display")
        font = _measure_font(a, 72, _PLAYFAIR)
        total_w = font.getlength(text)
        start_x = 960 - total_w / 2
        char_y = 118
        x = start_x
        for j, ch in enumerate(text):
            w = font.getlength(ch)
            if ch != " ":
                cst = st + j * _ACCENT_CHAR_STAGGER
                lines.append(
                    f"Dialogue: 1,{ass_time(cst)},{ass_time(en)},Accent,,0,0,0,,"
                    f"{{{fn}\\b1\\fs72\\an7\\pos({x:.0f},{char_y})\\c&H{txt_col}&"
                    f"\\3c&H{glow}&\\4c&H{glow}&\\bord1.4\\blur3\\fad(10,{FADE_OUT})"
                    f"\\t(0,110,\\fscy135\\fscx135)\\t(110,210,\\fscy92\\fscx92)"
                    f"\\t(210,260,\\fscy100\\fscx100)}}{ch}"
                )
            x += w
        # подчёркивание "дорисовывается" слева направо (не схлопывается по центру)
        bar_w, bar_h = min(total_w + 20, 620), 6
        bx0 = 960 - bar_w / 2
        dur_ms = int((en - st) * 1000)
        draw_ms = min(380, dur_ms // 3)
        lines.append(
            f"Dialogue: 1,{ass_time(st)},{ass_time(en)},Bar,,0,0,0,,"
            f"{{\\an4\\pos({bx0:.0f},206)\\1c&H{glow}&\\p1\\fad(0,{FADE_OUT})"
            f"\\t(0,{draw_ms},\\fscx100)}}m 0 0 l {bar_w:.0f} 0 {bar_w:.0f} {bar_h} 0 {bar_h}{{\\p0}}"
        )
        if sfx is not None:
            sfx.append({"at": st, "role": "accent"})
    return lines


# ---------- блок: цитата-плашка (серьёзный вывод из сюжета, не просто факт) ----------
# Отдельно от accents: тот — быстрый наезд+масштаб для дат/цифр сверху кадра;
# цитата — спокойное всплытие снизу-центра, кавычки, serif-италик, держится
# дольше. Нужен отдельный визуальный язык, чтобы не все вставки выглядели
# одинаково ("побогаче", user 2026-10-06).

def _plate(st, en, bx0, by0, bw, bh, fi, fo, box, accent, near_left=True):
    """Подложка элемента. Видов пять, потому что чёрная полупрозрачная
    плашка с ушком читалась как траурная рамка (user, 2026-10-17:
    "такое впечатление, что эпитафия"):
      plate  — как было: тёмная заливка + цветное ушко;
      bare   — без заливки вообще, только цветная черта под текстом;
      line   — толстая цветная черта у ближнего края, заливки нет;
      solid  — заливка САМИМ акцентным цветом (текст тёмный) — светло;
      fade   — тёмная заливка, тающая в прозрачность к дальнему краю.
    """
    o = []
    def shape(x, y, w, h, col, alpha=None):
        a = f"\\alpha&H{alpha}&" if alpha else ""
        o.append(f"Dialogue: 2,{ass_time(st)},{ass_time(en)},Bar,,0,0,0,,"
                 f"{{\\an7\\pos({x:.0f},{y:.0f})\\fad({fi},{fo})"
                 f"\\1c&H{col}&{a}\\p1}}m 0 0 l {w:.0f} 0 {w:.0f} {h:.0f} 0 {h:.0f}")
    if box == "plate":
        shape(bx0, by0, bw, bh, INK_BGR, "58")
        shape(bx0 if near_left else bx0 + bw - 8, by0, 8, bh, accent)
    elif box == "line":
        shape(bx0 if near_left else bx0 + bw - 9, by0, 9, bh, accent)
    elif box == "solid":
        # на широкой плашке (цитата) та же заливка читается как глухой блок —
        # разводим сильнее по ширине
        shape(bx0, by0, bw, bh, accent, "96" if bw > 1000 else "6E")
    elif box == "fade":
        n = 9
        for k in range(n):
            frac = k / n if near_left else (n - 1 - k) / n
            al = int(0x40 + (0xF0 - 0x40) * frac)
            shape(bx0 + bw * k / n, by0, bw / n + 1, bh, INK_BGR, f"{al:02X}")
        shape(bx0 if near_left else bx0 + bw - 8, by0, 8, bh, accent)
    # "bare" — ничего не рисуем, текст живёт на обводке
    return o


GOLD_BGR = "61A2C4"   # (196,162,97) RGB -> BGR hex для \1c
INK_BGR = "0E1214"    # (20,18,20)-ish тёмная подложка


_QUOTE_LINE_COLORS = [GOLD_BGR, "3DC7F2"]      # золото / тил — чередуем верхнюю линию
_QUOTE_FONTS = ["", ""]   # одна шрифтовая роль на весь ролик: курсив снят 2026-10-18


def build_quotes(quotes, sfx=None):
    """Полноценная карточка-плашка, не голый текст: полупрозрачная тёмная
    подложка на всю ширину блока, тонкая золотая линия сверху, крупный
    курсив по центру. Поднята над нижней третью кадра — там зона будущих
    субтитров, класть туда что-то ещё нельзя (user, 2026-10-06, жёсткая
    жалоба на цитату, которая и мелкая, и топталась по зоне субтитров)."""
    FADE_IN, FADE_OUT = 340, 280
    lines = []
    for i, q in enumerate(quotes):
        st, en, text, author = q["start"], q["end"], q["text"], q.get("author", "")
        y = q.get("y", 480)  # верхняя половина кадра, подальше от будущих субтитров
        # Длинную цитату ломаем пополам по пробелу: одной строкой на 1560 px
        # она вытягивается в тонкую ленту и читается мельче, чем есть.
        if "\n" not in text and len(text) > 46:
            ws = text.split(" ")
            best, bw = None, None
            for k in range(1, len(ws)):
                a, b = " ".join(ws[:k]), " ".join(ws[k:])
                w = max(len(a), len(b))
                if bw is None or w < bw:
                    best, bw = a + "\n" + b, w
            text = best
        nl = text.count("\n")
        esc = text.replace("\n", "\\N")
        box_w = 1560
        box_h = (190 if author else 150) + nl * 74
        bx0 = 960 - box_w / 2
        by0 = y - box_h / 2
        line_col = _col(q, _QUOTE_LINE_COLORS[i % len(_QUOTE_LINE_COLORS)])
        fn = _fnt(q, _QUOTE_FONTS[i % len(_QUOTE_FONTS)])
        q_txt = f"\\c&H{line_col}&" if _ckey(q) in PALETTE_BGR else ""

        box = q.get("box", "plate")
        anim = q.get("anim", "fade")   # 2026-10-18: прыжки букв сняты вместе с игровым языком
        lines += _plate(st, en, bx0, by0, box_w, box_h, FADE_IN, FADE_OUT,
                        box, line_col, True)
        # тонкая цветная линия над цитатой — остаётся при любой подложке
        lines.append(
            f"Dialogue: 2,{ass_time(st)},{ass_time(en)},Bar,,0,0,0,,"
            f"{{\\an7\\pos({bx0 + box_w/2 - 110:.0f},{by0 - 4:.0f})\\fad({FADE_IN},{FADE_OUT})"
            f"\\1c&H{line_col}&\\p1}}m 0 0 l 220 0 220 3 0 3"
        )
        txt_col = line_col if _ckey(q) in PALETTE_BGR else "EDE8DE"
        edge = "\\bord3.2\\3c&H0A0C0E&\\shad1" if box in ("bare", "line") else ""
        if anim == "chars":
            # Буквы выпрыгивают по одной, тем же bounce'ом, что у подписей и
            # кружков: "чтобы буквы как бы плясали" (user, 2026-10-17).
            from PIL import ImageFont
            QF = 70
            _PF = ("/home/andrey/.claude/skills/script-to-video/template/"
                   "../../news-video/template/fonts/RobotoCondensed-Bold.ttf")
            try:
                qfont = ImageFont.truetype(_PF, QF)
            except OSError:
                qfont = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", QF)
            rows = text.split("\n")
            rows[0] = "«" + rows[0]
            rows[-1] = rows[-1] + "»"
            RH = 88
            top = y - (len(rows) * RH) / 2 - (14 if author else 0)
            for r, row in enumerate(rows):
                lines += _jump_chars(row, 960, top + r * RH, st + r * 0.30, en, qfont,
                                     stagger=0.028, fs=QF, style="Quote",
                                     tags=f"{fn}\\c&H{txt_col}&{edge}", layer=2,
                                     fade_out=FADE_OUT)
        else:
            lines.append(
                f"Dialogue: 2,{ass_time(st)},{ass_time(en)},Quote,,0,0,0,,"
                f"{{{fn}{q_txt}{edge}\\an5\\pos(960,{y - (16 if author else 0) - nl * 6})"
                f"\\fad({FADE_IN},{FADE_OUT})"
                f"\\t(0,220,\\fscx103\\fscy103)\\t(220,340,\\fscx100\\fscy100)}}«{esc}»"
            )
        if author:
            lines.append(
                f"Dialogue: 2,{ass_time(st)},{ass_time(en)},QuoteAuthor,,0,0,0,,"
                f"{{\\an5\\pos(960,{y + 54 + nl * 37})\\fad({FADE_IN},{FADE_OUT})}}{author}"
            )
        if sfx is not None:
            sfx.append({"at": st, "role": "quote"})
    return lines


# ---------- блок: текстовый лейбл-наименование (как подпись вида на фото) ----------
# Маленькая подпись сбоку, НЕ центр-верх (там accents) и НЕ низ (там будущие
# субтитры) — называет то, что уже видно в кадре, в стиле референса
# Parasitário ("BOCYDIUM GLOBULARE · 7MM"): короткое слово/фраза рядом с
# объектом, не факт и не цитата.

_LABEL_TAB_COLORS = [GOLD_BGR, "3DC7F2"]
_LABEL_FONTS = ["", "\\fnLiberation Sans"]  # "" = дефолт стиля (Arial)
_LABEL_CHAR_STAGGER = 0.045  # сек/символ — тот же темп, что у _jump_chars ниже


def build_labels(labels, sfx=None):
    """Подпись-наименование с лёгкой подложкой и "ушкой" на ближнем крае
    (не голый текст — см. build_quotes) И побуквенной анимацией самого
    текста (2026-10-07: раньше был целый блок через \\fad — "бедненько",
    по словам пользователя; буквы теперь выпрыгивают по одной, тем же
    bounce-паттерном, что у _jump_chars в build_comparison, просто
    переиспользованным здесь вместо изобретения третьего вида анимации)."""
    FADE_IN, FADE_OUT = 240, 200
    # 2026-10-17: ×1.5 к размерам документального формата (были 440x76/фс32).
    # В новостном кадре подпись читалась мелко и обрезалась — user смотрел
    # образец полного цикла и просил "увеличить примерно в полтора раза".
    # Стиль Label в HEADER поднят синхронно (34 -> 51), иначе измеренная
    # PIL-ширина разойдётся с реальной и буквы наедут друг на друга.
    # Плашка шьётся ПО ТЕКСТУ (2026-10-17). Прибитая ширина 660 давала разом
    # две беды: пустую коробку под словом "КАБИНЕТ" и текст, уехавший за край
    # под длинной подписью — то самое "подписи обрезаются".
    PAD, MIN_W, box_h = 42, 300, 114
    _DEJAVU_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    lines = []
    for i, l in enumerate(labels):
        st, en, text = l["start"], l["end"], l["text"]
        side = l.get("side", "left")
        y = l.get("y", 760)
        left = side == "left"
        tab_col = _col(l, _LABEL_TAB_COLORS[i % len(_LABEL_TAB_COLORS)])
        txt_col = tab_col if _ckey(l) in PALETTE_BGR else "FFFFFF"
        fn = _fnt(l, _LABEL_FONTS[i % len(_LABEL_FONTS)])
        font = _measure_font(l, 48, _DEJAVU_B)
        total_w = font.getlength(text)
        box_w = max(MIN_W, total_w + PAD * 2)
        bx0 = 90 if left else 1920 - 90 - box_w
        by0 = y - box_h / 2
        tx = bx0 + PAD if left else bx0 + box_w - PAD

        box = l.get("box", "plate")
        lines += _plate(st, en, bx0, by0, box_w, box_h, FADE_IN, FADE_OUT,
                        box, tab_col, left)
        if box == "solid":
            txt_col = INK_BGR          # на цветной заливке белым не прочесть
        # без заливки текст держится на собственной обводке, иначе он
        # пропадает на светлом кадре
        edge = "\\bord3.6\\3c&H0A0C0E&\\shad1" if box in ("bare", "line") else ""

        start_x = tx if left else tx - total_w
        char_y = y - 30  # примерный верх строки для an7 при fs51
        x = start_x
        for j, ch in enumerate(text):
            w = font.getlength(ch)
            if ch != " ":
                cst = st + j * _LABEL_CHAR_STAGGER
                lines.append(
                    f"Dialogue: 2,{ass_time(cst)},{ass_time(en)},Label,,0,0,0,,"
                    f"{{{fn}\\b1\\c&H{txt_col}&{edge}\\an7\\pos({x:.0f},{char_y:.0f})\\fad(10,{FADE_OUT})"
                    f"\\t(0,100,\\fscy130\\fscx130)\\t(100,200,\\fscy90\\fscx90)"
                    f"\\t(200,240,\\fscy100\\fscx100)}}{ch}"
                )
            x += w
        if box == "bare":
            ux = start_x
            lines.append(
                f"Dialogue: 2,{ass_time(st)},{ass_time(en)},Bar,,0,0,0,,"
                f"{{\\an7\\pos({ux:.0f},{char_y + 62:.0f})\\fad({FADE_IN},{FADE_OUT})"
                f"\\1c&H{tab_col}&\\p1}}m 0 0 l {total_w:.0f} 0 {total_w:.0f} 6 0 6")
        if sfx is not None:
            sfx.append({"at": st, "role": "label"})
    return lines


# ---------- блок: термометр (наливается + желтеет->краснеет) ----------

def build_thermometer(therm, width):
    t_st, t_en, label = therm["start"], therm["end"], therm.get("label", "")
    w0, h0 = therm.get("w", 300), therm.get("h", 26)
    x0 = width - therm.get("margin", 60) - w0
    y0 = therm.get("y", 140)
    steps = 14
    lines = []
    for i in range(steps):
        f0, f1 = i / steps, (i + 1) / steps
        sub_st = t_st + (t_en - t_st) * f0
        sub_en = t_st + (t_en - t_st) * f1
        w = max(4, int(w0 * f1))
        r = 255
        g = int(0xd2 + (0x3b - 0xd2) * f1)
        b = int(0x3d + (0x3b - 0x3d) * f1)
        col = f"&H00{b:02X}{g:02X}{r:02X}"
        lines.append(
            f"Dialogue: 2,{ass_time(sub_st)},{ass_time(sub_en)},Bar,,0,0,0,,"
            f"{{\\pos({x0},{y0})\\1c{col}\\p1}}m 0 0 l {w} 0 {w} {h0} 0 {h0}{{\\p0}}"
        )
    lines.append(
        f"Dialogue: 2,{ass_time(t_st)},{ass_time(t_en)},Bar,,0,0,0,,"
        f"{{\\pos({x0},{y0})\\1a&HFF&\\3c&HFFFFFF&\\bord2\\p1}}m 0 0 l {w0} 0 {w0} {h0} 0 {h0}{{\\p0}}"
    )
    if label:
        lines.append(
            f"Dialogue: 2,{ass_time(t_st)},{ass_time(t_en)},Therm,,0,0,0,,"
            f"{{\\pos({x0+w0//2},{y0-26})}}{label}"
        )
    return lines


# ---------- блок: кружки-сравнение (анимированные буквы + PNG с фото) ----------

def _jump_chars(text, center_x, y, t0, visible_until, font, stagger=0.05, fs=None,
                style="Accent", tags="\\b1\\c&HFFFFFF&", layer=3, fade_out=0):
    # fs по умолчанию берётся из самого PIL-шрифта: ширину строки меряем им,
    # а рисует ASS — если числа разойдутся, буквы наедут друг на друга
    fs = int(fs or getattr(font, "size", 34))
    lines = []
    x = center_x - font.getlength(text) / 2
    for i, ch in enumerate(text):
        w = font.getlength(ch)
        if ch != " ":
            st = t0 + i * stagger
            lines.append(
                f"Dialogue: {layer},{ass_time(st)},{ass_time(visible_until)},{style},,0,0,0,,"
                f"{{\\an7\\pos({x:.0f},{y:.0f})\\fs{fs}{tags}\\fad(10,{fade_out})"
                f"\\t(0,100,\\fscy130\\fscx130)\\t(100,200,\\fscy90\\fscx90)\\t(200,240,\\fscy100\\fscx100)}}{ch}"
            )
        x += w
    return lines


def build_comparison(cmp_cfg, width, out_png=None):
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    st, en = cmp_cfg["start"], cmp_cfg["end"]
    left, right = cmp_cfg["left"], cmp_cfg["right"]
    # 2026-10-17, ×1.5 к документальным размерам (были 300/9, шрифты 34/22):
    # в новостном кадре кружки читались мелко, а подписи под ними обрезались.
    SZ, BORDER = cmp_cfg.get("size", 450), cmp_cfg.get("border", 13)
    margin = cmp_cfg.get("margin", 120)
    cy = cmp_cfg.get("y", 60)  # верх кадра по умолчанию — не мешает нижним титрам и центру кадра

    # 2026-10-17: кружки висели по 10 с и успевали надоесть — потолок 5 с
    # (user: "держать 4-5 секунд"). Снять на конкретной вставке:
    # "max_seconds": 0 в конфиге. Окно кладётся обратно в cmp_cfg, потому что
    # PNG с кружками накладывается отдельным ffmpeg-проходом по тем же st/en.
    max_sec = cmp_cfg.get("max_seconds", 5.0)
    if max_sec and en - st > max_sec:
        en = st + max_sec
        cmp_cfg["end"] = en

    FB = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 51)
    FS = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 33)

    def make_circle(path, hexcolor):
        r, g, b = int(hexcolor[0:2], 16), int(hexcolor[2:4], 16), int(hexcolor[4:6], 16)
        im = Image.open(path).convert("RGB")
        im = ImageOps.fit(im, (SZ, SZ), Image.LANCZOS)
        mask = Image.new("L", (SZ, SZ), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, SZ, SZ), fill=255)
        out = Image.new("RGBA", (SZ + BORDER * 2, SZ + BORDER * 2), (0, 0, 0, 0))
        out.paste(im, (BORDER, BORDER), mask)
        ImageDraw.Draw(out).ellipse(
            (BORDER // 2, BORDER // 2, SZ + BORDER + BORDER // 2, SZ + BORDER + BORDER // 2),
            outline=(r, g, b, 255), width=BORDER)
        return out

    dark = make_circle(left["photo"], left.get("color", "FF5A5A"))
    light = make_circle(right["photo"], right.get("color", "FFD250"))
    dw = dark.width
    cx_l = margin
    cx_r = width - margin - dw

    if out_png:
        canvas = Image.new("RGBA", (width, cmp_cfg.get("height", 1080)), (0, 0, 0, 0))
        canvas.paste(dark, (cx_l, cy), dark)
        canvas.paste(light, (cx_r, cy), light)
        canvas.save(out_png)

    ass_lines = []
    label_y = cy + dark.height + 21
    def fit(text, center_x):
        """Подпись под кружком не должна уезжать за край кадра: если на
        штатном кегле не влезает — ужимаем её, а не обрезаем (2026-10-17,
        "КТО ОРЁТ ПОД ОКНАМИ" доставала до самой кромки)."""
        _DB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        allow = min(2 * (center_x - 24), 2 * (width - center_x - 24), dw + 170)
        size = 51
        while size > 30:
            f = ImageFont.truetype(_DB, size)
            if f.getlength(text) <= allow:
                return f, size
            size -= 3
        return ImageFont.truetype(_DB, 30), 30

    fl, sl = fit(left["label"], cx_l + dw / 2)
    fr, sr = fit(right["label"], cx_r + dw / 2)
    ass_lines += _jump_chars(left["label"], cx_l + dw / 2, label_y, st, en, fl, fs=sl)
    ass_lines += _jump_chars(right["label"], cx_r + dw / 2, label_y, st + 0.15, en, fr, fs=sr)

    def detail_block(text, cx, y):
        esc = text.replace("\n", "\\N")
        return (f"Dialogue: 3,{ass_time(st+1.1)},{ass_time(en)},Accent,,0,0,0,,"
                f"{{\\an8\\pos({cx:.0f},{y})\\fs{int(FS.size)}\\b0\\fad(200,0)}}{esc}")

    if left.get("detail"):
        ass_lines.append(detail_block(left["detail"], cx_l + dw / 2, label_y + 69))
    if right.get("detail"):
        ass_lines.append(detail_block(right["detail"], cx_r + dw / 2, label_y + 69))

    return ass_lines, (cx_l, cx_r, cy, dw)


# ---------- сборка файла ----------

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,56,&H00F2F2F2,&H000000FF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,3,0,2,2,80,80,75,1
Style: Accent,Arial Black,78,&H00FFFFFF,&H000000FF,&H00101010,&H00000000,1,0,0,0,100,100,1,0,1,4,0,8,60,60,100,1
Style: Bar,Arial,10,&H003DC7F2,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,8,0,0,0,1
Style: Therm,Arial,34,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,8,0,0,0,1
Style: Quote,DejaVu Sans,70,&H00EDE8DE,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,5,160,160,100,1
Style: QuoteAuthor,Arial,26,&H00C4A261,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,0,0,5,160,160,100,1
Style: Label,Arial,51,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,8,60,60,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def burn(in_mp4, out_mp4, ass_path, png_path, window):
    """Прожиг одним проходом: субтитры/накладки из ASS плюс PNG с кружками
    в их окно. Это и есть тот самый «второй проход», который раньше надо
    было помнить и делать руками."""
    import shlex
    import subprocess as sp
    ass_esc = ass_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    if png_path and window:
        st, en = window
        fc = (f"[0:v]ass='{ass_esc}'[v0];"
              f"[v0][1:v]overlay=0:0:enable='between(t,{st:.3f},{en:.3f})'[v]")
        cmd = ["nice", "-n", "19", "ffmpeg", "-v", "error", "-y", "-i", in_mp4,
               "-i", png_path, "-filter_complex", fc, "-map", "[v]"]
    else:
        cmd = ["nice", "-n", "19", "ffmpeg", "-v", "error", "-y", "-i", in_mp4,
               "-vf", f"ass='{ass_esc}'"]
    cmd += ["-map", "0:a?", "-c:a", "copy", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "19", "-pix_fmt", "yuv420p", "-threads", "2", out_mp4]
    r = sp.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print("прожиг не удался:", (r.stderr or "")[-600:])
        raise SystemExit(1)
    print("готовое видео:", out_mp4, "(субтитры, накладки"
          + (", кружки" if png_path and window else "") + ")")


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        raise SystemExit(1)
    cfg = json.load(open(args[0], encoding="utf-8"))
    out_ass = args[1]
    out_png = args[2] if len(args) > 2 and not args[2].startswith("--") else None
    burn_in = burn_out = None
    if "--burn" in args:
        i = args.index("--burn")
        if len(args) < i + 3:
            print("--burn требует два пути: входное и выходное видео")
            raise SystemExit(1)
        burn_in, burn_out = args[i + 1], args[i + 2]
        if out_png is None:
            out_png = out_ass.rsplit(".", 1)[0] + "_compare.png"

    w = cfg.get("width", 1920)
    h = cfg.get("height", 1080)
    blocks = cfg.get("blocks", {})

    body = [HEADER.format(w=w, h=h)]
    sfx = []  # {"at": сек_абс, "role": accent/label/quote/thermometer/comparison}
             # — свод для build_sfx_track.py, чтобы звук не прибивался вручную

    if blocks.get("captions") and cfg.get("srt"):
        body += build_captions(cfg["srt"])
    if blocks.get("accents"):
        body += build_accents(blocks["accents"], sfx)
    if blocks.get("quotes"):
        body += build_quotes(blocks["quotes"], sfx)
    if blocks.get("labels"):
        body += build_labels(blocks["labels"], sfx)
    if blocks.get("thermometer"):
        body += build_thermometer(blocks["thermometer"], w)
        sfx.append({"at": blocks["thermometer"]["start"], "role": "accent"})
    cmp_window = None
    if blocks.get("comparison"):
        cmp_lines, _ = build_comparison(blocks["comparison"], w, out_png)
        body += cmp_lines
        cmp_window = (blocks["comparison"]["start"], blocks["comparison"]["end"])
        print(f"кружки: {cmp_window[0]:.2f}-{cmp_window[1]:.2f} с")
        sfx.append({"at": blocks["comparison"]["start"], "role": "label"})

    open(out_ass, "w", encoding="utf-8").write("\n".join(body) + "\n")
    n = sum(1 for l in body if l.startswith("Dialogue"))
    sfx_path = out_ass.rsplit(".", 1)[0] + ".sfx.json"
    json.dump(sfx, open(sfx_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {out_ass}: {n} dialogue lines, {sfx_path}: {len(sfx)} sfx-событий"
          + (f", {out_png}" if out_png else ""))

    # окно кружков — отдельным файлом: чужому конвейеру иначе неоткуда
    # узнать, в какие секунды накладывать PNG
    if cmp_window and out_png:
        json.dump({"png": os.path.abspath(out_png),
                   "start": cmp_window[0], "end": cmp_window[1]},
                  open(out_ass + ".compare.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    if burn_in:
        burn(burn_in, burn_out, out_ass, out_png if cmp_window else None, cmp_window)


if __name__ == "__main__":
    main()
