#!/usr/bin/env python3
"""Склеивает клипы из build_clips_1080.py через кроссфейд-переходы, НЕ теряя
синхронизацию с озвучкой.

Почему не просто concat demuxer + xfade: обычный xfade "съедает" TD секунд на
каждом стыке (итог короче суммы длительностей клипов на (n-1)*TD). Если потом
подгонять это под длину озвучки растяжением/сдвигом таймкодов субтитров —
получается НЕТОЧНО (на лионском тесте 2026-10-05 давало рассинхрон субтитров
в конце ролика на ~4.5с: подписи смещались равномерно, а реальные границы
сцен — скачками по 0.35с на каждом переходе).

Правильное решение: удлинить каждый клип (кроме последнего) на TD ещё ДО
склейки — тогда переход "съедает" ровно добавленное время, а исходные
границы сцен (и тайминги субтитров) остаются нетронутыми. Поэтому:

  1. Перед этим скриптом: в scenes.json увеличь duration_sec у всех сцен
     КРОМЕ последней на TD (обычно 0.35), затем пересобери клипы через
     build_clips_1080.py.
  2. Прогони этот скрипт — он посчитает реальные длительности клипов и
     построит filter_complex с правильными offset'ами.
  3. Субтитры (build_captions.py) делай из ОРИГИНАЛЬНОГО (неудлинённого)
     scenes.json/SRT — коррекция таймкодов не нужна вообще.

Usage:
  python3 xfade_assemble.py <clips-dir> <n-clips> <out.mp4> [transition-duration] [ffmpeg-bin]
"""
import json
import os
import subprocess
import sys


def dur(ffprobe, path):
    r = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    return float(r.stdout.strip())


# Спокойные переходы: не отвлекают от содержания и не мигают. Порядок
# подобран так, чтобы соседние стыки не были похожи, а `fade` возвращался
# как «дыхание» между более заметными.
MIX = ["fade", "smoothleft", "fadeblack", "wiperight", "dissolve",
       "fade", "smoothright", "slideleft", "wipeleft", "fadeblack",
       "fade", "slideright", "smoothup", "dissolve", "wipedown"]


def _supported(names, ffmpeg="ffmpeg"):
    """Оставить только те переходы, которые знает установленный ffmpeg:
    список режимов менялся от версии к версии, а неизвестное имя роняет
    всю склейку в самом конце сборки."""
    try:
        r = subprocess.run([ffmpeg, "-hide_banner", "-h", "filter=xfade"],
                           capture_output=True, text=True, timeout=20)
        have = r.stdout + r.stderr
    except Exception:
        return names
    ok = [n for n in names if f" {n} " in have or f"\n     {n}" in have]
    return ok or ["fade"]


def pick_transitions(spec, count, seed=0):
    """Список переходов на count стыков по строке-спецификации."""
    if spec == "mix":
        base = MIX
    else:
        base = [x.strip() for x in spec.split(",") if x.strip()] or ["fade"]
    out, prev = [], None
    for i in range(max(0, count)):
        cand = base[i % len(base)]
        # один и тот же переход не идёт два стыка подряд, если выбор есть
        if cand == prev and len(base) > 1:
            cand = base[(i + 1) % len(base)]
        out.append(cand)
        prev = cand
    return out


def main():
    args = sys.argv[1:]
    if len(args) < 3:
        print(__doc__)
        raise SystemExit(1)
    clips_dir, n, out_path = args[0], int(args[1]), args[2]
    td = float(args[3]) if len(args) > 3 else 0.35
    # ПЕРЕХОДЫ. До 19.10.2026 здесь был зашит один `fade` на весь ролик —
    # полсотни режимов ffmpeg простаивали. Теперь набор задаётся пятым
    # аргументом: имя одного перехода, перечень через запятую (идут по
    # кругу) или `mix` — спокойная подборка по умолчанию.
    # По умолчанию — РОТАЦИЯ (`mix`). Раньше здесь стоял один `fade`, и
    # хотя выбор перехода был сделан ещё 19.10, без пятого аргумента ролик
    # всё равно собирался на одном переходе — что и значилось в арсенале
    # как «переход между планами один». 20.10: умолчание изменено.
    tr_arg = args[4] if len(args) > 4 else "mix"
    ffmpeg = args[5] if len(args) > 5 else "ffmpeg"
    ffprobe = "ffprobe".join(ffmpeg.rsplit("ffmpeg", 1))

    clip_paths = [os.path.join(clips_dir, f"clip_{i:03d}.mp4") for i in range(1, n + 1)]
    transitions = pick_transitions(tr_arg, max(0, n - 1))
    allowed = _supported(sorted(set(transitions)), ffmpeg)
    transitions = [tr if tr in allowed else "fade" for tr in transitions]
    if transitions:
        print("переходы:", ", ".join(transitions))
    durs = [dur(ffprobe, p) for p in clip_paths]

    inputs, filt = [], []
    for i, p in enumerate(clip_paths, 1):
        inputs += ["-i", p]
        # normalise every input to the same fps/SAR/pix_fmt — xfade refuses to
        # run otherwise (hit this with mixed Ken-Burns-image clips and
        # stock-video clips: different SAR -> "parameters do not match")
        filt.append(f"[{i-1}:v]scale=1920:1080,setsar=1,fps=30,format=yuv420p[n{i}]")

    cumulative = durs[0]
    prev = "n1"
    for i in range(2, n + 1):
        offset = cumulative - td
        out_label = f"x{i}" if i < n else "vout"
        tr = transitions[i - 1] if i - 1 < len(transitions) else "fade"
        filt.append(f"[{prev}][n{i}]xfade=transition={tr}:duration={td}:"
                    f"offset={offset:.3f}[{out_label}]")
        cumulative = cumulative + durs[i - 1] - td
        prev = out_label

    filter_complex = ";".join(filt)
    # жёсткий потолок, не доля ядер — слабая машина пользователя, "половина
    # ядер" всё равно грузила её ощутимо (2026-10-07)
    threads = "2"
    cmd = (["nice", "-n", "19", "ionice", "-c3", ffmpeg, "-y"] + inputs +
           ["-filter_complex", filter_complex, "-map", f"[{prev}]",
            "-threads", threads, "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            out_path])
    subprocess.run(cmd, check=True)
    print(f"wrote {out_path}, expected duration {cumulative:.2f}s "
          f"(sum of clip durations {sum(durs):.2f}s)")


if __name__ == "__main__":
    main()
