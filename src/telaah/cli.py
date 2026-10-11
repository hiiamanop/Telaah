#!/usr/bin/env python3
"""Research partner interaktif. Percakapan dan memori tersimpan di data/<proyek>/memory.db,
di folder tempat perintah dijalankan.

Pakai:  telaah [-p proyek] [--resume [id]] [--sesi]
Ketik /keluar untuk selesai (ringkasan sesi dibuat otomatis).
"""
import argparse
import os
import sys

from . import agent, auth, config, memory, tui


def ensure_login(ui, force=False):
    """Gerbang masuk: kunci OpenRouter harus ada DAN lolos tes koneksi. Return True bila boleh lanjut."""
    key = config.OPENROUTER_API_KEY
    if key and not force:
        try:
            auth.test_connection(key)
            return True
        except auth.LoginError as e:
            if os.environ.get("OPENROUTER_API_KEY"):  # env/.env menang atas berkas; memasukkan ulang tak akan dipakai
                ui.error(f"OPENROUTER_API_KEY di env/.env tidak lolos: {e}")
                return False
            ui.error(f"Kunci tersimpan tidak lolos: {e}")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        ui.error("Belum terhubung ke OpenRouter. Jalankan di terminal: telaah --login (atau isi OPENROUTER_API_KEY di .env)")
        return False
    if not key or force:
        ui.notice("Aplikasi ini memakai OpenRouter untuk model bahasa dan embedding.")
    for _ in range(3):
        try:
            config.OPENROUTER_API_KEY = auth.login(say=ui.notice)
        except auth.LoginError as e:
            ui.error(f"Gagal: {e}")
            continue
        except (EOFError, KeyboardInterrupt):  # Ctrl+D / Ctrl+C = batal
            print()
            return False
        ui.notice(f"Terhubung. Kunci tersimpan di {auth.cred_path()} (hanya Anda yang bisa membaca).")
        return True
    return False


def main():
    a = argparse.ArgumentParser()
    config.add_project_arg(a)
    a.add_argument("--resume", nargs="?", const=0, type=int, metavar="ID",
                   help="lanjutkan sesi terakhir, atau sesi ID")
    a.add_argument("--sesi", action="store_true", help="daftar sesi lalu keluar")
    a.add_argument("--login", action="store_true", help="masukkan (ulang) API key OpenRouter lalu keluar")
    a.add_argument("--logout", action="store_true", help="hapus kunci OpenRouter yang tersimpan lalu keluar")
    a = a.parse_args()
    ui = tui.UI()
    if a.logout:
        ui.notice("Kunci dihapus." if auth.clear_key() else "Tidak ada kunci tersimpan.")
        return
    if a.login:
        ensure_login(ui, force=True)
        return
    proj = config.project_from(a).ensure()
    mem = memory.Memory(proj)

    if a.sesi:
        ui.sesi(mem.sessions())
        return

    if config.LLM_BACKEND == "openrouter" and not ensure_login(ui):
        return
    sid, history = None, []
    if a.resume is not None:
        sid = a.resume or mem.last_session()
        if sid and mem.db.execute("select 1 from sessions where id=?", (sid,)).fetchone():
            history = agent.trim_history(mem.history(sid))
        else:
            sys.exit(f"sesi {a.resume or '(terakhir)'} tidak ada. Lihat: telaah -p {proj.name} --sesi")
    sid = sid or mem.new_session()

    wm = mem.working_memory()
    system = agent.SYSTEM + (f"\n\nMEMORI PROYEK '{proj.name}':\n{wm}" if wm else "")
    tools = agent.build_tools(proj, mem, sid, out=ui.show_result)
    ag = agent.Agent(mem, sid, tools, system, confirm=ui.confirm, history=history, on_tool=ui.tool_call)
    by_name = {t.name: t for t in tools}
    ask = tui.make_prompt(f"{proj.dir}/.history")
    ui.banner(proj, sid, len(history))
    try:
        while True:
            try:
                line = ask().strip()
            except EOFError:
                break
            if not line:
                continue
            handled = tui.handle_command(line, ui, proj, mem, by_name)
            if handled == "keluar":
                break
            if handled:
                continue
            try:
                ui.start_thinking()
                try:
                    reply = ag.turn(line)
                finally:
                    ui.stop_thinking()
            except KeyboardInterrupt:
                ui.notice("(dibatalkan)")
                continue
            except Exception as e:
                ui.error(f"gagal: {e}")
                continue
            if reply:
                ui.reply(reply)
    except KeyboardInterrupt:
        print()
    finally:
        try:
            ui.start_thinking()
            try:
                s = agent.summarize_session(mem, sid)
            finally:
                ui.stop_thinking()
            if s:
                ui.summary(s)
        except Exception as e:
            ui.notice(f"(ringkasan sesi gagal: {str(e)[:80]}; percakapan tetap tersimpan)")
        mem.close()
