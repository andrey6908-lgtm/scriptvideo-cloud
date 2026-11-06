#!/usr/bin/env python3
"""Удлиняет каждую сцену (кроме последней) в scenes.json на длительность
перехода TD, чтобы последующая склейка через xfade_assemble.py не сдвигала
границы сцен относительно озвучки.

ПОВТОРНЫЙ ЗАПУСК БЕЗОПАСЕН (с 20.10.2026). Раньше второй прогон молча
прибавлял ещё по TD секунд каждой сцене, ролик расходился с озвучкой, и
понять это можно было только по финальному рассинхрону. Теперь в файле
остаётся отметка `xfade_extended` с величиной удлинения: если она уже
стоит и совпадает — скрипт ничего не делает и говорит об этом; если
стоит ДРУГАЯ величина — пересчитывает от исходных длительностей.
`--undo` возвращает исходные значения.

Usage: python3 extend_for_xfade.py <scenes.json> [transition-duration=0.35]
       python3 extend_for_xfade.py <scenes.json> --undo
"""
import json
import sys


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        raise SystemExit(1)
    path = args[0]
    undo = "--undo" in args
    td = 0.35
    for a in args[1:]:
        if not a.startswith("--"):
            td = float(a)

    data = json.load(open(path, encoding="utf-8"))
    n = len(data["scenes"])
    was = data.get("xfade_extended")

    if undo:
        if not was:
            print("отметки об удлинении нет — файл и так исходный")
            return
        for s in data["scenes"]:
            if s["id"] < n:
                s["duration_sec"] = round(s["duration_sec"] - float(was), 2)
        data.pop("xfade_extended", None)
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"откат: снято по {was}s с {n-1}/{n} сцен")
        return

    if was is not None:
        if abs(float(was) - td) < 1e-6:
            print(f"уже удлинено на {td}s — повторный прогон ничего не меняет")
            return
        # величина перехода изменилась: сначала снимаем старое
        for s in data["scenes"]:
            if s["id"] < n:
                s["duration_sec"] = round(s["duration_sec"] - float(was), 2)
        print(f"было удлинение {was}s — пересчитываю на {td}s")

    for s in data["scenes"]:
        if s["id"] < n:
            s["duration_sec"] = round(s["duration_sec"] + td, 2)
    data["xfade_extended"] = td
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"удлинено {n-1}/{n} сцен на {td}s (последняя не тронута)")


if __name__ == "__main__":
    main()
