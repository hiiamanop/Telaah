import os
import stat
import urllib.error

import pytest

from telaah import auth


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    return tmp_path


def test_credentials_private_and_roundtrip(home):
    assert auth.load_key() is None
    auth.save_key("sk-test-1")
    p = auth.cred_path()
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600 and stat.S_IMODE(os.stat(os.path.dirname(p)).st_mode) == 0o700
    assert auth.load_key() == "sk-test-1"
    os.chmod(p, 0o644)
    auth.save_key("sk-test-2")  # menimpa berkas longgar -> kembali 0600
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600 and auth.load_key() == "sk-test-2"
    assert auth.clear_key() and auth.load_key() is None and not auth.clear_key()
    open(p, "w").write("bukan json")
    assert auth.load_key() is None  # rusak = dianggap belum login, tanpa crash


def _http(code):
    def get(k): raise urllib.error.HTTPError("u", code, "x", {}, None)
    return get

def test_connection_ok_and_rejections():
    seen = {}
    auth.test_connection("sk-or-ok", lambda k: seen.update(k=k) or 200)
    assert seen["k"] == "sk-or-ok"
    for bad in ("", "  ", "a b", None):
        with pytest.raises(auth.LoginError, match="kosong"):
            auth.test_connection(bad, lambda k: 200)
    for code in (401, 403):
        with pytest.raises(auth.LoginError, match="ditolak"):
            auth.test_connection("k", _http(code))
    with pytest.raises(auth.LoginError, match="HTTP 500"):
        auth.test_connection("k", _http(500))
    def net(k): raise urllib.error.URLError("offline")
    with pytest.raises(auth.LoginError, match="tidak bisa menghubungi"):
        auth.test_connection("k", net)

def test_login_saves_only_after_passing():
    key = auth.login(say=lambda m: None, ask=lambda p: " sk-or-1 \n", get=lambda k: 200)
    assert key == "sk-or-1" and auth.load_key() == "sk-or-1"
    with pytest.raises(auth.LoginError):  # gagal tidak menimpa kunci lama
        auth.login(say=lambda m: None, ask=lambda p: "sk-or-buruk", get=_http(401))
    assert auth.load_key() == "sk-or-1"

def test_failed_login_stores_nothing():
    with pytest.raises(auth.LoginError):
        auth.login(say=lambda m: None, ask=lambda p: "sk-or-buruk", get=_http(401))
    assert auth.load_key() is None

class _UI:
    def __init__(self): self.out = []
    def notice(self, m): self.out.append(m)
    def error(self, m): self.out.append("ERR " + m)

def test_gate_blocks_bad_env_key_and_passes_good(monkeypatch):
    from telaah import cli, config
    monkeypatch.setenv("OPENROUTER_API_KEY", "dari-env")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "dari-env")
    monkeypatch.setattr(auth, "_get", _http(401))
    ui = _UI()
    assert cli.ensure_login(ui) is False and "env/.env" in ui.out[0]
    monkeypatch.setattr(auth, "_get", lambda k: 200)
    assert cli.ensure_login(_UI()) is True

def test_gate_non_tty_without_key_refuses(monkeypatch):
    from telaah import cli, config
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    ui = _UI()  # pytest: stdin bukan TTY
    assert cli.ensure_login(ui) is False and "--login" in ui.out[0]

def test_config_prefers_env_over_saved_key(monkeypatch, tmp_path):
    import importlib
    from telaah import config
    auth.save_key("dari-login")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # tanpa .env
    assert importlib.reload(config).OPENROUTER_API_KEY == "dari-login"
    monkeypatch.setenv("OPENROUTER_API_KEY", "dari-env")
    assert importlib.reload(config).OPENROUTER_API_KEY == "dari-env"
    monkeypatch.delenv("OPENROUTER_API_KEY")
    importlib.reload(config)


def test_default_chat_model_is_pinned_not_alias():
    import os
    from telaah import config
    if "OPENROUTER_CHAT_MODEL" not in os.environ:
        assert config.OPENROUTER_CHAT_MODEL == "deepseek/deepseek-v4.1-flash"
    assert "latest" not in "deepseek/deepseek-v4.1-flash"
