"""Optional streaming path for chat completions (OpenAI-compatible APIs).

Only used when the caller explicitly opts in (``stream_responses`` in config)
and no tool round-trip is expected. Falls back to the blocking path on any
error so a broken stream never loses the user's request.
"""

from __future__ import annotations

from .providers import Provider, make_client


def stream_chat(provider: Provider, messages, temperature: float = 0.5):
    """Yield text deltas from the provider. Raises on transport/auth errors."""
    client = make_client(provider)
    stream = client.chat.completions.create(
        model=provider.model,
        messages=messages,
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        try:
            delta = chunk.choices[0].delta
        except (IndexError, AttributeError):
            continue
        text = getattr(delta, "content", None)
        if text:
            yield text
