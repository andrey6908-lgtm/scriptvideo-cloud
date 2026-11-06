#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Накладывает PNG с кружками-сравнением на видео в нужном окне времени.

`build_dynamics.py` рисует подписи и кольца внутри ASS, а сами круглые
фото выкладывает отдельным PNG — без второго прохода кружки остаются
пустыми. Раньше этот проход надо было собирать руками по напечатанному
окну, и его легко было забыть (найдено ревизией 19.10.2026). Теперь —
одна команда, окно читается прямо из конфига.

    python3 bake_compare.py <dyn.json> <compare.png> <in.mp4> <out.mp4>

Появление и уход — мягкие, 0.35 с, чтобы кружки не выщёлкивали.
"""
import json
import os
import subprocess
import sys

FADE = 0.35


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        raise SystemExit(1)
    cfg_path, png, src, dst = sys.argv[1:5]
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    cmp_cfg = (cfg.get("blocks") or {}).get("comparison")
    if not cmp_cfg:
        print("в конфиге нет блока comparison — накладывать нечего")
        raise SystemExit(2)
    if not os.path.exists(png):
        print(f"нет файла с кружками: {png}")
        raise SystemExit(2)

    st = float(cmp_cfg["start"])
    en = float(cmp_cfg["end"])
    fin = f"{st:.2f}:{FADE}"
    fout = f"{max(st, en - FADE):.2f}:{FADE}"
    flt = (f"[1:v]format=rgba,fade=t=in:st={fin}:alpha=1,"
           f"fade=t=out:st={fout}:alpha=1[ov];"
           f"[0:v][ov]overlay=0:0:enable='between(t,{st:.2f},{en:.2f})'[v]")

    cmd = ["nice", "-n", "19", "ffmpeg", "-v", "error", "-y",
           "-i", src, "-loop", "1", "-i", png,
           "-filter_complex", flt, "-map", "[v]"]
    # звук исходника сохраняем, если он есть
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                            "-show_entries", "stream=index", "-of", "csv=p=0", src],
                           capture_output=True, text=True)
    if probe.stdout.strip():
        cmd += ["-map", "0:a", "-c:a", "copy"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-pix_fmt", "yuv420p", "-threads", "2", dst]
    subprocess.run(cmd, check=True)
    print(f"кружки наложены в окне {st:.2f}-{en:.2f} с -> {dst}")


if __name__ == "__main__":
    main()
