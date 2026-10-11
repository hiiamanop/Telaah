#!/usr/bin/env python3
"""Export literature.csv proyek -> references.bib (BibTeX).

Pakai:  python -m telaah.export_bib [-p proyek]
"""
import argparse
import csv
import re

from . import config

a = argparse.ArgumentParser()
config.add_project_arg(a)
proj = config.project_from(a.parse_args())
rows = list(csv.DictReader(open(proj.literature)))
with open(proj.bib, "w") as f:
    for r in rows:
        if not r.get("title"):
            continue
        key = re.sub(r"\W+", "", (r["authors"].split(",")[0].split() or ["x"])[-1] + r.get("year", ""))
        f.write(f"@article{{{key},\n  title={{{r['title']}}},\n"
                f"  author={{{r['authors']}}},\n  year={{{r.get('year', '')}}},\n"
                f"  doi={{{r.get('doi', '')}}},\n  file={{{r['file']}}}\n}}\n\n")
print(f"{len(rows)} baris -> {proj.bib}")
