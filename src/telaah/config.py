"""Config RAG: baca .env via stdlib; kunci OpenRouter dari env/.env, atau dari `telaah --login`."""
import os
import re

from . import auth


def load_env(path=".env"):
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


load_env()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY") or auth.load_key() or ""  # env/.env menang atas hasil login
OPENROUTER_EMBED_MODEL = os.environ.get("OPENROUTER_EMBED_MODEL", "qwen/qwen3-embedding-8b")
# id disematkan persis (bukan alias -latest yang bisa berganti); lolos tests/eval_scope.py 14/14 dan verifikasi kutipan 8/8
OPENROUTER_CHAT_MODEL = os.environ.get("OPENROUTER_CHAT_MODEL", "deepseek/deepseek-v4.1-flash")
NINEROUTER_URL = os.environ.get("NINEROUTER_URL", "http://localhost:20128")
NINEROUTER_API_KEY = os.environ.get("NINEROUTER_API_KEY", "")
NINEROUTER_MODEL = os.environ.get("NINEROUTER_MODEL", "main")
LLM_BACKEND = os.environ.get("LLM_BACKEND", "openrouter")  # openrouter | ninerouter
ELSEVIER_API_KEY = os.environ.get("ELSEVIER_API_KEY", "")
OLLAMA_URL =os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")
PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "./data")
DEFAULT_PROJECT = "default"
COLLECTION = "papers"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
TOP_K = 5
EMBED_BATCH = 64  # chunk per request embedding
# Jarak cosine maks. agar chunk dianggap bukti. Terukur (qwen3-embedding-8b, 3 paper):
# pertanyaan relevan terbaik 0.18-0.30, tak relevan 0.50-0.68. Ukur ulang bila ganti model embedding.
MAX_DIST = float(os.environ.get("MAX_DIST", "0.40"))

class Project:
    """Satu proyek riset = satu folder data/<nama>/ (papers, chroma, csv, bib) terisolasi."""

    def __init__(self, name):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):  # cegah path traversal
            raise ValueError(f"nama proyek tidak valid: {name!r} (huruf/angka/_/-, maks 64)")
        self.name = name
        self.dir = f"{PROJECTS_DIR}/{name}"
        self.papers = f"{self.dir}/papers"
        self.chroma = f"{self.dir}/chroma"
        self.literature = f"{self.dir}/literature.csv"
        self.bib = f"{self.dir}/references.bib"

    def ensure(self):
        os.makedirs(self.papers, exist_ok=True)
        return self

def add_project_arg(parser):
    parser.add_argument("-p", "--project", default=DEFAULT_PROJECT,
                        help=f"nama proyek (default: {DEFAULT_PROJECT})")

def project_from(args):
    try:
        return Project(args.project)
    except ValueError as e:
        raise SystemExit(str(e))
