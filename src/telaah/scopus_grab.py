#!/usr/bin/env python3
"""Cari artikel open access via Scopus (termasuk Elsevier), unduh PDF-nya via OpenAlex per DOI.

Pakai:  python -m telaah.scopus_grab "<teks | query Scopus>" [-p proyek] [-n maks] [-d delay]
Perlu ELSEVIER_API_KEY. Key non-institusi hanya boleh Scopus Search (25 hasil/halaman, tanpa abstrak,
tanpa full text Elsevier); PDF diambil dari lokasi OA di OpenAlex, sekitar 60% artikel punya.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

from . import config
from . import openalex_grab as oa
from . import papermeta
from .grabbers import BaseGrabber

API = "https://api.elsevier.com/content/search/scopus"
PAGE = 25  # batas count untuk key standar


def scopus_query(arg):
    """Teks biasa -> TITLE-ABS-KEY(...); selalu paksa OPENACCESS(1)."""
    q = arg if re.search(r"\b[A-Z-]{3,}\(", arg) else f"TITLE-ABS-KEY({arg})"
    return q if "OPENACCESS(" in q else f"({q}) AND OPENACCESS(1)"


def scopus_search(query, start, key):
    url = API + "?" + urllib.parse.urlencode({"query": query, "count": PAGE, "start": start})
    req = urllib.request.Request(url, headers={"X-ELS-APIKey": key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["search-results"]


def entry_dois(entries):
    # DOI dengan ',' atau '|' merusak filter OpenAlex; dilewati (jarang)
    return [e["prism:doi"].lower() for e in entries
            if e.get("prism:doi") and not re.search(r"[,|]", e["prism:doi"])]


def works_by_doi(dois, mailto=None):
    out = {}
    for i in range(0, len(dois), 50):
        d = oa.search({"filter": "doi:" + "|".join(dois[i:i + 50]), "per-page": 50}, 1, mailto)
        for w in d.get("results") or []:
            out[(w.get("doi") or "").replace("https://doi.org/", "").lower()] = w
    return out


class ScopusGrabber(BaseGrabber):
    source = "scopus"

    def run(self, query_or_url, out, max_n=0, delay=1.0, mailto=None):
        if not config.ELSEVIER_API_KEY:
            raise SystemExit("ELSEVIER_API_KEY belum diisi di .env")
        os.makedirs(out, exist_ok=True)
        q = scopus_query(query_or_url)
        dois, start = [], 0
        while True:
            r = scopus_search(q, start, config.ELSEVIER_API_KEY)
            if start == 0:
                print(f"Total hasil Scopus: {r['opensearch:totalResults']}")
            dois += entry_dois(r.get("entry") or [])  # hasil kosong = entry berisi {"error": ...}
            start += PAGE
            if start >= int(r["opensearch:totalResults"]) or (max_n and len(dois) >= max_n):
                break
        dois = dois[:max_n] if max_n else dois
        works = works_by_doi(dois, mailto)
        ok = skip = fail = nopdf = 0
        for n, doi in enumerate(dois, 1):
            w = works.get(doi)
            urls = oa.candidates(w) if w else []
            if not urls:
                nopdf += 1
                continue
            path = os.path.join(out, oa.fname(w))
            if os.path.exists(path):
                skip += 1
                continue
            for url in urls:
                try:
                    oa.download(url, path)
                    oa.save_meta(w, path, url)
                    ok += 1
                    print(f"[{n}] OK   {os.path.basename(path)}")
                    break
                except Exception:
                    pass
            else:
                fail += 1
                print(f"[{n}] GAGAL {doi}")
            time.sleep(delay)
        print(f"Selesai. ok={ok} skip={skip} gagal={fail} tanpa_pdf={nopdf} -> {out}/")
        return ok, skip, fail


def main():
    a = argparse.ArgumentParser()
    a.add_argument("query_or_url")
    a.add_argument("-o", "--out", default=None, help="folder tujuan (default: papers/ proyek)")
    a.add_argument("-n", "--max", type=int, default=0)
    a.add_argument("-d", "--delay", type=float, default=1.0)
    a.add_argument("--mailto", default=None)
    config.add_project_arg(a)
    a = a.parse_args()
    out = a.out or config.project_from(a).ensure().papers
    try:
        ScopusGrabber().run(a.query_or_url, out, a.max, a.delay, a.mailto)
    except Exception as e:
        sys.exit(f"gagal: {e}")


if __name__ == "__main__":
    main()
