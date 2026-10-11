#!/usr/bin/env python3
"""Ringkas tiap PDF -> CSV matriks literatur. Resume otomatis via CSV.

Pakai:  python -m telaah.summarize [-p proyek] [-n maks] [--redo]
"""
import argparse
import csv
import json
import os

from pypdf import PdfReader

from . import config
from . import llm

FIELDS = ["file", "title", "authors", "year", "problem", "method", "result", "doi"]

PROMPT = """Baca paper berikut, jawab JSON saja:
{"title": ..., "authors": "nama dipisah ' and '", "year": "YYYY angka saja",
 "problem": "1 kalimat", "method": "1-2 kalimat", "result": "1-2 kalimat",
 "doi": "10.xxxx/... atau kosong"}

Paper:
"""


def summarize(text):
    raw = llm.chat([{"role": "user", "content": PROMPT + text[:12000]}])[0]
    raw = raw[raw.find("{"):raw.rfind("}") + 1]
    return json.loads(raw)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("-n", "--max", type=int, default=0)
    a.add_argument("--redo", action="store_true")
    config.add_project_arg(a)
    a = a.parse_args()
    proj = config.project_from(a).ensure()
    CSV = proj.literature

    done = set()
    if os.path.exists(CSV) and not a.redo:
        with open(CSV) as f:
            done = {r["file"] for r in csv.DictReader(f)}

    pdfs = sorted(f for f in os.listdir(proj.papers) if f.endswith(".pdf"))
    pdfs = [f for f in pdfs if f not in done]
    if a.max:
        pdfs = pdfs[:a.max]
    new_file = not os.path.exists(CSV) or a.redo
    mode = "w" if new_file else "a"
    with open(CSV, mode, newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for i, pdf in enumerate(pdfs, 1):
            try:
                text = "\n".join((p.extract_text() or "")
                                 for p in PdfReader(f"{proj.papers}/{pdf}").pages[:4])
                w.writerow({"file": pdf, **summarize(text)})
                print(f"[{i}/{len(pdfs)}] OK {pdf}")
            except Exception as e:
                print(f"[{i}/{len(pdfs)}] GAGAL {pdf}: {str(e)[:120]}")


if __name__ == "__main__":
    main()
