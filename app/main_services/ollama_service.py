import logging
import time

import requests

from app.config import OLLAMA_URL, MODEL, OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    """Ollama could not answer. The message tells the user how to fix it."""


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

    started = time.perf_counter()
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
    # ConnectionError must come first: ConnectTimeout is both a ConnectionError and
    # a Timeout, and "server not reachable" is the more useful message for it.
    except requests.exceptions.ConnectionError as e:
        raise OllamaError(
            f"Cannot reach Ollama at {OLLAMA_URL}; start it with `ollama serve`."
        ) from e
    except requests.exceptions.Timeout as e:
        raise OllamaError(
            f"Ollama did not answer within {OLLAMA_TIMEOUT:g} seconds; "
            "increase OLLAMA_TIMEOUT or use a smaller model."
        ) from e
    except requests.exceptions.HTTPError as e:
        # Ollama answers 404 on /api/generate when the model is not pulled
        if e.response is not None and e.response.status_code == 404:
            raise OllamaError(
                f"Model {MODEL} not pulled; run `ollama pull {MODEL}`."
            ) from e
        raise OllamaError(f"Ollama returned an error: {e}") from e

    answer = response.json().get("response", "")
    logger.info(
        "Ollama call: model=%s prompt_chars=%d response_chars=%d seconds=%.1f",
        MODEL, len(prompt), len(answer), time.perf_counter() - started,
    )
    return answer
