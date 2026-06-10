import importlib
import os
import time

from dotenv import load_dotenv

try:
    import config
except ImportError:  # pragma: no cover - config.py is expected in normal use
    config = object()

from constants import RETRY_ATTEMPTS, RETRY_BASE_WAIT_S

load_dotenv()

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_OPENAI_MODEL = "gpt-5.2"
RETRY_STATUS_CODES = {429, 500, 502, 503, 529}


# =============================================================================
# Public API
# =============================================================================

def call_llm(prompt: str, max_tokens: int = 1000) -> str:
    """Call the configured LLM provider and return stripped text."""
    provider = _get_llm_provider()
    if provider == "anthropic":
        return _call_anthropic(prompt, max_tokens)
    if provider in {"openai", "openai-compatible"}:
        return _call_openai(prompt, max_tokens, compatible=(provider == "openai-compatible"))
    raise ValueError(
        f"Unsupported LLM_PROVIDER '{provider}'. "
        "Use 'anthropic', 'openai', or 'openai-compatible'."
    )


def call_claude(prompt: str, max_tokens: int = 1000) -> str:
    """Backward-compatible alias for existing generator/scraper call sites."""
    return call_llm(prompt, max_tokens=max_tokens)


# =============================================================================
# Provider Implementations
# =============================================================================

def _call_anthropic(prompt: str, max_tokens: int) -> str:
    anthropic = _import_required(
        "anthropic",
        "Install Anthropic support with: pip install anthropic",
    )
    model = _get_llm_model("anthropic")
    api_key = _setting("ANTHROPIC_API_KEY")

    def request():
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()

    return _with_retry(request, "Anthropic")


def _call_openai(prompt: str, max_tokens: int, *, compatible: bool) -> str:
    base_url = _setting("LLM_BASE_URL") if compatible else _setting("OPENAI_BASE_URL")
    if compatible and not base_url:
        raise ValueError("LLM_BASE_URL is required when LLM_PROVIDER='openai-compatible'")

    openai = _import_required(
        "openai",
        "Install OpenAI support with: pip install openai",
    )
    model = _get_llm_model("openai-compatible" if compatible else "openai")
    api_key = _openai_api_key(compatible=compatible)

    def request():
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        client = openai.OpenAI(**kwargs)
        response = client.responses.create(
            model=model,
            input=prompt,
            max_output_tokens=max_tokens,
        )
        return _extract_openai_text(response)

    label = "OpenAI-compatible" if compatible else "OpenAI"
    return _with_retry(request, label)


# =============================================================================
# Config And Environment Resolution
# =============================================================================

def _get_llm_provider() -> str:
    provider = str(_setting("LLM_PROVIDER", "anthropic")).strip().lower()
    aliases = {
        "claude": "anthropic",
        "anthropic": "anthropic",
        "openai": "openai",
        "gpt": "openai",
        "openai_compatible": "openai-compatible",
        "openai-compatible": "openai-compatible",
        "compatible": "openai-compatible",
        "custom": "openai-compatible",
    }
    return aliases.get(provider, provider)


def _get_llm_model(provider: str) -> str:
    explicit = _setting("LLM_MODEL")
    if explicit:
        return explicit
    if provider == "anthropic":
        return _setting("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    if provider == "openai":
        return _setting("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    if provider == "openai-compatible":
        model = _setting("OPENAI_MODEL")
        if model:
            return model
        raise ValueError("LLM_MODEL is required when LLM_PROVIDER='openai-compatible'")
    return ""


def _openai_api_key(*, compatible: bool) -> str | None:
    if compatible:
        return _setting("LLM_API_KEY") or _setting("OPENAI_API_KEY")
    return _setting("OPENAI_API_KEY") or _setting("LLM_API_KEY")


def _setting(name: str, default=None):
    value = getattr(config, name, None)
    if value not in (None, ""):
        return value
    value = os.getenv(name)
    if value not in (None, ""):
        return value
    return default


# =============================================================================
# Retry Handling
# =============================================================================

def _with_retry(request_fn, label: str) -> str:
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return request_fn()
        except Exception as e:
            if _is_retryable_error(e) and attempt < RETRY_ATTEMPTS - 1:
                status_code = getattr(e, "status_code", None)
                error_label = status_code if status_code is not None else e.__class__.__name__
                wait = RETRY_BASE_WAIT_S * (attempt + 1)
                print(f"  {label} API error {error_label} - retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"{label} request failed without raising an exception")


def _is_retryable_error(error) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code in RETRY_STATUS_CODES:
        return True
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True
    class_name = error.__class__.__name__.lower()
    return "timeout" in class_name or "connection" in class_name


# =============================================================================
# Response Parsing
# =============================================================================

def _extract_openai_text(response) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text.strip()

    if isinstance(response, dict):
        output_text = response.get("output_text")
        if output_text:
            return output_text.strip()
        output = response.get("output", [])
    else:
        output = getattr(response, "output", [])

    chunks = []
    for item in output or []:
        content = item.get("content", []) if isinstance(item, dict) else getattr(item, "content", [])
        for part in content or []:
            text = _content_part_text(part)
            if text:
                chunks.append(text)
    text = "".join(chunks).strip()
    if text:
        return text
    raise ValueError("OpenAI response did not contain text output")


def _content_part_text(part) -> str:
    if isinstance(part, dict):
        if part.get("type") in {"output_text", "text"}:
            return part.get("text", "")
        return ""
    part_type = getattr(part, "type", None)
    if part_type in {"output_text", "text"}:
        return getattr(part, "text", "")
    return ""


# =============================================================================
# Import Helpers
# =============================================================================

def _import_required(module_name: str, install_hint: str):
    try:
        return importlib.import_module(module_name)
    except ImportError as e:
        raise ImportError(install_hint) from e
