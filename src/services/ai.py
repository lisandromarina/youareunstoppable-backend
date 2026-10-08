import logging

import requests

from src.services.errors import DomainError

logger = logging.getLogger(__name__)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def complete(messages: list[dict[str, str]], *, api_key: str, model: str) -> str:
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": messages,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.warning("Coach request failed: %s", exc)
        raise DomainError(502, "The coach could not reply.") from exc
    if response.status_code >= 400:
        logger.warning("Coach request failed: status %s body %s", response.status_code, response.text[:1000])
        raise DomainError(502, "The coach could not reply.")
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning("Coach response was not a completion: %s", response.text[:1000])
        raise DomainError(502, "The coach could not reply.") from exc
    if not isinstance(content, str) or not content.strip():
        logger.warning("Coach response was empty")
        raise DomainError(502, "The coach could not reply.")
    return content
