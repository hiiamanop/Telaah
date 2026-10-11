"""Tampilan terminal (rich): panel, tabel, spinner, perintah /. Hanya tampilan; tanpa LLM dan tanpa jaringan.

Semua teks dinamis (kutipan paper, balasan model) dirender sebagai Text, bukan markup rich, supaya
'[S1]' dan kutipan verbatim tampil apa adanya.
"""
import os

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import config

HELP = [("/bantuan", "daftar perintah"),
        ("/koleksi", "paper di proyek dan status index"),
        ("/memori", "catatan dan keputusan yang tersimpan"),
        ("/riwayat <kata>", "cari di percakapan, jawaban, keputusan, catatan lama"),
        ("/sesi", "daftar sesi (lanjutkan dengan: telaah --resume ID)"),
        ("/proyek", "daftar proyek di folder data"),
        ("/keluar", "selesai; ringkasan sesi dibuat otomatis")]
EXIT = {"/keluar", "/exit", "exit"}


def style_result(text):
    """Teks hasil tanya_koleksi -> Text berwarna per baris (isi tetap persis)."""
    out = Text()
    for line in text.split("\n"):
        s = line.lstrip()
        style = ("dim italic" if s.startswith(">") else "bold" if s == "Bukti:" else
                 "bold red" if s.startswith("PERINGATAN") else
                 "yellow" if s.startswith(("Bukti tidak cukup", "Tidak ada klaim", "Tidak ada di bukti")) else "")
        out.append(line + "\n", style=style)
    out.rstrip()
    return out


class UI:
    def __init__(self, console=None):
        self.c = console or Console()
        self._st = None

    # --- status
    def start_thinking(self):
        self._st = self.c.status("Berpikir…", spinner="dots")
        self._st.start()

    def stop_thinking(self):
        if self._st:
            self._st.stop()
            self._st = None

    # --- alur percakapan
    def banner(self, proj, sid, resumed=0):
        body = Text()
        body.append(f"proyek  {proj.name}\n", style="bold")
        body.append(f"sesi    #{sid}" + (f" (dilanjutkan, {resumed} pesan dimuat)" if resumed else "") + "\n")
        body.append("ketik /bantuan untuk perintah, /keluar untuk selesai", style="dim")
        self.c.print(Panel(body, title="Telaah", border_style="cyan", expand=False))

    def reply(self, text):
        self.c.print(Markdown(text))
        self.c.print()

    def show_result(self, text):
        """Hasil tanya_koleksi, dicetak program (bukan model)."""
        self.c.print(Panel(style_result(text), title="Jawaban berbukti", border_style="green"))

    def tool_call(self, name, args):
        brief = ", ".join(f"{k}={str(v)[:40]!r}" for k, v in args.items())
        self.c.print(Text(f"• {name}({brief})", style="dim"))

    def error(self, msg):
        self.c.print(Text(msg, style="red"))

    def notice(self, msg):
        self.c.print(Text(msg, style="dim"))

    def summary(self, text):
        self.c.print(Panel(Text(text), title="Ringkasan sesi (dibuat model, belum diverifikasi)", border_style="blue"))

    def confirm(self, text):
        """Tanya y/N. Spinner dijeda selama bertanya. EOF (stdin habis) dihitung menolak."""
        live = self._st
        if live:
            live.stop()
        try:
            self.c.print(Panel(Text(text), title="Konfirmasi", border_style="yellow"))
            try:
                return input("Lanjutkan? [y/N] ").strip().lower() in ("y", "ya")
            except EOFError:
                return False
        finally:
            if live:
                live.start()

    # --- tabel
    def _table(self, title, cols, rows):
        t = Table(title=title, title_justify="left", show_lines=False)
        for c in cols:
            t.add_column(c, overflow="fold")
        for r in rows:
            t.add_row(*[Text(str(x)) for x in r])
        self.c.print(t if rows else Text(f"{title}: (kosong)", style="dim"))

    def koleksi(self, info):
        self.c.print(Text(f"{info['total_pdf']} paper, {info['indexed']} ter-index", style="bold"))
        self._table("Koleksi", ["judul", "tahun", "penulis pertama", "index"],
                    [(r["title"] or r["file"], r["year"] or "-", r["first_author"] or "-",
                      "ya" if r["indexed"] else "belum") for r in info["daftar"]])

    def sesi(self, rows):
        self._table("Sesi", ["id", "mulai", "pesan", "judul / ringkasan"],
                    [(s["id"], s["started"][:16], s["n"], (s["summary"] or s["title"])[:90]) for s in rows])

    def riwayat(self, rows):
        self._table("Hasil pencarian", ["jenis", "id", "cuplikan"],
                    [(r["kind"], r["ref"], r["snippet"]) for r in rows])

    def memori(self, notes, decisions):
        self._table("Catatan", ["id", "waktu", "isi"], [(n["id"], n["time"][:16], n["text"]) for n in notes])
        self._table("Keputusan", ["id", "waktu", "isi", "jawaban"],
                    [(d["id"], d["time"][:16], d["text"], f"#{d['answer_id']}") for d in decisions])

    def proyek(self, names, current):
        self._table("Proyek", ["nama", ""], [(n, "aktif" if n == current else "") for n in names])

    def bantuan(self):
        self._table("Perintah", ["perintah", "fungsi"], HELP)


def list_projects():
    try:
        return sorted(d for d in os.listdir(config.PROJECTS_DIR)
                      if os.path.isdir(f"{config.PROJECTS_DIR}/{d}"))
    except OSError:
        return []


def handle_command(line, ui, proj, mem, tools):
    """Perintah '/...'. Return 'keluar', True (sudah ditangani), atau False (bukan perintah; teruskan ke agen)."""
    if line in EXIT:
        return "keluar"
    if not line.startswith("/"):
        return False
    cmd, _, arg = line.partition(" ")
    arg = arg.strip()
    if cmd == "/bantuan":
        ui.bantuan()
    elif cmd == "/koleksi":
        ui.koleksi(tools["daftar_koleksi"].fn())
    elif cmd == "/memori":
        ui.memori(mem.notes(), mem.decisions())
    elif cmd == "/riwayat":
        if arg:
            ui.riwayat(mem.search(arg))
        else:
            ui.notice("pakai: /riwayat <kata kunci>")
    elif cmd == "/sesi":
        ui.sesi(mem.sessions())
    elif cmd == "/proyek":
        ui.proyek(list_projects(), proj.name)
    else:
        ui.notice(f"perintah tidak dikenal: {cmd}. Ketik /bantuan.")
    return True


def make_prompt(history_path):
    """Fungsi ask(prefix) -> str. prompt_toolkit bila terminal interaktif (riwayat berkas, autocomplete
    /perintah, Alt+Enter = baris baru); selain itu input() biasa, supaya pipa dan tes tetap jalan."""
    import sys
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return lambda prefix="anda> ": input(prefix)
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings

    kb = KeyBindings()

    @kb.add("escape", "enter")  # Alt+Enter / Esc lalu Enter: baris baru
    def _(event):
        event.current_buffer.insert_text("\n")

    try:
        os.makedirs(os.path.dirname(history_path), exist_ok=True)
        if not os.path.exists(history_path):  # buat dulu dengan izin 0600; berisi ketikan pengguna
            os.close(os.open(history_path, os.O_CREAT | os.O_WRONLY, 0o600))
        os.chmod(history_path, 0o600)
        hist = FileHistory(history_path)
    except OSError:
        hist = None
    session = PromptSession(history=hist, key_bindings=kb, multiline=False, enable_history_search=True,
                            completer=WordCompleter([c for c, _ in HELP if " " not in c] + ["/riwayat"],
                                                    sentence=True),
                            complete_while_typing=False)
    return lambda prefix="anda> ": session.prompt(prefix)
