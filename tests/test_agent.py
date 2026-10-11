import json

import pytest

from telaah import agent
from telaah import config
from telaah.memory import Memory


def call(name, args, cid="c1"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class FakeLLM:
    """Giliran berurutan; mencatat pesan yang diterima."""
    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def __call__(self, messages, tools=None):
        self.seen.append((list(messages), tools))
        return self.replies.pop(0)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    proj = config.Project("a").ensure()
    mem = Memory(proj)
    return proj, mem, mem.new_session()


def make(env, llm, tools, confirm=lambda t: True, history=()):
    proj, mem, sid = env
    return agent.Agent(mem, sid, tools, "SYS", chat=llm, confirm=confirm, out=lambda t: None, history=history)


def tool(name, fn, describe=None):
    return agent.Tool(name, "d", {"x": {"type": "string"}}, [], fn, describe)


def test_tool_loop_persists_everything(env):
    llm = FakeLLM({"content": None, "tool_calls": [call("t", {"x": "1"})]}, {"content": "selesai"})
    ag = make(env, llm, [tool("t", lambda x: f"hasil {x}")])
    assert ag.turn("halo") == "selesai"
    h = env[1].history(env[2])
    assert [m["role"] for m in h] == ["user", "assistant", "tool", "assistant"]
    assert h[2]["content"] == "hasil 1" and h[2]["tool_call_id"] == "c1"
    assert llm.seen[1][0][-1]["role"] == "tool"  # hasil tool dikirim balik ke model


def test_confirm_refusal_does_not_run_tool(env):
    ran = []
    llm = FakeLLM({"content": None, "tool_calls": [call("t", {})]}, {"content": "ok"})
    ag = make(env, llm, [tool("t", lambda: ran.append(1), describe=lambda a: "yakin?")], confirm=lambda t: False)
    ag.turn("unduh")
    assert ran == [] and "ditolak" in env[1].history(env[2])[2]["content"]


def test_bad_args_unknown_tool_and_tool_crash_reported_not_raised(env):
    llm = FakeLLM({"content": None, "tool_calls": [
        {"id": "a", "type": "function", "function": {"name": "t", "arguments": "{bukan json"}},
        call("tidak_ada", {}, "b"), call("boom", {}, "c"), call("exit", {}, "d")]}, {"content": "ok"})
    def boom(): raise RuntimeError("meledak")
    def ex(): raise SystemExit("keluar paksa")
    ag = make(env, llm, [tool("t", lambda: "x"), tool("boom", boom), tool("exit", ex)])
    assert ag.turn("x") == "ok"
    res = [m["content"] for m in env[1].history(env[2]) if m["role"] == "tool"]
    assert "argumen tak valid" in res[0] and "tidak ada" in res[1] and "meledak" in res[2] and "keluar paksa" in res[3]


def test_step_limit_forces_text_answer(env):
    forever = {"content": None, "tool_calls": [call("t", {}, "c")]}
    llm = FakeLLM(*[dict(forever) for _ in range(agent.MAX_TOOL_CALLS + 1)], {"content": "terpaksa jawab"})
    runs = []
    ag = make(env, llm, [tool("t", lambda: runs.append(1) or "x")])
    assert ag.turn("loop") == "terpaksa jawab"
    assert len(runs) == agent.MAX_TOOL_CALLS and llm.seen[-1][1] is None  # putaran akhir tanpa tool


def test_large_tool_result_trimmed_for_llm_but_stored_whole(env):
    big = "x" * (agent.MAX_TOOL_CHARS + 500)
    llm = FakeLLM({"content": None, "tool_calls": [call("t", {})]}, {"content": "ok"})
    ag = make(env, llm, [tool("t", lambda: big)])
    ag.turn("a")
    sent = llm.seen[1][0][-1]["content"]
    assert len(sent) < len(big) and sent.endswith("(dipotong)")
    assert env[1].history(env[2])[2]["content"] == big


def test_clean_history_drops_incomplete_tool_groups():
    ok = [{"role": "assistant", "content": None, "tool_calls": [call("t", {}, "1")]},
          {"role": "tool", "content": "r", "tool_call_id": "1"}]
    cut = [{"role": "assistant", "content": None, "tool_calls": [call("t", {}, "2"), call("t", {}, "3")]},
           {"role": "tool", "content": "r", "tool_call_id": "2"}]  # hasil 3 hilang
    msgs = [{"role": "user", "content": "a"}] + ok + [{"role": "tool", "content": "yatim", "tool_call_id": "9"}] \
        + cut + [{"role": "user", "content": "b"}]
    out = agent.clean_history(msgs)
    assert [m["role"] for m in out] == ["user", "assistant", "tool", "user"]
    long = [{"role": "user", "content": str(i)} if i % 2 == 0 else {"role": "assistant", "content": "r"} for i in range(100)]
    t = agent.trim_history(long, 10)
    assert t[0]["role"] == "user" and len(t) <= 11


def test_resume_feeds_old_messages_to_llm(env):
    proj, mem, sid = env
    mem.add_message(sid, "user", "pertanyaan lama")
    mem.add_message(sid, "assistant", "jawaban lama")
    mem.close()
    mem2 = Memory(proj)
    llm = FakeLLM({"content": "baru"})
    ag = agent.Agent(mem2, sid, [], "SYS", chat=llm, history=agent.trim_history(mem2.history(sid)))
    ag.turn("lanjut")
    sent = [m["content"] for m in llm.seen[0][0]]
    assert sent == ["SYS", "pertanyaan lama", "jawaban lama", "lanjut"]
    assert [m["content"] for m in mem2.history(sid)][-2:] == ["lanjut", "baru"]


def test_summary_marks_model_and_skips_empty(env):
    proj, mem, sid = env
    assert agent.summarize_session(mem, sid, chat=lambda m: ("x", "t")) is None  # sesi kosong
    mem.add_message(sid, "user", "cari GNN")
    mem.add_message(sid, "assistant", "ok")
    assert agent.summarize_session(mem, sid, chat=lambda m: ("  bahas GNN  ", "t")) == "bahas GNN"
    s = mem.sessions()[0]
    assert s["summary"] == "bahas GNN"
    assert mem.db.execute("select summary_by from sessions").fetchone()[0] == "model"


def test_real_tools_decision_requires_answer_and_confirm(env):
    proj, mem, sid = env
    tools = {t.name: t for t in agent.build_tools(proj, mem, sid)}
    assert set(tools) >= {"tanya_koleksi", "catat_keputusan", "cari_dan_unduh", "index_koleksi", "cari_riwayat"}
    assert tools["catat_keputusan"].describe and tools["cari_dan_unduh"].describe and tools["index_koleksi"].describe
    assert tools["tanya_koleksi"].describe is None
    with pytest.raises(ValueError):
        tools["catat_keputusan"].fn("pakai X", 999)
    with pytest.raises(ValueError):
        tools["cari_dan_unduh"].fn("q", sumber="sumber_palsu")
    assert tools["daftar_koleksi"].fn()["total_pdf"] == 0
    tools["catat_catatan"].fn("fokus NYT")
    assert "fokus NYT" in mem.working_memory()


def _fake_grabber(seen, new=2, fail=False):
    class Fake:
        def run(self, q, out, n, **kw):
            seen.append((q, n, kw))
            if fail:
                raise RuntimeError("diblokir")
            return new, 1, 0
    return Fake


def test_cari_dan_unduh_indexes_new_pdfs_right_after_download(env, monkeypatch):
    proj, mem, sid = env
    seen, idx = [], []
    monkeypatch.setattr(agent, "OpenAlexGrabber", _fake_grabber(seen))
    monkeypatch.setattr(agent.ingest, "ingest_project", lambda p: idx.append(p) or (2, 0, 0))
    fn = {t.name: t for t in agent.build_tools(proj, mem, sid)}["cari_dan_unduh"].fn
    out = fn("gnn", n=5)
    assert seen == [("gnn", 5, {})] and len(idx) == 1 and "ieee" not in out
    assert "openalex: baru=2" in out and "Index: baru=2" in out
    with pytest.raises(ValueError):  # IEEE bukan lagi sumber
        fn("gnn", sumber="ieee")


def test_cari_dan_unduh_skips_index_when_nothing_new(env, monkeypatch):
    proj, mem, sid = env
    monkeypatch.setattr(agent, "OpenAlexGrabber", _fake_grabber([], new=0))
    monkeypatch.setattr(agent.ingest, "ingest_project", lambda p: 1 / 0)  # tidak boleh dipanggil
    fn = {t.name: t for t in agent.build_tools(proj, mem, sid)}["cari_dan_unduh"].fn
    assert "tidak ada yang di-index" in fn("gnn")


def test_cari_dan_unduh_keeps_download_when_index_or_source_fails(env, monkeypatch):
    proj, mem, sid = env
    monkeypatch.setattr(agent, "OpenAlexGrabber", _fake_grabber([]))
    def boom(p): raise RuntimeError("kredit habis")
    monkeypatch.setattr(agent.ingest, "ingest_project", boom)
    fn = {t.name: t for t in agent.build_tools(proj, mem, sid)}["cari_dan_unduh"].fn
    out = fn("gnn")
    assert "openalex: baru=2" in out and "Index GAGAL (kredit habis)" in out and "index_koleksi" in out
    monkeypatch.setattr(agent, "OpenAlexGrabber", _fake_grabber([], fail=True))
    assert "openalex: GAGAL (diblokir)" in fn("gnn") and "tidak ada yang di-index" in fn("gnn")

def test_scope_rule_stays_in_system_prompt():
    # perilaku sebenarnya diukur dengan tests/eval_scope.py (LLM sungguhan); ini cuma menjaga aturannya tak terhapus
    assert agent.REFUSAL in agent.SYSTEM and agent.SYSTEM.index("0. LINGKUP") < agent.SYSTEM.index("1. Pertanyaan")
    assert "JANGAN tolak" in agent.SYSTEM
