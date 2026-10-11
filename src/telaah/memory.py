"""Ingatan proyek: sesi, pesan, jawaban berbukti, keputusan, catatan. SQLite (stdlib) di data/<proyek>/memory.db.

Memori BUKAN bukti: ringkasan dan catatan hanya petunjuk arah kerja. Klaim riset wajib lewat rag.ask.
"""
import json
import os
import re
import sqlite3
import time

VERSION = 2

SCHEMA = """
create table sessions(
  id integer primary key, started text not null, title text not null default '',
  summary text not null default '', summary_by text not null default '');
create table messages(
  id integer primary key, session_id integer not null references sessions(id), seq integer not null,
  role text not null, content text, tool_calls text, tool_call_id text, name text, created text not null,
  unique(session_id, seq));
create table answers(
  id integer primary key, session_id integer references sessions(id), time text not null,
  question text not null, status text not null, answer text not null default '', via text not null default '',
  max_dist real, best_dist real, evidence text not null default '[]',
  cited text not null default '[]', invalid_cites text not null default '[]',
  claims text not null default '[]');
create table decisions(
  id integer primary key, time text not null, text text not null,
  answer_id integer not null references answers(id), evidence text not null);
create table notes(
  id integer primary key, time text not null, text text not null, active integer not null default 1);
create virtual table search_fts using fts5(text, kind unindexed, ref unindexed);
"""


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def fts_query(q):
    """Teks bebas -> query FTS5 aman (tiap kata di-quote, AND). Kosong -> None."""
    toks = re.findall(r"\w+", q)
    return " ".join('"%s"' % t for t in toks) if toks else None


class Memory:
    def __init__(self, proj):
        os.makedirs(proj.dir, exist_ok=True)
        self.path = f"{proj.dir}/memory.db"
        new = not os.path.exists(self.path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        if new:
            os.chmod(self.path, 0o600)  # berisi pertanyaan dan draf pengguna
        self.db.execute("pragma journal_mode=wal")
        self.db.execute("pragma foreign_keys=on")
        v = self.db.execute("pragma user_version").fetchone()[0]
        if v == 0:
            with self.db:
                self.db.executescript(SCHEMA)
                self.db.execute(f"pragma user_version={VERSION}")
        elif v == 1:  # v1 -> v2: klaim terverifikasi per jawaban
            with self.db:
                self.db.execute("alter table answers add column claims text not null default '[]'")
                self.db.execute(f"pragma user_version={VERSION}")
        elif v != VERSION:
            raise SystemExit(f"{self.path}: skema v{v}, aplikasi mengharapkan v{VERSION}")

    def close(self):
        self.db.close()

    # --- sesi & pesan
    def new_session(self, title=""):
        with self.db:
            return self.db.execute("insert into sessions(started, title) values(?,?)", (now(), title)).lastrowid

    def last_session(self):
        """Sesi terakhir yang punya pesan; sesi kosong (dibuka lalu langsung ditutup) dilewati."""
        return self.db.execute("select max(session_id) from messages").fetchone()[0]

    def sessions(self, limit=20):
        return [dict(r) for r in self.db.execute(
            "select s.id, s.started, s.title, s.summary, (select count(*) from messages where session_id=s.id) n "
            "from sessions s order by s.id desc limit ?", (limit,))]

    def set_title(self, sid, title):
        with self.db:
            self.db.execute("update sessions set title=? where id=? and title=''", (title, sid))

    def set_summary(self, sid, summary, title=None):
        with self.db:
            self.db.execute("update sessions set summary=?, summary_by='model', title=coalesce(?, title) where id=?",
                            (summary, title, sid))

    def add_message(self, sid, role, content=None, tool_calls=None, tool_call_id=None, name=None):
        with self.db:
            seq = self.db.execute("select coalesce(max(seq),0)+1 from messages where session_id=?", (sid,)).fetchone()[0]
            mid = self.db.execute(
                "insert into messages(session_id, seq, role, content, tool_calls, tool_call_id, name, created) "
                "values(?,?,?,?,?,?,?,?)",
                (sid, seq, role, content, json.dumps(tool_calls) if tool_calls else None,
                 tool_call_id, name, now())).lastrowid
            if role in ("user", "assistant") and content:  # hasil tool (bukti besar) tak diindeks
                self.db.execute("insert into search_fts(text, kind, ref) values(?,?,?)", (content, "message", str(mid)))
        return mid

    def history(self, sid):
        """Pesan sesi dalam format chat API (siap dikirim ulang ke LLM)."""
        out = []
        for r in self.db.execute("select * from messages where session_id=? order by seq", (sid,)):
            m = {"role": r["role"], "content": r["content"]}
            if r["tool_calls"]:
                m["tool_calls"] = json.loads(r["tool_calls"])
            if r["tool_call_id"]:
                m["tool_call_id"] = r["tool_call_id"]
            if r["name"]:
                m["name"] = r["name"]
            out.append(m)
        return out

    # --- jawaban berbukti & keputusan
    def add_answer(self, rec, sid=None):
        """rec = dict keluaran rag.ask. Return id jawaban."""
        with self.db:
            aid = self.db.execute(
                "insert into answers(session_id, time, question, status, answer, via, max_dist, best_dist, "
                "evidence, cited, invalid_cites, claims) values(?,?,?,?,?,?,?,?,?,?,?,?)",
                (sid, rec["time"], rec["question"], rec["status"], rec.get("answer", ""), rec.get("via", ""),
                 rec.get("max_dist"), rec.get("best_dist"), json.dumps(rec.get("evidence", []), ensure_ascii=False),
                 json.dumps(rec.get("cited", [])), json.dumps(rec.get("invalid_cites", [])),
                 json.dumps(rec.get("claims", []), ensure_ascii=False))).lastrowid
            self.db.execute("insert into search_fts(text, kind, ref) values(?,?,?)",
                            (rec["question"] + "\n" + rec.get("answer", ""), "answer", str(aid)))
        return aid

    def answer(self, aid):
        r = self.db.execute("select * from answers where id=?", (aid,)).fetchone()
        if not r:
            return None
        d = dict(r)
        for k in ("evidence", "cited", "invalid_cites", "claims"):
            d[k] = json.loads(d[k])
        return d

    def add_decision(self, text, answer_id):
        """Keputusan wajib menunjuk jawaban berstatus 'answered'; bukti disalin agar tetap utuh."""
        a = self.answer(answer_id)
        if not a or a["status"] != "answered":
            raise ValueError(f"keputusan butuh jawaban berbukti; id {answer_id} tidak ada atau tanpa bukti")
        with self.db:
            did = self.db.execute("insert into decisions(time, text, answer_id, evidence) values(?,?,?,?)",
                                  (now(), text, answer_id, json.dumps(a["evidence"], ensure_ascii=False))).lastrowid
            self.db.execute("insert into search_fts(text, kind, ref) values(?,?,?)", (text, "decision", str(did)))
        return did

    def decisions(self):
        return [dict(r) for r in self.db.execute("select id, time, text, answer_id from decisions order by id")]

    # --- catatan
    def add_note(self, text):
        with self.db:
            nid = self.db.execute("insert into notes(time, text) values(?,?)", (now(), text)).lastrowid
            self.db.execute("insert into search_fts(text, kind, ref) values(?,?,?)", (text, "note", str(nid)))
        return nid

    def notes(self):
        return [dict(r) for r in self.db.execute("select id, time, text from notes where active=1 order by id")]

    def drop_note(self, nid):
        with self.db:
            return self.db.execute("update notes set active=0 where id=? and active=1", (nid,)).rowcount == 1

    # --- pencarian & memori kerja
    def search(self, q, limit=8):
        fq = fts_query(q)
        if not fq:
            return []
        return [dict(r) for r in self.db.execute(
            "select kind, ref, snippet(search_fts, 0, '[', ']', '…', 14) snippet from search_fts "
            "where search_fts match ? order by bm25(search_fts) limit ?", (fq, limit))]

    def working_memory(self, max_chars=6000):
        """Teks ringkas untuk prompt sistem: catatan, keputusan, 3 ringkasan sesi terakhir. Dipotong ke anggaran."""
        parts = []
        if n := self.notes():
            parts.append("Catatan aktif:\n" + "\n".join(f"- #{x['id']} {x['text']}" for x in n))
        if d := self.decisions():
            parts.append("Keputusan riset (berdasar jawaban berbukti):\n"
                         + "\n".join(f"- #{x['id']} {x['text']} (jawaban #{x['answer_id']})" for x in d))
        ss = [s for s in self.sessions(3) if s["summary"]]
        if ss:
            parts.append("Ringkasan sesi lalu (dibuat model, belum diverifikasi, BUKAN bukti):\n"
                         + "\n".join(f"- sesi #{s['id']} {s['started'][:10]}: {s['summary']}" for s in ss))
        out = "\n\n".join(parts)
        return out if len(out) <= max_chars else out[:max_chars - 20] + "\n…(dipotong)"
