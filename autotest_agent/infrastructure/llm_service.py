"""
LLM Service -- sends prompts to Google Gemini and (optionally) parses
the response into a Pydantic model.

Think of it as a "smart assistant caller": you give it instructions
(system prompt) and a question (user prompt), and it returns either
free-form text or a nicely structured Python object.

Usage:
    svc = GeminiLLMService(api_key="...", model_name="gemini-2.5-flash-lite")
    test_code = svc.generate(
        system_prompt="You are a test engineer...",
        user_prompt="Write tests for user login",
        output_schema=GeneratedTest,
    )
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, TypeVar, get_origin

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ValidationError

from autotest_agent.domain.ports import LLMPort

T = TypeVar("T", bound=BaseModel)


class GeminiLLMService(LLMPort):
    """
    Concrete implementation of LLMPort backed by Google Gemini.
    Uses LangChain's ChatGoogleGenerativeAI wrapper so we get
    nice streaming, retry, and token-counting support for free.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.5-flash-lite",
        *,
        max_output_tokens: int | None = None,
        max_total_tokens_per_run: int | None = 80_000,
    ) -> None:
        kwargs: dict[str, Any] = {
            "model": model_name,
            "google_api_key": api_key,
            "temperature": 0.2,
        }
        if max_output_tokens is not None:
            kwargs["max_output_tokens"] = max_output_tokens
        self._llm = ChatGoogleGenerativeAI(**kwargs)
        self._max_output_tokens = max_output_tokens
        self._max_total_tokens_per_run = max_total_tokens_per_run
        self._tokens_used_this_run = 0

    @property
    def tokens_used_this_run(self) -> int:
        """Total tokens reported by Gemini across successful invokes in this process."""
        return self._tokens_used_this_run

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[Any] | None = None,
    ) -> Any:
        """
        Call Gemini with a system + user prompt.
        If output_schema is a Pydantic model class, we ask the LLM to
        return JSON matching that schema and parse it automatically.
        Otherwise we return the raw text response.
        """
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

        if output_schema is not None and _is_pydantic_model(output_schema):
            return self._generate_structured(messages, output_schema)

        response = self._invoke_with_retry(messages)
        return response.content

    def _rough_prompt_tokens(self, messages: list[BaseMessage]) -> int:
        """Cheap upper-ish bound before a call (Google does not expose remaining quota)."""
        total_chars = 0
        for m in messages:
            c = getattr(m, "content", "") or ""
            if isinstance(c, str):
                total_chars += len(c)
        return max(256, total_chars // 3 + 1024)

    def _output_budget_guess(self) -> int:
        if self._max_output_tokens is not None:
            return int(self._max_output_tokens)
        return 8192

    def _check_budget_before_call(self, messages: list[BaseMessage]) -> None:
        if self._max_total_tokens_per_run is None:
            return
        next_guess = self._rough_prompt_tokens(messages) + self._output_budget_guess()
        if self._tokens_used_this_run + next_guess > self._max_total_tokens_per_run:
            raise RuntimeError(
                f"Per-run Gemini token budget would be exceeded (~"
                f"{self._tokens_used_this_run} used so far; next call ~{next_guess} "
                f"estimated). Raise gemini.max_total_tokens_per_run in config.yaml or "
                f"set it to null to disable this guard."
            )

    def _accumulate_usage(self, response: Any) -> None:
        meta = getattr(response, "usage_metadata", None)
        if not meta:
            return
        total: int | None
        if isinstance(meta, dict):
            total = meta.get("total_tokens")
            if total is None:
                total = (meta.get("input_tokens") or 0) + (meta.get("output_tokens") or 0)
        else:
            total = getattr(meta, "total_tokens", None)
        try:
            self._tokens_used_this_run += int(total or 0)
        except (TypeError, ValueError):
            pass

    def _generate_structured(self, messages: list, schema: type[T]) -> T:
        """
        Ask the LLM to return JSON, then parse it into the given
        Pydantic model.  Falls back to manual JSON extraction if
        the LLM wraps the output in markdown code fences.
        """
        messages[-1] = HumanMessage(
            content=f"{messages[-1].content}{build_structured_json_prompt_suffix(schema)}"
        )
        response = self._invoke_with_retry(messages)
        return _parse_json_response(response.content, schema)

    def _invoke_with_retry(self, messages: list, max_attempts: int = 6) -> Any:
        """
        Call the model; on transient Google errors, wait and retry.

        Retries:
        - 429 / RESOURCE_EXHAUSTED (rate / quota bursts)
        - 503 / UNAVAILABLE / "high demand" (temporary overload)

        Does not fix zero quota or wrong model — change config or billing for that.
        """
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            try:
                self._check_budget_before_call(messages)
                response = self._llm.invoke(messages)
                self._accumulate_usage(response)
                return response
            except Exception as exc:
                if not _is_retryable_llm_error(exc):
                    raise
                last_error = exc
                if attempt == max_attempts - 1:
                    break
                err_str = str(exc)
                delay_match = re.search(
                    r"retry in ([\d.]+)\s*s",
                    err_str,
                    flags=re.IGNORECASE,
                )
                if delay_match:
                    wait_sec = float(delay_match.group(1))
                elif _is_overload_error(exc):
                    # 503 "high demand" — back off a bit longer between tries
                    wait_sec = min(90.0, 8.0 * (2**attempt))
                else:
                    wait_sec = min(60.0, 5.0 * (2**attempt))
                wait_sec = min(max(wait_sec + 1.0, 2.0), 120.0)
                time.sleep(wait_sec)
        assert last_error is not None
        raise last_error


def _is_retryable_llm_error(exc: Exception) -> bool:
    """True if the error often clears after waiting (Google transient)."""
    text = str(exc).lower()
    if "429" in text or "resource_exhausted" in text:
        return True
    if "503" in text or "unavailable" in text:
        return True
    if "high demand" in text:
        return True
    return False


def _is_overload_error(exc: Exception) -> bool:
    """503-style overload (not necessarily the same as rate limit)."""
    text = str(exc).lower()
    return "503" in text or "unavailable" in text or "high demand" in text


def build_structured_json_prompt_suffix(model_cls: type[BaseModel]) -> str:
    """
    Build instructions plus a small **data** example (not a JSON Schema).

    Small models often copy full ``model_json_schema()`` output and return
    ``{"type": "object", "properties": ...}`` — which is not valid input for
    our Pydantic models.  Showing a concrete instance shape avoids that.
    """
    example = _minimal_data_example_dict(model_cls)
    example_json = json.dumps(example, indent=2)
    return (
        "\n\nRespond with ONE JSON object only: real values, same keys as below "
        "(replace the placeholder strings and lists with your actual content).\n"
        f"{example_json}\n\n"
        "Rules:\n"
        '- Keys must match exactly (e.g. "ticket_id", not nested under "properties").\n'
        "- Do NOT output JSON Schema / OpenAPI (no root \"type\":\"object\" describing "
        'the payload, no "$defs", no "properties" wrapper for the whole answer).\n'
        "- Your reply must be runnable data JSON, like the example shape above."
    )


def _minimal_data_example_dict(model_cls: type[BaseModel]) -> dict[str, Any]:
    """Placeholder values so the model sees a data document, not a schema."""
    out: dict[str, Any] = {}
    for name, finfo in model_cls.model_fields.items():
        ann = finfo.annotation
        origin = get_origin(ann)
        if origin is list:
            if name == "relevant_context":
                out[name] = []
            elif name == "test_scenarios":
                out[name] = ["First scenario in one line", "Second scenario"]
            else:
                out[name] = ["item"]
            continue
        if ann is str or getattr(ann, "__name__", None) == "str":
            if name == "ticket_id":
                out[name] = "TICKET-KEY"
            elif name in ("target_file", "file_path"):
                out[name] = "target_framework/tests/test_example.py"
            elif name == "code":
                out[name] = "# full pytest file as one string; escape newlines for JSON"
            elif name == "explanation":
                out[name] = "What these tests cover"
            else:
                out[name] = f"<{name}>"
            continue
        out[name] = None
    return out


def _is_pydantic_model(cls: type) -> bool:
    """Check whether a type is a Pydantic BaseModel subclass."""
    try:
        return issubclass(cls, BaseModel)
    except TypeError:
        return False


def _parse_json_response(text: str, schema: type[T]) -> T:
    """
    Extract JSON from the LLM response (which might be wrapped in
    ```json ... ``` fences) and validate it against the Pydantic schema.

    Local models often add a sentence before the JSON; we peel that off by
    taking the first balanced ``{ ... }`` block when plain parse fails.
    """
    cleaned = _coerce_llm_json_text(text)
    try:
        return schema.model_validate_json(cleaned)
    except ValidationError as exc:
        err_low = str(exc).lower()
        if schema.__name__ == "GeneratedTest" and (
            "eof while parsing" in err_low or "json_invalid" in err_low
        ):
            raise RuntimeError(
                "Incomplete JSON from the model (output was cut off). Raise "
                "`gemini.max_output_tokens` in config.yaml or simplify the test file."
            ) from exc
        raise


def _coerce_llm_json_text(raw: str) -> str:
    """
    Turn messy model output into a single JSON object string.

    Strips markdown fences, finds the first ``{``, then keeps the balanced
    ``{ ... }`` span (handles a lead-in sentence before the JSON).
    """
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s*```\s*$", "", text).strip()

    start = text.find("{")
    if start == -1:
        return text

    balanced = _extract_balanced_braces(text, start)
    return balanced if balanced else text[start:]


def _extract_balanced_braces(text: str, start: int) -> str:
    """Return substring from ``start`` through the closing ``}`` for that object."""
    end = _find_matching_brace(text, start)
    if end is None:
        return ""
    return text[start : end + 1]


def _find_matching_brace(text: str, open_idx: int) -> int | None:
    """Index of the ``}`` that closes the ``{`` at ``open_idx``, or None."""
    if open_idx >= len(text) or text[open_idx] != "{":
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(open_idx, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return None
