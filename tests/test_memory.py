import os
import stat

import pytest

from telaah import config
from telaah.memory import Memory


@pytest.fixture
def mem(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    return Memory(config.Project("a"))


def _rec(status="answered", q="apa metode utama?", ans="Metode X [S1]"):
    return {"time": "2026-10-09T10:00:00", "question": q, "status": status, "answer": ans, "via": "t",
            "max_dist": 0.4, "best_dist": 0.2, "cited": [1], "invalid_cites": [],
            "evidence": [{"id": "S1", "cite": "Wei 2025, hlm. 3", "file": "f.pdf", "page": 3, "dist": 0.2, "text": "teks bukti"}]}


def test_db_private_and_versioned(mem):
    assert stat.S_IMODE(os.stat(mem.path).st_mode) == 0o600
    assert mem.db.execute("pragma user_version").fetchone()[0] == 2
    mem.db.execute("pragma user_version=99")
    with pytest.raises(SystemExit):
        Memory(config.Project("a"))


def test_persists_across_instances_and_resume_format(mem):
    sid = mem.new_session("uji")
    mem.add_message(sid, "user", "cari artikel GNN")
    calls = [{"id": "c1", "type": "function", "function": {"name": "cari", "arguments": "{}"}}]
    mem.add_message(sid, "assistant", None, tool_calls=calls)
    mem.add_message(sid, "tool", "5 artikel", tool_call_id="c1", name="cari")
    mem.add_message(sid, "assistant", "Selesai")
    mem.close()
    m2 = Memory(config.Project("a"))  # proses baru = sesi baru
    assert m2.last_session() == sid
    h = m2.history(sid)
    assert [x["role"] for x in h] == ["user", "assistant", "tool", "assistant"]
    assert h[1]["tool_calls"] == calls and h[2]["tool_call_id"] == "c1" and h[2]["name"] == "cari"
    assert "tool_calls" not in h[0]


def test_sessions_are_isolated_and_ordered(mem):
    s1, s2 = mem.new_session(), mem.new_session()
    mem.add_message(s1, "user", "satu")
    mem.add_message(s2, "user", "dua")
    mem.add_message(s1, "assistant", "tiga")
    assert [m["content"] for m in mem.history(s1)] == ["satu", "tiga"]
    assert mem.last_session() == s2 and [s["n"] for s in mem.sessions()] == [1, 2]


def test_search_handles_hostile_input_and_skips_tool_output(mem):
    sid = mem.new_session()
    mem.add_message(sid, "user", "bandingkan metode PGExplainer dan GNNExplainer")
    mem.add_message(sid, "tool", "rahasiaalat hanya di hasil tool", tool_call_id="x")
    mem.add_answer(_rec(q="apa itu PGExplainer?", ans="Penjelas berbasis probabilistik"), sid)
    kinds = {r["kind"] for r in mem.search("PGExplainer")}
    assert kinds == {"message", "answer"}
    assert mem.search("rahasiaalat") == []  # hasil tool tidak diindeks
    for bad in ('"', 'a" OR "b', "NEAR(", "C++ *", "'; drop table messages;--", "   ", ""):
        mem.search(bad)  # tidak boleh melempar
    assert mem.db.execute("select count(*) from messages").fetchone()[0] == 2


def test_decision_requires_evidence_and_copies_it(mem):
    ok = mem.add_answer(_rec())
    no = mem.add_answer(_rec(status="no_evidence", ans=""))
    with pytest.raises(ValueError):
        mem.add_decision("pakai metode X", no)
    with pytest.raises(ValueError):
        mem.add_decision("pakai metode X", 999)
    did = mem.add_decision("pakai metode X", ok)
    assert mem.decisions()[0]["id"] == did
    import json
    snap = json.loads(mem.db.execute("select evidence from decisions where id=?", (did,)).fetchone()[0])
    assert snap[0]["text"] == "teks bukti"
    assert any(r["kind"] == "decision" for r in mem.search("metode"))


def test_notes_and_working_memory_budget(mem):
    n = mem.add_note("fokus ke dataset NYT")
    mem.add_decision("pakai metode X", mem.add_answer(_rec()))
    sid = mem.new_session()
    mem.set_summary(sid, "bahas XAI untuk GNN", title="xai")
    wm = mem.working_memory()
    assert "fokus ke dataset NYT" in wm and "pakai metode X" in wm
    assert "belum diverifikasi" in wm and "bahas XAI" in wm
    assert mem.drop_note(n) and not mem.drop_note(n) and "fokus ke dataset" not in mem.working_memory()
    for i in range(300):
        mem.add_note("catatan panjang " * 20)
    assert len(mem.working_memory(max_chars=2000)) <= 2000


def test_last_session_skips_empty_sessions(mem):
    assert mem.last_session() is None  # belum ada sesi
    s1 = mem.new_session()
    mem.add_message(s1, "user", "isi")
    mem.new_session()  # sesi kosong lebih baru
    mem.new_session()
    assert mem.last_session() == s1
