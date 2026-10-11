import io

from rich.console import Console

from telaah import agent
from telaah import config
from telaah import tui
from telaah.memory import Memory


def make_ui():
    buf = io.StringIO()
    return tui.UI(Console(file=buf, width=100, force_terminal=False, color_system=None)), buf


def test_result_panel_keeps_brackets_and_quotes_verbatim():
    ui, buf = make_ui()
    ui.show_result('- klaim [S1]\n    > "kutipan [S2] asli"\nBukti:\n  [S1] Wei 2025, hlm. 3 (jarak 0.2)')
    out = buf.getvalue()
    assert "[S1]" in out and '"kutipan [S2] asli"' in out and "Jawaban berbukti" in out  # tak dimakan markup rich


def test_tables_render_and_empty_state():
    ui, buf = make_ui()
    ui.koleksi({"total_pdf": 2, "indexed": 1, "daftar": [
        {"title": "Judul [x]", "file": "f", "year": 2025, "first_author": "Ada", "indexed": True},
        {"title": "", "file": "g.pdf", "year": None, "first_author": "", "indexed": False}]})
    ui.memori([], [])
    out = buf.getvalue()
    assert "2 paper, 1 ter-index" in out and "Judul [x]" in out and "g.pdf" in out and "belum" in out
    assert "Catatan: (kosong)" in out and "Keputusan: (kosong)" in out


def test_commands_do_not_reach_agent_and_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    proj = config.Project("a").ensure()
    mem = Memory(proj)
    sid = mem.new_session()
    mem.add_note("fokus NYT")
    mem.add_message(sid, "user", "bahas PGExplainer")
    tools = {t.name: t for t in agent.build_tools(proj, mem, sid)}
    ui, buf = make_ui()
    h = lambda line: tui.handle_command(line, ui, proj, mem, tools)
    assert h("halo apa kabar") is False and h("") is False       # bukan perintah -> ke agen
    assert h("/keluar") == "keluar" and h("exit") == "keluar"
    for cmd in ("/bantuan", "/koleksi", "/memori", "/sesi", "/proyek", "/riwayat PGExplainer", "/riwayat", "/ngawur"):
        assert h(cmd) is True
    out = buf.getvalue()
    assert "fokus NYT" in out and "PGExplainer" in out and "perintah tidak dikenal: /ngawur" in out
    assert "pakai: /riwayat" in out and "aktif" in out


def test_confirm_refuses_on_eof_and_accepts_y(monkeypatch):
    ui, _ = make_ui()
    monkeypatch.setattr("builtins.input", lambda p="": "y")
    assert ui.confirm("unduh?") is True
    monkeypatch.setattr("builtins.input", lambda p="": "")
    assert ui.confirm("unduh?") is False
    def eof(p=""): raise EOFError
    monkeypatch.setattr("builtins.input", eof)
    assert ui.confirm("unduh?") is False


def test_make_prompt_falls_back_to_input_without_tty(tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda p="": f"dibaca:{p}")
    ask = tui.make_prompt(str(tmp_path / ".history"))   # pytest: stdin bukan tty
    assert ask() == "dibaca:anda> "
    assert not (tmp_path / ".history").exists()


def test_on_tool_hook_called_before_tool_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    proj = config.Project("a").ensure()
    mem = Memory(proj)
    sid = mem.new_session()
    seen = []
    call = {"id": "c1", "type": "function", "function": {"name": "t", "arguments": '{"x": "1"}'}}
    replies = iter([{"content": None, "tool_calls": [call]}, {"content": "ok"}])
    t = agent.Tool("t", "d", {"x": {"type": "string"}}, [], lambda x: seen.append(("jalan", x)) or "r")
    ag = agent.Agent(mem, sid, [t], "SYS", chat=lambda m, tools=None: next(replies),
                     on_tool=lambda n, a: seen.append(("hook", n, a)))
    ag.turn("x")
    assert seen == [("hook", "t", {"x": "1"}), ("jalan", "1")]
