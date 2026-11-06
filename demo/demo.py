#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Рисует по одному КОРОТКОМУ примеру на каждое выразительное средство
документального сборщика (script-to-video) — для общей полки эффектов.

    python3 demo.py <папка сборки> [V5 V8 ...]

Без списка рисует все. Содержание нейтральное и сгенерированное: ни одной
чужой фотографии и ни одного куска настоящего ролика — пример показывает
ПРИЁМ, а не тему. Запускать только в облаке: на машине пользователя считать
нельзя (его прямое слово 22.10).

Коды V* — это номера средств на полке `effects-library`, они закреплены.
"""
import json, os, shutil, subprocess, sys, math, random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, "template")
sys.path.insert(0, TPL)

W, H = 1920, 1080
FF = os.environ.get("FFMPEG", "ffmpeg")
FP = os.environ.get("FFPROBE", "ffprobe")


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print("  ОШИБКА:", " ".join(str(c) for c in cmd)[:200])
        print("  ", (r.stderr or r.stdout)[-700:])
    return r


def tpl(name, *args):
    return run([sys.executable, os.path.join(TPL, name), *[str(a) for a in args]])


# ---------------------------------------------------------------- материал
def make_photo(path, seed, w=W, h=H):
    """Нейтральный абстрактный кадр: мягкий градиент, крупная форма, зерно.

    Не изображает ничего конкретного — на полке важно, ЧТО делает приём, а
    не что на фотографии. Так пример не стареет вместе с темой ролика.
    """
    from PIL import Image, ImageDraw, ImageFilter
    rnd = random.Random(seed)
    base = rnd.choice([(54, 62, 78), (72, 58, 48), (46, 66, 60),
                       (78, 64, 72), (40, 52, 70), (84, 74, 56)])
    top = tuple(min(255, int(c * 1.75) + 18) for c in base)
    im = Image.new("RGB", (w, h), base)
    d = ImageDraw.Draw(im)
    for y in range(h):                      # вертикальный градиент
        k = y / h
        d.line([(0, y), (w, y)],
               fill=tuple(int(top[i] * (1 - k) + base[i] * k) for i in range(3)))
    for _ in range(3):                      # мягкие пятна света
        r = rnd.randint(int(h * 0.3), int(h * 0.8))
        cx, cy = rnd.randint(0, w), rnd.randint(0, h)
        glow = Image.new("L", (w, h), 0)
        ImageDraw.Draw(glow).ellipse([cx - r, cy - r, cx + r, cy + r], fill=46)
        glow = glow.filter(ImageFilter.GaussianBlur(r * 0.45))
        im = Image.composite(Image.new("RGB", (w, h), top), im, glow)
    d = ImageDraw.Draw(im, "RGBA")          # одна крупная геометрия
    for i in range(rnd.randint(2, 4)):
        x = rnd.randint(-int(w * 0.1), int(w * 0.8))
        y = rnd.randint(-int(h * 0.1), int(h * 0.7))
        s = rnd.randint(int(h * 0.25), int(h * 0.7))
        a = rnd.randint(18, 40)
        if rnd.random() < 0.5:
            d.ellipse([x, y, x + s, y + s], outline=(235, 230, 220, a + 40),
                      width=max(2, s // 90))
        else:
            d.rectangle([x, y, x + s, y + int(s * 0.7)], fill=(235, 230, 220, a))
    im = im.filter(ImageFilter.GaussianBlur(0.6))
    px = im.load()                          # лёгкое зерно, чтобы не было пластика
    for _ in range(w * h // 70):
        xx, yy = rnd.randrange(w), rnd.randrange(h)
        r0, g0, b0 = px[xx, yy]
        n = rnd.randint(-12, 12)
        px[xx, yy] = (max(0, min(255, r0 + n)), max(0, min(255, g0 + n)),
                      max(0, min(255, b0 + n)))
    im.save(path, quality=93)


def make_video_source(path, src_img, seconds=13.0):
    """Настоящий mp4 из кадра: медленный проезд. Нужен там, где приём
    работает ТОЛЬКО поверх видео (всплывашки) или показывает подрезку видео."""
    run([FF, "-y", "-v", "error", "-loop", "1", "-i", src_img,
         "-vf", (f"scale={int(W*1.25)}:{int(H*1.25)},"
                 f"zoompan=z=1:x='(iw-{W})*(on/({seconds}*30))':y='(ih-{H})/2'"
                 f":d=1:s={W}x{H}:fps=30,format=yuv420p"),
         "-t", str(seconds), "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "20", "-an", path])


def dur(path):
    r = subprocess.run([FP, "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# ---------------------------------------------------------------- подготовка
def prepare(B):
    d = {k: os.path.join(B, k) for k in
         ("images", "clips", "bg", "out", "tmp", "framed", "corner")}
    for p in d.values():
        os.makedirs(p, exist_ok=True)

    print("· фоны-паттерны (V4)")
    tpl("make_bg_texture.py", d["bg"])

    print("· нейтральные кадры")
    for i in range(1, 7):
        make_photo(os.path.join(d["images"], f"scene_{i:03d}.jpg"), seed=i * 17)
    for name, seed in (("photo_a", 71), ("photo_b", 72), ("photo_c", 73)):
        make_photo(os.path.join(d["tmp"], f"{name}.jpg"), seed=seed, w=1100, h=1100)

    print("· видео-исходники для сцен 4 и 5")
    for sid in (4, 5):
        src = os.path.join(d["images"], f"scene_{sid:03d}.jpg")
        make_video_source(os.path.join(d["images"], f"scene_{sid:03d}.mp4"), src)

    scenes = {"scenes": [{"id": i, "duration_sec": 7.0} for i in range(1, 7)]}
    sp = os.path.join(B, "scenes.json")
    json.dump(scenes, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("· клипы сцен")
    tpl("build_clips_1080.py", sp, d["images"], d["clips"], FF)
    return d, sp


# ---------------------------------------------------------------- средства
def demo_frames(B, d, out):
    """V1 рамка-паспарту, V2 угловой квадрат, V4 процедурные фоны."""
    r = tpl("frame_clips.py", d["clips"], d["bg"], d["framed"])
    src = os.path.join(d["framed"], "clip_001.mp4")
    if os.path.exists(src):
        shutil.copy(src, out("V1", "ramka-passpartu"))

    # угловую раскладку разрешаем всем клипам и берём ТОТ, которому она выпала:
    # раскладка выбирается детерминированно, «попросить» её нельзя
    r = tpl("frame_clips.py", d["clips"], d["bg"], d["corner"],
            "--corner", "1,2,3,4,5,6")
    pick = None
    for line in (r.stdout or "").splitlines():
        if "layout=corner_square" in line and "-> ok" in line:
            pick = line.split("]")[1].split("(")[0].strip()
            break
    if pick and os.path.exists(os.path.join(d["corner"], pick)):
        shutil.copy(os.path.join(d["corner"], pick), out("V2", "uglovoy-kvadrat"))
    else:
        print("  угловая раскладка не выпала ни одному клипу")

    # V4: сами фоны — медленный проезд по каждому из четырёх паттернов
    import glob
    pngs = sorted(glob.glob(os.path.join(d["bg"], "*.png")))[:4]
    parts = []
    for i, p in enumerate(pngs):
        q = os.path.join(d["tmp"], f"bg{i}.mp4")
        run([FF, "-y", "-v", "error", "-loop", "1", "-i", p,
             "-vf", (f"scale={int(W*1.15)}:-1,crop={W}:{H}:"
                     f"'(iw-{W})*(t/1.9)':'(ih-{H})/2',fps=30,format=yuv420p"),
             "-t", "1.9", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-an", q])
        if os.path.exists(q):
            parts.append(q)
    if parts:
        lst = os.path.join(d["tmp"], "bg_list.txt")
        open(lst, "w").write("\n".join(f"file '{os.path.abspath(p)}'" for p in parts))
        run([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
             "-c", "copy", out("V4", "procedurnye-fony")])


def demo_clips(B, d, out):
    """V5 Ken Burns по фото, V6 видео-сцена под длительность."""
    for sid, code, slug in ((1, "V5", "ken-burns"), (4, "V6", "video-scena")):
        src = os.path.join(d["clips"], f"clip_{sid:03d}.mp4")
        if os.path.exists(src):
            shutil.copy(src, out(code, slug))


def demo_xfade(B, d, out):
    """V7 кроссфейд-склейка без потери синхронизации."""
    sp = os.path.join(B, "scenes_x.json")
    json.dump({"scenes": [{"id": i, "duration_sec": 2.8} for i in (1, 2, 3)]},
              open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    cx = os.path.join(B, "clips_x")
    os.makedirs(cx, exist_ok=True)
    tpl("extend_for_xfade.py", sp, "0.35")
    tpl("build_clips_1080.py", sp, d["images"], cx, FF)
    tpl("xfade_assemble.py", cx, "3", out("V7", "krossfeyd-skleyka"), "0.35", FF)


def _burn(B, d, out, code, slug, blocks, srt=None, base_sid=2):
    """Общий путь для надписей: конфиг → build_dynamics --burn → готовый клип."""
    cfg = {"width": W, "height": H, "blocks": blocks}
    if srt:
        cfg["srt"] = srt
    cp = os.path.join(d["tmp"], f"dyn_{code}.json")
    json.dump(cfg, open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    base = os.path.join(d["clips"], f"clip_{base_sid:03d}.mp4")
    tpl("build_dynamics.py", cp, os.path.join(d["tmp"], f"dyn_{code}.ass"),
        "--burn", base, out(code, slug))


def demo_dynamics(B, d, out):
    """V8 заголовок, V9 цитата, V10 лейбл, V11 субтитры, V13 термометр,
    V14 кружки-сравнение."""
    _burn(B, d, out, "V8", "akcentnyy-zagolovok",
          {"accents": [{"start": 0.7, "end": 6.3, "text": "1960-Е · АРХИВ"}]})
    _burn(B, d, out, "V9", "citata-plashka",
          {"quotes": [{"start": 0.7, "end": 6.5,
                       "text": "Решение приняли за одну ночь", "author": ""}]})
    _burn(B, d, out, "V10", "leybl-podpis-sboku",
          {"labels": [{"start": 0.6, "end": 6.4, "text": "ВЕРХНЯЯ ПАЛУБА",
                       "side": "left"}]})
    srt = os.path.join(d["tmp"], "demo.srt")
    open(srt, "w", encoding="utf-8").write(
        "1\n00:00:00,400 --> 00:00:02,600\nНижняя дорожка подписей\n\n"
        "2\n00:00:02,700 --> 00:00:04,800\nидёт под кадром и не спорит\n\n"
        "3\n00:00:04,900 --> 00:00:06,900\nс остальными надписями.\n")
    _burn(B, d, out, "V11", "subtitry-nizhnyaya-dorozhka",
          {"captions": True}, srt=srt)
    _burn(B, d, out, "V13", "termometr-indikator",
          {"thermometer": {"start": 0.6, "end": 6.4, "label": "ГЛУБИНА"}})
    _burn(B, d, out, "V14", "kruzhki-sravnenie",
          {"comparison": {"start": 0.6, "end": 6.6,
                          "left": {"photo": os.path.join(d["tmp"], "photo_a.jpg"),
                                   "label": "ПЕРВЫЙ ОБРАЗЕЦ",
                                   "detail": "плотнее\nтяжелее", "color": "FF5A5A"},
                          "right": {"photo": os.path.join(d["tmp"], "photo_b.jpg"),
                                    "label": "ВТОРОЙ ОБРАЗЕЦ",
                                    "detail": "легче\nбыстрее", "color": "FFD250"}}})


def demo_charts(B, d, out):
    """V15 столбчатый график, V16 слайдер-диапазон."""
    bars = {"title": "Три образца", "seconds": 6.5,
            "caption": "высота столбца — соотношение, а не точное число",
            "bars": [{"label": "ПЕРВЫЙ", "color": "D4B896", "value": 0.34,
                      "photo": os.path.join(d["tmp"], "photo_a.jpg")},
                     {"label": "ВТОРОЙ", "color": "9C6B3E", "value": 0.61,
                      "photo": os.path.join(d["tmp"], "photo_b.jpg")},
                     {"label": "ТРЕТИЙ", "color": "4A2F1E", "value": 0.92,
                      "photo": os.path.join(d["tmp"], "photo_c.jpg")}]}
    p = os.path.join(d["tmp"], "bars.json")
    json.dump(bars, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tpl("build_chart_bars.py", p, out("V15", "stolbchatyy-grafik"))

    sl = {"title": "Оценка · диапазон", "min": 0, "max": 140, "low": 28,
          "high": 135, "range_label": "ПЕРВОНАЧАЛЬНАЯ ОЦЕНКА",
          "marker_value": 35, "marker_display": "≈35", "seconds": 6.5,
          "caption": "диапазон показан целиком, метка — уточнённое значение",
          "photo": {"path": os.path.join(d["tmp"], "photo_c.jpg"),
                    "label": "образец"}}
    p = os.path.join(d["tmp"], "slider.json")
    json.dump(sl, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tpl("build_chart_slider.py", p, out("V16", "slayder-diapazon"))


def demo_cards(B, d, out):
    """V18 карточка-глава, V19 карточка-факт, V20 карточка-досье."""
    tpl("make_chapter_card.py", "ГЛАВА ПЕРВАЯ", "Как это начиналось",
        "Северное побережье · 1901", out("V18", "kartochka-glava"), "6")

    cc = {"background_photo": os.path.join(d["images"], "scene_002.jpg"),
          "eyebrow": "Полевая запись",
          "text": "ТЕКСТ ПОЯВЛЯЕТСЯ ПОСИМВОЛЬНО, КАК НА МАШИНКЕ.",
          "source": "подпись-источник набирается курсивом", "seconds": 6.5}
    p = os.path.join(d["tmp"], "concept.json")
    json.dump(cc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tpl("make_concept_card.py", p, out("V19", "kartochka-fakt"))

    pc = {"title": "ОБЪЕКТ №1", "subtitle": "СЕВЕРНОЕ ПОБЕРЕЖЬЕ · 1901",
          "main_photo": os.path.join(d["tmp"], "photo_a.jpg"),
          "top_fields": [{"label": "КАТЕГОРИЯ", "value": "ПЕРВЫЙ ТИП"},
                         {"label": "СОСТОЯНИЕ", "value": "СОХРАНЁН"}],
          "stats": [{"label": "НАЙДЕНО", "value": "28–135"},
                    {"label": "СРОК", "value": "9 МЕСЯЦЕВ"},
                    {"label": "ОПИСАН", "value": "ДЕК. 1901"},
                    {"label": "ХРАНИТСЯ", "value": "АРХИВ"}],
          "insets": [{"photo": os.path.join(d["tmp"], "photo_b.jpg"),
                      "label": "ВСТАВКА"},
                     {"photo": os.path.join(d["tmp"], "photo_c.jpg"),
                      "label": "ВСТАВКА"}],
          "seconds": 7.0}
    p = os.path.join(d["tmp"], "profile.json")
    json.dump(pc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tpl("build_profile_card.py", p, out("V20", "kartochka-dose"))


def demo_overlays(B, d, out, sp):
    """V21 фото-попап с выездом из угла, V22 текстовая всплывашка-слово.

    Оба приёма кладутся ТОЛЬКО поверх видео-сцены (поверх фото выглядит
    плоско) — поэтому сцены 4 и 5 сделаны настоящими mp4.
    """
    ov = {"anchor": "bottom",
          "4": {"photo": os.path.join(d["tmp"], "photo_c.jpg"), "at": 0.6},
          "5": {"text": {"words": "ОДНО СЛОВО", "color": "yellow",
                         "at": 0.8, "pos": "bc"}}}
    p = os.path.join(d["tmp"], "overlays.json")
    json.dump(ov, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tpl("build_overlays.py", "overlay", sp, d["images"], d["clips"], p)
    for sid, code, slug in ((4, "V21", "foto-popap"), (5, "V22", "tekstovaya-vsplyvashka")):
        src = os.path.join(d["clips"], f"clip_{sid:03d}.mp4")
        if os.path.exists(src):
            shutil.copy(src, out(code, slug))


# ---------------------------------------------------------------- запуск
GROUPS = [("рамки и фоны", demo_frames, ("V1", "V2", "V4")),
          ("клипы сцен", demo_clips, ("V5", "V6")),
          ("кроссфейд", demo_xfade, ("V7",)),
          ("надписи", demo_dynamics, ("V8", "V9", "V10", "V11", "V13", "V14")),
          ("диаграммы", demo_charts, ("V15", "V16")),
          ("карточки", demo_cards, ("V18", "V19", "V20")),
          ("всплывашки", demo_overlays, ("V21", "V22"))]


def main():
    B = sys.argv[1] if len(sys.argv) > 1 else "build"
    only = {a.upper() for a in sys.argv[2:]} or None
    os.makedirs(B, exist_ok=True)
    d, sp = prepare(B)

    def out(code, slug):
        return os.path.join(d["out"], f"{code}_{slug}.mp4")

    for name, fn, codes in GROUPS:
        if only and not (set(codes) & only):
            continue
        print(f"\n=== {name}: {', '.join(codes)}")
        try:
            fn(B, d, out, sp) if fn is demo_overlays else fn(B, d, out)
        except Exception as e:
            print(f"  ГРУППА УПАЛА: {type(e).__name__}: {e}")

    print("\n=== итог")
    made, missing = [], []
    for _, _, codes in GROUPS:
        for c in codes:
            f = [x for x in sorted(os.listdir(d["out"])) if x.startswith(c + "_")]
            if f and dur(os.path.join(d["out"], f[0])) > 0.4:
                made.append((c, f[0], dur(os.path.join(d["out"], f[0]))))
            else:
                missing.append(c)
    for c, f, s in made:
        print(f"  {c:<4} {s:5.1f} с  {f}")
    print(f"готово {len(made)} из {len(made) + len(missing)}")
    if missing:
        print("НЕ ВЫШЛО:", ", ".join(missing))


if __name__ == "__main__":
    main()
