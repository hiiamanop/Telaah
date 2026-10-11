#!/usr/bin/env python3
"""Metadata Crossref by title. Return dict atau None."""
import json
import urllib.parse
import urllib.request

API = "https://api.crossref.org/works"
UA = "Telaah/1.0 (mailto:research@example.com)"


def lookup(title, year=None):
    """3 kandidat, terima bila overlap judul >=60% dan tahun +-1."""
    q = urllib.parse.urlencode({"query.bibliographic": title, "rows": 3, "select": "DOI,title,author,container-title,volume,issue,page,published,URL"})
    req = urllib.request.Request(API + "?" + q, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        items = json.load(r)["message"].get("items") or []
    want = set(title.lower().split())
    for m in items:
        got = (m.get("title") or [""])[0]
        overlap = len(want & set(got.lower().split())) / max(1, len(want))
        y = (m.get("published") or {}).get("date-parts", [[None]])[0][0]
        if overlap >= 0.6 and (year is None or (y and abs(y - year) <= 1)):
            break
    else:
        return None
    authors = " and ".join(f"{a.get('given', '')} {a.get('family', '')}".strip()
                           for a in m.get("author", []))
    year = (m.get("published") or {}).get("date-parts", [[ ""]])[0][0]
    return {"doi": m.get("DOI", ""), "title": (m.get("title") or [""])[0],
            "authors": authors, "journal": (m.get("container-title") or [""])[0],
            "volume": m.get("volume", ""), "issue": m.get("issue", ""),
            "pages": m.get("page", ""), "year": str(year), "url": m.get("URL", "")}
