import requests

OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = "qwen2.5:3b"


def get_models():
    response = requests.get(
        f"{OLLAMA_URL}/api/tags",
        timeout=5,
    )
    response.raise_for_status()
    return response.json().get("models", [])


def ask_local_ai(prompt: str) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
    }

    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json=payload,
        timeout=180,
    )
    response.raise_for_status()

    return response.json().get("response", "")