import json

import pytest

from telaah import config
from telaah import evidence as ev
from telaah import rag
from telaah import store

TEXT = ("The proposed XGA-E frame-\nwork reduces false alarms by 12% on the NetFlow dataset. "
        "Sparsity is the proportion of critical components identified by the XAI method.")


def test_verify_quote_tolerant_to_pdf_noise_but_strict_on_content():
    ok = lambda q, t=TEXT: ev.verify_quote(q, t)[0]
    assert ok("The proposed XGA-E framework reduces false alarms by 12% on the NetFlow dataset")
    assert ok("the PROPOSED xga-e  frame- work reduces false alarms by 12% on the netflow dataset.")
    assert ok("proposed XGA-E framework ... Sparsity is the proportion of critical components")  # urut maju
    assert not ok("Sparsity is the proportion of critical components ... The proposed XGA-E framework reduces")  # urutan terbalik
    assert not ok("The proposed XGA-E framework reduces false alarms by 21% on the NetFlow dataset")  # angka diubah
    assert not ok("The proposed XGA-E framework reduces false alarms on every dataset we tried")  # karangan
    assert ev.verify_quote("reduces false", TEXT) == (False, "kutipan terlalu pendek")
    assert ev.verify_quote("x" * 401, TEXT) == (False, "kutipan terlalu panjang")
    assert ev.verify_quote("", TEXT)[0] is False and ev.verify_quote("...", TEXT)[0] is False
    assert ev.verify_quote("ﬁlter ﬁlter ﬁlter ﬁlter ﬁlter", "filter filter filter filter filter")[0]  # ligatur


def test_parse_claims_accepts_wrapped_json_rejects_bad_shapes():
    raw = 'Ini hasilnya:\n```json\n{"klaim":[{"teks":"a","bukti":"S1","kutipan":"k"}],"catatan":"n"}\n```'
    claims, note = ev.parse_claims(raw)
    assert claims == [{"teks": "a", "bukti": "S1", "kutipan": "k"}] and note == "n"
    for bad in ("tanpa json", "{}", '{"klaim": "x"}', '{"klaim":[1]}', '{"klaim":[{"teks":"a"}]}',
                '{"klaim":[{"teks":1,"bukti":"S1","kutipan":"k"}]}'):
        with pytest.raises(ValueError):
            ev.parse_claims(bad)
    many = {"klaim": [{"teks": "a", "bukti": "S1", "kutipan": "k"}] * 20}
    assert len(ev.parse_claims(json.dumps(many))[0]) == ev.MAX_CLAIMS


def test_verify_claims_checks_the_cited_chunk_not_any_chunk():
    sel = [(0.1, {}, TEXT), (0.2, {}, "Completely different chunk about busbar splitting in power grids today.")]
    q = "The proposed XGA-E framework reduces false alarms by 12% on the NetFlow dataset"
    claims = [{"teks": "a", "bukti": "S1", "kutipan": q}, {"teks": "b", "bukti": "S2", "kutipan": q},
              {"teks": "c", "bukti": "S9", "kutipan": q}, {"teks": "d", "bukti": "[S1]", "kutipan": q},
              {"teks": "", "bukti": "S1", "kutipan": q}, {"teks": "e", "bukti": "bebas", "kutipan": q}]
    got = [(c["ok"], c["reason"]) for c in ev.verify_claims(claims, sel)]
    assert got == [(True, ""), (False, "kutipan tidak ada di bukti"), (False, "id bukti tidak ada"), (True, ""),
                   (False, "klaim kosong"), (False, "id bukti tidak ada")]


def test_render_answer_only_verified_with_quote():
    cl = [{"teks": "benar", "bukti": "S1", "kutipan": "kutipan asli", "ok": True, "reason": ""},
          {"teks": "karangan", "bukti": "S1", "kutipan": "palsu", "ok": False, "reason": "x"}]
    out = ev.render_answer(cl, "dataset tak disebut")
    assert "benar [S1]" in out and "kutipan asli" in out and "karangan" not in out and "dataset tak disebut" in out


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    p = config.Project("a").ensure()
    col = store.open_collection(p, create=True)
    col.add(ids=["1"], embeddings=[[1.0, 0.0]], documents=[TEXT],
            metadatas=[{"file": "f", "page": 2, "title": "T", "authors": "Ada Lovelace", "year": 2025, "doi": ""}])
    monkeypatch.setattr(rag.llm, "embed", lambda ts: [[1.0, 0.0]])
    return p


GOOD = {"teks": "framework menurunkan alarm palsu", "bukti": "S1",
        "kutipan": "reduces false alarms by 12% on the NetFlow dataset"}
FAKE = {"teks": "framework juara semua dataset", "bukti": "S1",
        "kutipan": "outperforms every baseline on all datasets tested"}


def test_ask_drops_fabricated_claims_keeps_verified(proj, monkeypatch):
    raw = json.dumps({"klaim": [GOOD, FAKE], "catatan": "dataset lain tak disebut"})
    monkeypatch.setattr(rag.llm, "chat", lambda m: (raw, "fake"))
    r = rag.ask(proj, "apa hasilnya?")
    assert r["status"] == "answered" and r["cited"] == [1]
    assert "menurunkan alarm palsu" in r["answer"] and "juara" not in r["answer"]
    assert [c["ok"] for c in r["claims"]] == [True, False]
    shown = rag.format_result(r)
    assert "1 klaim dibuang" in shown and "juara" not in shown and "maknanya tetap perlu Anda nilai" in shown
    from telaah import memory
    saved = memory.Memory(proj).answer(r["answer_id"])
    assert [c["ok"] for c in saved["claims"]] == [True, False]  # klaim dibuang tetap tercatat untuk audit


def test_ask_all_fabricated_is_unverified_and_hides_answer(proj, monkeypatch):
    monkeypatch.setattr(rag.llm, "chat", lambda m: (json.dumps({"klaim": [FAKE]}), "fake"))
    r = rag.ask(proj, "apa hasilnya?")
    assert r["status"] == "unverified" and "juara" not in rag.format_result(r)
    assert "jawaban tidak ditampilkan" in rag.format_result(r)


def test_ask_retries_once_on_bad_json_then_gives_up(proj, monkeypatch):
    replies = iter(["bukan json sama sekali", json.dumps({"klaim": [GOOD]})])
    seen = []
    monkeypatch.setattr(rag.llm, "chat", lambda m: seen.append(len(m)) or (next(replies), "fake"))
    assert rag.ask(proj, "q")["status"] == "answered" and seen == [2, 4]
    monkeypatch.setattr(rag.llm, "chat", lambda m: ("rusak terus", "fake"))
    assert rag.ask(proj, "q")["status"] == "unverified"


def test_memory_v1_migrates_to_v2(tmp_path, monkeypatch):
    import sqlite3
    from telaah import memory
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    p = config.Project("m").ensure()
    c = sqlite3.connect(f"{p.dir}/memory.db")
    c.executescript(memory.SCHEMA.replace(",\n  claims text not null default '[]'", ""))
    c.execute("pragma user_version=1")
    c.execute("insert into answers(time, question, status) values('t','q','answered')")
    c.commit(); c.close()
    m = memory.Memory(p)
    assert m.db.execute("pragma user_version").fetchone()[0] == 2 and m.answer(1)["claims"] == []
