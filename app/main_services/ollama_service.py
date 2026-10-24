import requests

from app.config import OLLAMA_URL, MODEL, OLLAMA_TIMEOUT


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
        timeout=OLLAMA_TIMEOUT,
    )
    response.raise_for_status()

    return response.json().get("response", "")