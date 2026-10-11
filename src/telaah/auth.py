"""Kunci API OpenRouter: dimasukkan pengguna saat onboarding, dites ke OpenRouter, disimpan di
~/.config/telaah/credentials.json (0600, di luar folder proyek)."""
import json
import os
import urllib.error
import urllib.request

CHECK_URL = "https://openrouter.ai/api/v1/key"  # 200 bila kunci sah, 401 bila tidak


class LoginError(Exception):
    pass


def cred_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "telaah", "credentials.json")


def save_key(key):
    path = cred_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"openrouter_api_key": key}, f)
    os.chmod(path, 0o600)  # berkas lama dengan izin longgar ikut diperketat


def load_key():
    try:
        with open(cred_path()) as f:
            k = json.load(f).get("openrouter_api_key")
        return k if isinstance(k, str) and k else None
    except (OSError, ValueError, AttributeError):
        return None


def clear_key():
    try:
        os.remove(cred_path())
        return True
    except OSError:
        return False


def _get(key):
    req = urllib.request.Request(CHECK_URL, headers={"Authorization": f"Bearer {key}", "User-Agent": "telaah"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


def test_connection(key, get=None):
    """Raise LoginError bila kunci kosong, ditolak, atau OpenRouter tak terjangkau."""
    get = get or _get
    if not key or any(c.isspace() for c in key):
        raise LoginError("kunci kosong atau mengandung spasi")
    try:
        get(key)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise LoginError("kunci ditolak OpenRouter (salah, dicabut, atau dinonaktifkan)")
        raise LoginError(f"OpenRouter membalas HTTP {e.code}")
    except (urllib.error.URLError, OSError) as e:
        raise LoginError(f"tidak bisa menghubungi OpenRouter: {e}")


def login(say=print, ask=None, get=None):
    """Minta kunci (tersembunyi), tes koneksi, simpan hanya bila lolos. Return kunci."""
    if ask is None:
        import getpass
        ask = getpass.getpass
    say("Buat kunci di https://openrouter.ai/keys lalu tempel di sini (ketikan tidak ditampilkan).")
    key = ask("OpenRouter API key: ").strip()
    say("Menguji koneksi ke OpenRouter...")
    test_connection(key, get)
    save_key(key)
    return key
