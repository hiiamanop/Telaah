"""HTTP client OpenRouter + fallback Ollama. Stdlib only."""
import json
import urllib.request

from . import config


def _post(url, payload, headers=None, timeout=120):
    req = urllib.request.Request(
        url, json.dumps(payload).encode(),
        {"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def embed(texts):
    """Embed via OpenRouter. Return list[list[float]]."""
    d = _post(f"https://openrouter.ai/api/v1/embeddings",
              {"model": config.OPENROUTER_EMBED_MODEL, "input": texts},
              {"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"})
    return [e["embedding"] for e in d["data"]]


def chat_openrouter(messages):
    d = _post("https://openrouter.ai/api/v1/chat/completions",
              {"model": config.OPENROUTER_CHAT_MODEL, "messages": messages},
              {"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"})
    return d["choices"][0]["message"]["content"]


def chat_ollama(messages):
    d = _post(f"{config.OLLAMA_URL}/api/chat",
              {"model": config.OLLAMA_MODEL, "messages": messages, "stream": False})
    return d["message"]["content"]


def chat_ninerouter(messages):
    d = _post(f"{config.NINEROUTER_URL}/v1/chat/completions",
              {"model": config.NINEROUTER_MODEL, "messages": messages, "stream": False},
              {"Authorization": f"Bearer {config.NINEROUTER_API_KEY}"})
    return d["choices"][0]["message"]["content"]


def chat_tools(messages, tools=None):
    """Satu giliran chat dengan tool calling. Return message dict (content, tool_calls).
    Tanpa fallback Ollama: model lokal kecil tak andal untuk tool calling."""
    if config.LLM_BACKEND == "ninerouter":
        url, key, model = (f"{config.NINEROUTER_URL}/v1/chat/completions",
                           config.NINEROUTER_API_KEY, config.NINEROUTER_MODEL)
    else:
        url, key, model = ("https://openrouter.ai/api/v1/chat/completions",
                           config.OPENROUTER_API_KEY, config.OPENROUTER_CHAT_MODEL)
    payload = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    return _post(url, payload, {"Authorization": f"Bearer {key}"})["choices"][0]["message"]

def chat(messages):
    """Chat via backend config.LLM_BACKEND (openrouter | ninerouter), fallback Ollama."""
    try:
        if config.LLM_BACKEND == "ninerouter":
            return chat_ninerouter(messages), "ninerouter"
        return chat_openrouter(messages), "openrouter"
    except Exception as e:
        print(f"{config.LLM_BACKEND} gagal ({e}), fallback Ollama...")
        return chat_ollama(messages), "ollama"
