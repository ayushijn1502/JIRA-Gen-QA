"""
Lightweight checks before spending tokens on full analyze/generate flows.

Google does not expose "remaining free-tier tokens" in the Generative Language API,
so we validate the key + model with a small metadata request and enforce a
configurable per-run token budget inside ``GeminiLLMService``.

Uses ``requests`` so system HTTPS proxy env vars (``HTTPS_PROXY``, etc.) are honored.
"""

from __future__ import annotations

import requests


def preflight_gemini(api_key: str, model_name: str, timeout: float = 30.0) -> None:
    """
    Verify the API key and that the configured model id exists for this API.

    Uses ``GET /v1beta/models/{model}`` (metadata only). Raises ``RuntimeError``
    with actionable text on failure.
    """
    key = (api_key or "").strip()
    if not key:
        raise RuntimeError(
            "gemini.api_key is empty. Set it in config.yaml or export "
            "AUTOTEST_GEMINI__API_KEY (see Google AI Studio)."
        )

    mid = model_name.removeprefix("models/")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{mid}"

    try:
        response = requests.get(url, params={"key": key}, timeout=timeout)
    except requests.exceptions.SSLError as exc:
        raise RuntimeError(
            "TLS/SSL error connecting to generativelanguage.googleapis.com. "
            "On macOS, try running Applications/Python 3.x/Install Certificates.command; "
            "behind corporate SSL inspection, install the proxy root CA or set REQUESTS_CA_BUNDLE. "
            f"Underlying error: {exc}"
        ) from exc
    except requests.exceptions.ProxyError as exc:
        raise RuntimeError(
            "HTTPS proxy error while contacting Google. Check HTTPS_PROXY / HTTP_PROXY "
            f"and proxy credentials. Underlying error: {exc}"
        ) from exc
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        raise RuntimeError(
            "Could not reach generativelanguage.googleapis.com (connection or timeout). "
            "Try: confirm internet and DNS, use a VPN if your region blocks Google APIs, "
            "set HTTPS_PROXY if a corporate proxy is required, or temporarily set "
            "gemini.run_preflight: false in config.yaml if the chat API still works "
            "from your network (preflight uses the same host). "
            f"Underlying error: {exc}"
        ) from exc

    if response.status_code == 401 or response.status_code == 403:
        raise RuntimeError(
            "Gemini API rejected the key (401/403). Regenerate the key in "
            "Google AI Studio and update gemini.api_key."
        )
    if response.status_code == 404:
        body = (response.text or "")[:500]
        raise RuntimeError(
            f"Gemini model '{mid}' was not found (404). "
            f"Check gemini.model_name (e.g. gemini-2.5-flash-lite). Response: {body}"
        )
    if response.status_code != 200:
        body = (response.text or "")[:500]
        raise RuntimeError(
            f"Gemini preflight HTTP {response.status_code} for model '{mid}'. {body}"
        )
