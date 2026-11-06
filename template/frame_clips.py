#!/usr/bin/env python3
"""Оборачивает каждый клип в декоративную раскладку (рамка-паспарту на
гуляющем фоне) ВМЕСТО футажа на весь экран 1920x1080 — по образцу
конкурента (референс-канал прислал пользователь, 2026-10-06). Вторая
версия (см. SKILL.md "6c" для истории первой): раскладка и фон теперь
ОБА варьируются от клипа к клипу, не один статичный вид на весь ролик.

Фон — любой .png (сгенерированный `make_bg_texture.py`, больше 1920x1080,
панорамируется кропом) ИЛИ .mp4 (реальный видео-задник, напр.
клетка.mp4/клетка2.mp4 из библиотеки пользователя — см. SKILL.md "Библиотека
ассетов" — масштабируется чуть больше кадра и тоже панорамируется кропом,
плюс стартует со случайного места своего 53-секундного цикла, чтобы два
клипа с одним и тем же видео-задником не выглядели одинаково).

Раскладки (выбираются детерминированно по индексу клипа, см. _pick_layout):
  center_box    — классический паспарту: один прямоугольник по центру,
                  поля со всех сторон.
  corner_square — квадрат в одном из верхних углов (чередуются левый/
                  правый), низ кадра остаётся свободным под субтитры.

**Было, убрано 2026-10-07**: раскладка `full` — без рамки вообще, клип на
весь экран. Пользователь поймал это как "каменный век"/"чистый сток" —
рамка+фон это БАЗА этого видеоряда (см. SKILL.md/память: "рамка и фон —
основная база, этого нельзя повторять [без них]"), не один из равноценных
вариантов, которым можно пожертвовать ради разнообразия. Теперь ВСЕГДА
рамка на гуляющем фоне, разнообразие только между `center_box`/
`corner_square`.

Ни layout, ни фон не повторяются два раза подряд (тот же принцип, что для
фото в видеоряде — см. SKILL.md/память: без соседних повторов).

**Было, убрано 2026-10-07**: раскладка `pip` — маленькая вставка в углу,
показывающая ДРУГОЙ МОМЕНТ ТОГО ЖЕ клипа. Пользователь поймал это как
дублирование ("вправо должна быть картинка, если это всплывашка... но
никак не дублирует один к одному эту основную картинку"). Верно — у
frame_clips.py на входе только один клип на сцену, второго осмысленного
изображения взять неоткуда; имитация "второго фрейма" тем же клипом
нарушает то же правило, что уже действует для попапов
(`build_overlays.py`: попап обязан нести НОВУЮ информацию, не повторять
кадр). Если нужен настоящий "кадр в кадре" с другим содержанием — это
задача попап-слоя (`build_overlays.py`, отдельное фото с реальной
дополнительной ценностью), не рамки.

**Угловая раскладка с 20.10.2026 снова доступна — но ТОЛЬКО там, где её
есть чем занять.** Её выключили 2026-10-07 из-за того, что свободная часть
кадра оставалась пустым фоном (память: corner_square empty space). Причина
была не в самой раскладке, а в том, что её ставили там, где поверх ничего
не ложится. Поэтому теперь угол включается адресно:

  --corner 3,7,12           — этим клипам можно угловую раскладку
  --corner-from <ass|json>  — взять номера сцен оттуда, где есть накладка
                              (build_dynamics .ass/.sfx.json или
                              overlays scenes.json)

Без этих ключей поведение прежнее: всегда `center_box`, пустоты не будет.

Usage:
  python3 frame_clips.py <clips_dir> <bg_dir> <out_dir> [box_w] [box_h]
                         [--corner 3,7,12] [--corner-from file]

bg_dir — папка с .png/.mp4 фонами вперемешку (frame_clips сам разбирает по
расширению).
"""
import glob
import os
import random
import subprocess
import sys

BORDER = 14
BG_TARGET_W, BG_TARGET_H = 1920, 1080
LAYOUTS = ["center_box"]
# слабая машина пользователя — жёсткий потолок потоков, не доля ядер
# (2026-10-07: "половина ядер" всё равно ощущалась как перегрузка на
# 24 клипах подряд; см. SKILL.md "Процессор — не мешать пользователю")
_THREADS = "2"


def _ffprobe_wh(ffprobe, path):
    r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=width,height",
                         "-of", "csv=s=x:p=0", path], capture_output=True, text=True)
    w, h = r.stdout.strip().split("\n")[0].split("x")
    return int(w), int(h)


def _dur(ffprobe, path):
    r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", path],
                        capture_output=True, text=True)
    return float(r.stdout.strip())


def _bg_input_and_crop(bg_path, ffprobe, dur, rnd, label):
    """Возвращает (input_args, filter_str) для гуляющего фона 1920x1080.
    Png — панорама кропом по уже-большому холсту. Mp4 — масштаб чуть
    больше кадра + панорама кропом + случайный старт внутри цикла, чтобы
    повторное использование того же файла не читалось одинаково."""
    is_video = bg_path.lower().endswith((".mp4", ".mov", ".webm", ".mkv"))
    if is_video:
        src_w, src_h = _ffprobe_wh(ffprobe, bg_path)
        src_dur = _dur(ffprobe, bg_path)
        scale_w, scale_h = int(BG_TARGET_W * 1.15), int(BG_TARGET_H * 1.15)
        xrange, yrange = scale_w - BG_TARGET_W, scale_h - BG_TARGET_H
        start = rnd.uniform(0, max(0.1, src_dur - dur - 0.5))
        inp = ["-stream_loop", "-1", "-ss", f"{start:.2f}", "-t", f"{dur:.3f}", "-i", bg_path]
        filt = (
            f"[{{idx}}:v]scale={scale_w}:{scale_h},"
            f"crop={BG_TARGET_W}:{BG_TARGET_H}:x='{xrange}*t/{dur:.3f}':"
            f"y='{yrange}*(0.5+0.3*sin(t))',fps=30[{label}]"
        )
    else:
        bg_w, bg_h = _ffprobe_wh(ffprobe, bg_path)
        xrange, yrange = max(1, bg_w - BG_TARGET_W), max(1, bg_h - BG_TARGET_H)
        inp = ["-loop", "1", "-t", f"{dur:.3f}", "-i", bg_path]
        filt = (
            f"[{{idx}}:v]crop={BG_TARGET_W}:{BG_TARGET_H}:x='{xrange}*t/{dur:.3f}':"
            f"y='{yrange}*(0.5+0.3*sin(t))',fps=30[{label}]"
        )
    return inp, filt


def _pick(seq, rnd, last):
    choices = [x for x in seq if x != last] or list(seq)
    pick = rnd.choice(choices)
    return pick


def build_cmd(clip_path, bg_path, out_path, dur, layout, box_w, box_h, ffmpeg, ffprobe, rnd):
    panel_w, panel_h = box_w + BORDER * 2, box_h + BORDER * 2
    ox, oy = (1920 - panel_w) // 2, (1080 - panel_h) // 2

    inputs = ["-i", clip_path]
    idx_counter = [1]

    if layout == "full":
        vf = f"[0:v]scale=1920:1080,setsar=1,fps=30,format=yuv420p[vout]"
        cmd = ["nice", "-n", "19", "ionice", "-c3", ffmpeg, "-y"] + inputs + [
            "-filter_complex", vf, "-map", "[vout]", "-t", f"{dur:.3f}",
            "-threads", _THREADS, "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", out_path]
        return cmd

    bg_inp, bg_filt_tmpl = _bg_input_and_crop(bg_path, ffprobe, dur, rnd, "bg")
    bg_filt = bg_filt_tmpl.format(idx=idx_counter[0])
    inputs += bg_inp
    idx_counter[0] += 1

    if layout == "center_box":
        vf = (
            f"[0:v]scale={box_w}:{box_h},pad={panel_w}:{panel_h}:{BORDER}:{BORDER}:color=0xEDE8DC[fg];"
            f"{bg_filt};"
            f"[bg][fg]overlay={ox}:{oy}[vout]"
        )
    elif layout == "corner_square":
        side = rnd.choice(["left", "right"])
        sq = min(box_w, box_h, 760)
        panel = sq + BORDER * 2
        cx = 90 if side == "left" else 1920 - 90 - panel
        cy = 90
        vf = (
            f"[0:v]scale={sq}:{sq}:force_original_aspect_ratio=increase,crop={sq}:{sq},"
            f"pad={panel}:{panel}:{BORDER}:{BORDER}:color=0xEDE8DC[fg];"
            f"{bg_filt};"
            f"[bg][fg]overlay={cx}:{cy}[vout]"
        )
    else:
        raise ValueError(layout)

    cmd = ["nice", "-n", "19", "ionice", "-c3", ffmpeg, "-y"] + inputs + [
        "-filter_complex", vf, "-map", "[vout]", "-t", f"{dur:.3f}",
        "-threads", _THREADS, "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", out_path]
    return cmd


def _corner_set(args):
    """Номера клипов, которым разрешена угловая раскладка."""
    out = set()
    if "--corner" in args:
        i = args.index("--corner")
        if len(args) > i + 1:
            out |= {int(x) for x in args[i + 1].replace(" ", "").split(",") if x}
    if "--corner-from" in args:
        i = args.index("--corner-from")
        if len(args) > i + 1 and os.path.exists(args[i + 1]):
            src = args[i + 1]
            try:
                if src.endswith(".json"):
                    import json
                    data = json.load(open(src, encoding="utf-8"))
                    items = data if isinstance(data, list) else data.get("scenes", [])
                    for it in items:
                        n = it.get("scene") or it.get("id") or it.get("n")
                        if n:
                            out.add(int(n))
                else:   # .ass — берём сцены по номеру из имён слоёв Dialogue
                    import re
                    for m in re.finditer(r"scene[_ ]?(\d+)", open(src, encoding="utf-8").read()):
                        out.add(int(m.group(1)))
            except Exception as e:
                print("не смог прочитать", src, e)
    return out


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        raise SystemExit(1)
    clips_dir, bg_dir, out_dir = sys.argv[1:4]
    pos = [a for a in sys.argv[4:] if not a.startswith("--")]
    # позиционные после ключей не берём: --corner 3,7 съедал бы box_w
    flags = sys.argv[4:]
    cut = len(pos)
    if "--corner" in flags:
        i = flags.index("--corner")
        pos = [a for a in flags[:i] if not a.startswith("--")]
    box_w = int(pos[0]) if len(pos) > 0 else 1480
    box_h = int(pos[1]) if len(pos) > 1 else 832
    corner_ok = _corner_set(sys.argv[4:])
    if corner_ok:
        print("угловая раскладка разрешена клипам:",
              ", ".join(str(x) for x in sorted(corner_ok)))
    ffmpeg, ffprobe = "ffmpeg", "ffprobe"
    os.makedirs(out_dir, exist_ok=True)

    bg_files = sorted(glob.glob(os.path.join(bg_dir, "*.png")) +
                       glob.glob(os.path.join(bg_dir, "*.mp4")))
    if not bg_files:
        print(f"нет фонов в {bg_dir}"); raise SystemExit(1)

    # исключаем clip_NNN.orig.mp4 — это резервная копия ДО попапа, которую
    # оставляет build_overlays.py; без фильтра глоб ловил её как лишний
    # клип и сбивал порядок/число сцен (2026-10-07)
    clips = sorted(p for p in glob.glob(f"{clips_dir}/clip_*.mp4") if not p.endswith(".orig.mp4"))
    last_layout, last_bg = None, None
    for i, path in enumerate(clips, 1):
        name = os.path.basename(path)
        out_path = os.path.join(out_dir, name)
        dur = _dur(ffprobe, path)
        rnd = random.Random(i * 997)  # детерминированно по индексу клипа

        # угол — только там, где его есть чем занять (см. шапку файла)
        pool = LAYOUTS + (["corner_square"] if i in corner_ok else [])
        layout = _pick(pool, rnd, last_layout) if len(pool) > 1 else pool[0]
        bg_path = _pick(bg_files, rnd, last_bg) if layout != "full" else None
        last_layout, last_bg = layout, (bg_path or last_bg)

        cmd = build_cmd(path, bg_path, out_path, dur, layout, box_w, box_h, ffmpeg, ffprobe, rnd)
        r = subprocess.run(cmd, capture_output=True, text=True)
        status = "ok" if r.returncode == 0 else "FAILED: " + r.stderr[-400:]
        bg_name = os.path.basename(bg_path) if bg_path else "—"
        print(f"[{i:02d}/{len(clips)}] {name} ({dur:.2f}s) layout={layout} bg={bg_name} -> {status}")


if __name__ == "__main__":
    main()
