"""Pilih bukti dari hasil query Chroma dan format sitasi. Fungsi murni, tanpa jaringan."""
import json
import re
import unicodedata

from . import config


def cite(m):
    """Label sitasi dari metadata chunk: 'Wei dkk. 2025, hlm. 6' (hlm. 0 = abstrak)."""
    names = [n.strip() for n in (m.get("authors") or "").split(" and ") if n.strip()]
    last = [n.split()[-1] for n in names]
    who = (last[0] if len(last) == 1 else f"{last[0]} dan {last[1]}" if len(last) == 2
           else f"{last[0]} dkk.") if last else (m.get("title") or m.get("file", "?"))[:40]
    year = m.get("year") or "t.t."
    page = "abstrak" if m.get("page") == 0 else f"hlm. {m.get('page')}"
    return f"{who} {year}, {page}" + (f" ({m['version']})" if m.get("version") else "")


def is_reference_list(text):
    # ponytail: heuristik, >=4 tahun dalam satu chunk ~ daftar pustaka. Ganti dengan deteksi heading bila meleset.
    return (len(re.findall(r"\b(?:19|20)\d{2}\b", text)) >= 4
            and len(re.findall(r"\bpp\.?\s*\d|\bet al\b|\bIn:|\bProceedings\b|\bvol\.", text)) >= 2)


def select(res, k=config.TOP_K, max_dist=config.MAX_DIST):
    """res = hasil col.query. Return [(dist, meta, teks)] lolos ambang jarak dan bukan daftar pustaka."""
    rows = zip(res["distances"][0], res["metadatas"][0], res["documents"][0])
    return [r for r in rows if r[0] <= max_dist and not is_reference_list(r[2])][:k]


def build_context(sel):
    return "\n\n".join(f"[S{i}] ({cite(m)})\n{t}" for i, (_, m, t) in enumerate(sel, 1))


MIN_QUOTE = 25   # huruf+angka minimal kutipan, supaya kutipan sepele ("the model") tak lolos
MAX_QUOTE = 400  # karakter; kutipan sepanjang chunk tak membuktikan apa pun
_ELLIPSIS = re.compile(r"\[\s*\.{3}\s*\]|\[\s*…\s*\]|\.{3}|…")


def _alnum(s):
    """Huruf+angka saja, huruf kecil, NFKC: kebal terhadap spasi, tanda hubung baris, ligatur, tanda baca."""
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", s).lower())


def verify_quote(quote, text):
    """(ok, alasan). Kutipan harus ada verbatim di teks chunk; '...' boleh memisahkan potongan berurutan."""
    if len(quote) > MAX_QUOTE:
        return False, "kutipan terlalu panjang"
    parts = [p for p in (_alnum(x) for x in _ELLIPSIS.split(quote)) if p]
    if sum(map(len, parts)) < MIN_QUOTE:
        return False, "kutipan terlalu pendek"
    hay, pos = _alnum(text), 0
    for p in parts:
        i = hay.find(p, pos)
        if i < 0:
            return False, "kutipan tidak ada di bukti"
        pos = i + len(p)
    return True, ""


def parse_claims(raw):
    """JSON jawaban model -> (klaim[], catatan). Raise ValueError bila bentuknya salah."""
    try:
        d = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except ValueError as e:
        raise ValueError(f"bukan JSON: {e}")
    if not isinstance(d, dict) or not isinstance(d.get("klaim"), list):
        raise ValueError('JSON harus berbentuk {"klaim": [...], "catatan": "..."}')
    claims = []
    for c in d["klaim"][:MAX_CLAIMS]:
        if not isinstance(c, dict) or not all(isinstance(c.get(k), str) for k in ("teks", "bukti", "kutipan")):
            raise ValueError("tiap klaim butuh teks, bukti, kutipan (string)")
        claims.append({k: c[k].strip() for k in ("teks", "bukti", "kutipan")})
    note = d.get("catatan")
    return claims, (note.strip()[:300] if isinstance(note, str) else "")


MAX_CLAIMS = 8


def verify_claims(claims, sel):
    """Tandai tiap klaim ok/alasan terhadap bukti terpilih sel=[(dist, meta, teks)]. Mengembalikan salinan."""
    out = []
    for c in claims:
        m = re.fullmatch(r"S(\d+)", c["bukti"].strip().strip("[]"))
        if not c["teks"]:
            ok, why = False, "klaim kosong"
        elif not m or not 1 <= int(m.group(1)) <= len(sel):
            ok, why = False, "id bukti tidak ada"
        else:
            ok, why = verify_quote(c["kutipan"], sel[int(m.group(1)) - 1][2])
        out.append(dict(c, ok=ok, reason=why))
    return out


def render_answer(claims, note=""):
    """Jawaban dari klaim LOLOS saja, tiap klaim dengan kutipan aslinya agar bisa dibandingkan pembaca."""
    lines = [f"- {c['teks']} [{c['bukti']}]\n    > \"{c['kutipan']}\"" for c in claims if c["ok"]]
    if note:
        lines.append(f"Tidak ada di bukti (catatan model, tidak diverifikasi): {note}")
    return "\n".join(lines)
