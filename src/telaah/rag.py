#!/usr/bin/env python3
"""Tanya berbasis bukti: retrieve Chroma -> saring bukti -> jawab hanya dari bukti, tiap klaim bersitasi.

Bukti tak cukup (jarak di atas ambang) -> tidak memanggil LLM. Jawaban = klaim berstruktur; hanya klaim yang
kutipannya terbukti ada (verbatim) di chunk rujukannya yang ditampilkan.
Setiap tanya dicatat di tabel answers (data/<proyek>/memory.db): pertanyaan, jawaban, bukti, jarak.

Pakai:  python -m telaah.rag "pertanyaan" [-p proyek] [-k top_k] [--max-dist 0.4]
"""
import argparse
import time

from . import config
from . import evidence
from . import llm
from . import memory
from . import store

SYSTEM = ("Kamu asisten riset. Jawab HANYA dari bukti [S1], [S2], ... yang diberikan. "
          'Keluarkan JSON saja: {"klaim": [{"teks": "klaim dalam bahasa pertanyaan", "bukti": "S2", '
          '"kutipan": "salinan PERSIS 1-2 kalimat dari bukti itu yang mendukung klaim"}], '
          '"catatan": "hal yang ditanyakan tapi tidak ada di bukti, atau kosong"}. '
          "Aturan: kutipan disalin kata per kata dari bukti (bahasa aslinya, jangan diubah atau diterjemahkan, "
          "boleh '...' untuk melompati bagian); satu klaim = satu bukti; maksimal 8 klaim; "
          "bila bukti tidak memuat jawabannya, klaim kosong dan jelaskan di catatan; "
          "bukti bertentangan = klaim terpisah. Jangan memakai pengetahuan di luar bukti.")


def extract_claims(question, sel):
    """Minta klaim berstruktur; satu kali ulang bila JSON rusak. Return (klaim terverifikasi, catatan, via)."""
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Bukti:\n{evidence.build_context(sel)}\n\nPertanyaan: {question}"}]
    for attempt in range(2):
        raw, via = llm.chat(msgs)
        try:
            claims, note = evidence.parse_claims(raw)
            return evidence.verify_claims(claims, sel), note, via
        except ValueError as e:
            msgs += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": f"Format salah ({e}). Keluarkan ulang JSON saja sesuai format."}]
    return [], "", via


def ask(proj, question, k=config.TOP_K, max_dist=config.MAX_DIST, mem=None, sid=None):
    """Return dict: status ('answered'|'unverified'|'no_evidence'), answer, claims, evidence[], answer_id.
    answered = minimal satu klaim yang kutipannya terbukti ada di bukti. Dicatat ke mem (dibuka bila None)."""
    col = store.open_collection(proj)
    q = llm.embed([question])[0]
    res = col.query(query_embeddings=[q], n_results=max(k * 4, 20),
                    include=["documents", "metadatas", "distances"])
    sel = evidence.select(res, k, max_dist)
    rec = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "question": question, "max_dist": max_dist,
           "best_dist": round(res["distances"][0][0], 3) if res["distances"][0] else None,
           "evidence": [{"id": f"S{i}", "cite": evidence.cite(m), "file": m["file"], "page": m["page"],
                         "dist": round(d, 3), "text": t} for i, (d, m, t) in enumerate(sel, 1)]}
    if not sel:
        rec.update(status="no_evidence", answer="", via="")
    else:
        claims, note, via = extract_claims(question, sel)
        good = [c for c in claims if c["ok"]]
        rec.update(status="answered" if good else "unverified", via=via, claims=claims,
                   answer=evidence.render_answer(claims, note),
                   cited=sorted({int(c["bukti"].strip("[]S")) for c in good}),
                   invalid_cites=[c["bukti"] for c in claims if c["reason"] == "id bukti tidak ada"])
    own = mem is None
    mem = mem or memory.Memory(proj)
    try:
        rec["answer_id"] = mem.add_answer(rec, sid)
    finally:
        if own:
            mem.close()
    return rec


def format_result(r):
    """Teks tampilan hasil ask(): klaim terverifikasi + bukti, atau penolakan. Dicetak program, bukan model."""
    if r["status"] == "no_evidence":
        return (f"Bukti tidak cukup: jarak terbaik {r['best_dist']} > ambang {r['max_dist']}. "
                "Koleksi tidak memuat topik ini. Tambah artikel (grab + ingest) atau ubah pertanyaan.")
    dropped = [c for c in r["claims"] if not c["ok"]]
    if r["status"] == "unverified":
        head = "Tidak ada klaim yang kutipannya terbukti ada di bukti; jawaban tidak ditampilkan."
    else:
        head = f"(via {r['via']}, jawaban #{r['answer_id']}; tiap klaim disertai kutipan yang terbukti ada di paper)"
    lines = [head, r["answer"]] if r["answer"] else [head]
    lines += ["", "Bukti:"] + [f"  [{e['id']}] {e['cite']} (jarak {e['dist']})" for e in r["evidence"]]
    if dropped:
        lines.append(f"{len(dropped)} klaim dibuang karena kutipan tak terverifikasi "
                     f"({', '.join(sorted({c['reason'] for c in dropped}))}).")
    lines.append("Catatan: kutipan terbukti ada; maknanya tetap perlu Anda nilai sendiri.")
    return "\n".join(lines)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("question")
    a.add_argument("-k", type=int, default=config.TOP_K)
    a.add_argument("--max-dist", type=float, default=config.MAX_DIST)
    config.add_project_arg(a)
    a = a.parse_args()
    proj = config.project_from(a)

    try:
        r = ask(proj, a.question, a.k, a.max_dist)
    except Exception as e:
        if isinstance(e, SystemExit):
            raise
        raise SystemExit(f"proyek '{proj.name}' belum punya index ({str(e)[:80]}). Jalankan ingest.py -p {proj.name}")
    print(format_result(r))


if __name__ == "__main__":
    main()
