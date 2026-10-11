#!/usr/bin/env python3
"""Grab PDF open access dari link OpenAlex atau query mentah.

Pakai:  .venv/bin/python openalex_grab.py "<url openalex | query>" [-p proyek] [-o folder] [-n maks] [-d delay]
Stdlib only.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import config
from . import papermeta
from .grabbers import BaseGrabber

SCAN = 5  # periksa paling banyak 5x maks artikel: banyak terbitan berbayar tak punya salinan terbuka
ARXIV_GAP = 3.0
_last_arxiv = 0.0
API = "https://api.openalex.org/works"
UA = "SkripsiAI/1.0 (mailto:research@example.com)"


def build_params(arg):
    """Return dict param API dari link openalex atau query mentah."""
    if arg.startswith("http"):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(arg).query)
        p = {k: v[0] for k, v in qs.items()}
    else:
        p = {"search": arg}
    p["per-page"] = 100  # semua artikel, termasuk berbayar: PDF dicari di salinan OA/arXiv per artikel
    return p


def search(params, page, mailto=None):
    q = dict(params, page=page)
    if mailto:
        q["mailto"] = mailto
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(q), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def from_ieee_host(url):
    """Ketentuan IEEE Xplore melarang unduh otomatis dari situsnya (juga konten OA); salinan di arXiv/repositori boleh."""
    host = urllib.parse.urlparse(url).hostname or ""
    return host == "ieee.org" or host.endswith(".ieee.org")


def pdf_urls(w):
    """Semua kandidat URL PDF OA: best dulu, lalu lokasi lain. Tautan situs IEEE dilewati."""
    urls = []
    loc = w.get("best_oa_location") or {}
    for l in [loc] + [l for l in w.get("locations") or [] if l.get("is_oa")]:
        u = l.get("pdf_url")
        if u and u not in urls and not from_ieee_host(u):
            urls.append(u)
    return urls


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def arxiv_pdf(w):
    """Pracetak arXiv untuk artikel (mis. terbitan berbayar): judul sama persis + nama belakang penulis pertama cocok."""
    title = w.get("display_name") or ""
    if not title:
        return None
    global _last_arxiv
    time.sleep(max(0, ARXIV_GAP - (time.monotonic() - _last_arxiv)))  # arXiv meminta jeda >=3 detik antar panggilan API
    _last_arxiv = time.monotonic()
    q = urllib.parse.urlencode({"search_query": 'ti:"%s"' % title.replace('"', " "), "max_results": 3})
    req = urllib.request.Request("http://export.arxiv.org/api/query?" + q, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            root = ET.fromstring(r.read())
    except Exception:
        return None
    ns = {"a": "http://www.w3.org/2005/Atom"}
    first = ((w.get("authorships") or [{}])[0].get("author") or {}).get("display_name", "")
    last = _norm(first.split()[-1]) if first.split() else ""
    for e in root.findall("a:entry", ns):
        names = _norm(" ".join(n.text or "" for n in e.findall("a:author/a:name", ns)))
        if _norm(e.findtext("a:title", "", ns)) == _norm(title) and (not last or last in names):
            return (e.findtext("a:id", "", ns) or "").replace("/abs/", "/pdf/").replace("http://", "https://")
    return None


def candidates(w, find_arxiv=arxiv_pdf):
    """URL PDF yang boleh dicoba: salinan OA dulu, lalu pracetak arXiv bila tak ada. Return [] bila tak ada."""
    urls = pdf_urls(w)
    if not urls:
        u = find_arxiv(w)
        urls = [u] if u else []
    return urls


def is_preprint(url):
    return (urllib.parse.urlparse(url).hostname or "").endswith("arxiv.org")


def fname(w):
    year = w.get("publication_year", "")
    oid = (w.get("id") or "").split("/")[-1]
    t = re.sub(r"[^\w\- ]+", "", w.get("display_name") or "untitled").strip()[:100]
    return f"{year}_{oid}_{t}.pdf"


BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "Chrome/124 Safari/537.36")


def save_meta(w, path, url):
    m = papermeta.from_openalex(w)
    if is_preprint(url):
        m["version"] = "pracetak"  # PDF = pracetak arXiv; halaman bisa beda dari versi terbitan
    papermeta.save(path, m)


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Referer": "https://openalex.org/"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if not data.startswith(b"%PDF"):
        raise ValueError("bukan PDF")
    with open(path, "wb") as f:
        f.write(data)


class OpenAlexGrabber(BaseGrabber):
    source = "openalex"

    def run(self, query_or_url, out="papers/openalex", max_n=0, delay=1.0, mailto=None):
        os.makedirs(out, exist_ok=True)
        params = build_params(query_or_url)
        ok = skip = fail = seen = page = 0
        titles = set()
        page = 1
        while True:
            d = search(params, page, mailto)
            if page == 1:
                print(f"Total hasil: {d['meta']['count']}")
            works = d.get("results") or []
            if not works:
                break
            for w in works:
                if max_n and (ok >= max_n or seen >= max_n * SCAN):
                    break
                seen += 1
                path = os.path.join(out, fname(w))
                t = _norm(w.get("display_name"))
                if os.path.exists(path) or t in titles:  # judul sama = salinan ganda (terbitan + arXiv)
                    skip += 1
                    continue
                titles.add(t)
                urls = candidates(w)
                if not urls:
                    skip += 1
                    time.sleep(delay)
                    continue
                err = None
                for url in urls:  # coba tiap lokasi OA sampai dapat
                    try:
                        download(url, path)
                        save_meta(w, path, url)
                        ok += 1
                        print(f"[{seen}] OK   {os.path.basename(path)}" + (" (pracetak arXiv)" if is_preprint(url) else ""))
                        break
                    except Exception as e:
                        err = e
                else:
                    fail += 1
                    print(f"[{seen}] GAGAL {w.get('id')}: {str(err)[:100]}")
                time.sleep(delay)
            if (max_n and (ok >= max_n or seen >= max_n * SCAN)) or page * 100 >= d["meta"]["count"]:
                break
            page += 1
        print(f"Selesai. ok={ok} skip={skip} gagal={fail} -> {out}/")
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
        OpenAlexGrabber().run(a.query_or_url, out, a.max, a.delay, a.mailto)
    except Exception as e:
        sys.exit(f"gagal: {e}")


if __name__ == "__main__":
    main()
