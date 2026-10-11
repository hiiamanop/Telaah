"""Metadata paper: sidecar <pdf>.json di sebelah PDF. Sumber kebenaran, boleh diedit tangan.

Field: title, authors (dipisah ' and '), year (int|None), doi, abstract, source.
"""
import json
import os
import re
import urllib.parse
import urllib.request

OPENALEX = "https://api.openalex.org/works"
UA = "SkripsiAI/1.0 (mailto:research@example.com)"


def sidecar(pdf_path):
    return os.path.splitext(pdf_path)[0] + ".json"


def save(pdf_path, meta):
    with open(sidecar(pdf_path), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)


def load(pdf_path):
    try:
        with open(sidecar(pdf_path)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _abstract(inv):
    """OpenAlex abstract_inverted_index -> teks."""
    pos = {i: w for w, ix in (inv or {}).items() for i in ix}
    return " ".join(pos[i] for i in sorted(pos))


def from_openalex(w):
    return {"title": w.get("display_name") or "",
            "authors": " and ".join(a["author"]["display_name"] for a in w.get("authorships") or []
                                    if a.get("author", {}).get("display_name")),
            "year": w.get("publication_year"),
            "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
            "abstract": _abstract(w.get("abstract_inverted_index")),
            "source": "openalex"}



def from_filename(name):
    """Nama hasil grabber: YYYY_ID_judul.pdf. Selain itu: judul = nama file."""
    stem = os.path.splitext(os.path.basename(name))[0]
    m = re.match(r"^(\d{4})_[^_]+_(.+)$", stem)
    return {"title": m.group(2) if m else stem, "authors": "", "year": int(m.group(1)) if m else None,
            "doi": "", "abstract": "", "source": "filename"}


def find_doi(text):
    # ponytail: DOI pertama di halaman 1; bisa salah bila itu DOI referensi. source="doi-lookup" menandai
    m = re.search(r"10\.\d{4,9}/[^\s\"<>]+", text)
    return m.group(0).rstrip(".,;:)]}").lower() if m else None


def by_doi(doi, mailto=None):
    url = f"{OPENALEX}/doi:{urllib.parse.quote(doi, safe='/')}" + (f"?mailto={mailto}" if mailto else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
            return dict(from_openalex(json.load(r)), source="doi-lookup")
    except Exception:
        return None


def resolve(pdf_path, first_page_text=""):
    """Sidecar kalau ada; kalau tidak: DOI halaman 1 -> OpenAlex; terakhir nama file. Hasil disimpan."""
    meta = load(pdf_path)
    if meta:
        return meta
    doi = find_doi(first_page_text)
    meta = (by_doi(doi) if doi else None) or from_filename(pdf_path)
    save(pdf_path, meta)
    return meta
