import logging
import time
from typing import Any, Dict, List

import requests

from app.config import OLLAMA_URL, MODEL, OLLAMA_TIMEOUT, EMBED_MODEL, EMBED_BATCH_SIZE

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


def _post_ollama(path: str, payload: Dict[str, Any], model: str) -> Dict[str, Any]:
    """POSTs to Ollama and turns transport/HTTP failures into an actionable OllamaError."""
    try:
        response = requests.post(
            f"{OLLAMA_URL}{path}",
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
        # Ollama answers 404 when the requested model is not pulled
        if e.response is not None and e.response.status_code == 404:
            raise OllamaError(
                f"Model {model} not pulled; run `ollama pull {model}`."
            ) from e
        raise OllamaError(f"Ollama returned an error: {e}") from e
    return response.json()


def ask_local_ai(prompt: str) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
    }

    started = time.perf_counter()
    answer = _post_ollama("/api/generate", payload, MODEL).get("response", "")
    logger.info(
        "Ollama call: model=%s prompt_chars=%d response_chars=%d seconds=%.1f",
        MODEL, len(prompt), len(answer), time.perf_counter() - started,
    )
    return answer


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embeds texts with the local embedding model, EMBED_BATCH_SIZE texts per request."""
    started = time.perf_counter()
    embeddings: List[List[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start:start + EMBED_BATCH_SIZE]
        data = _post_ollama("/api/embed", {"model": EMBED_MODEL, "input": batch}, EMBED_MODEL)
        batch_embeddings = data.get("embeddings") or []
        if len(batch_embeddings) != len(batch):
            raise OllamaError(
                f"Ollama returned {len(batch_embeddings)} embeddings for {len(batch)} texts "
                f"(model {EMBED_MODEL})."
            )
        embeddings.extend(batch_embeddings)

    logger.info(
        "Ollama embed: model=%s texts=%d batches=%d seconds=%.2f",
        EMBED_MODEL, len(texts), -(-len(texts) // EMBED_BATCH_SIZE), time.perf_counter() - started,
    )
    return embeddings
