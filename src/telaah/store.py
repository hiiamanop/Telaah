"""Buka collection Chroma proyek: jarak cosine, model embedding dicatat dan dijaga konsisten."""
import chromadb

from . import config


def open_collection(proj, create=False, reset=False):
    """create=False: collection harus sudah ada (raise bila belum). reset=True: hapus dulu."""
    db = chromadb.PersistentClient(path=proj.chroma)
    if reset:
        try:
            db.delete_collection(config.COLLECTION)
        except Exception:  # belum ada
            pass
    model = config.OPENROUTER_EMBED_MODEL
    if create:
        col = db.get_or_create_collection(
            config.COLLECTION, configuration={"hnsw": {"space": "cosine"}},
            metadata={"embed_model": model})
    else:
        col = db.get_collection(config.COLLECTION)
    have = (col.metadata or {}).get("embed_model")
    if col.count() and have != model:
        raise SystemExit(f"index proyek '{proj.name}' dibuat dengan model {have or '(tak tercatat)'}, "
                         f"sekarang {model}. Vektor tak cocok: jalankan ingest.py -p {proj.name} --reindex")
    return col
