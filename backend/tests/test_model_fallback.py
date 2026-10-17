"""Model-selection tests — run with ``pytest backend/tests/test_model_fallback.py``.

Google retires Gemini model ids over time, and a retired id used to fail every chat
request with "Gemini model '...' not found". These tests cover the recovery path that
replaced that dead end:

- ``candidate_models``     — the configured id is tried first, then the known-good ids.
- ``model_is_unavailable`` — only a missing/retired model id triggers the fallback; a bad
                             key, a quota limit or a provider outage must not.
- ``active_model``         — falls back to the packaged default when the variable is unset.

None of these touch the network.
"""

from __future__ import annotations

import pytest

from backend.main import (
    DEFAULT_GEMINI_MODEL,
    FALLBACK_GEMINI_MODELS,
    NoUsableModel,
    active_model,
    candidate_models,
    model_is_overloaded,
    model_is_unavailable,
    should_try_next_model,
)


# ------------------------------------------------------------------ candidate ordering

def test_configured_model_is_tried_first() -> None:
    assert candidate_models("gemini-3.5-flash")[0] == "gemini-3.5-flash"


def test_every_known_good_model_is_reachable() -> None:
    chain = candidate_models("gemini-3.5-flash")
    for name in FALLBACK_GEMINI_MODELS:
        assert name in chain, f"{name} must be in the fallback chain"


def test_chain_has_no_duplicates() -> None:
    for requested in FALLBACK_GEMINI_MODELS:
        chain = candidate_models(requested)
        assert len(chain) == len(set(chain)), f"duplicate ids for {requested}: {chain}"


def test_unknown_model_still_gets_the_fallbacks() -> None:
    chain = candidate_models("gemini-nonexistent-9999")
    assert chain[0] == "gemini-nonexistent-9999"
    assert len(chain) > 1


# ------------------------------------------------------------------ error classification

@pytest.mark.parametrize("message", [
    "404 NOT_FOUND. This model models/gemini-2.0-flash is no longer available to new users.",
    "models/gemini-9-flash is not found for API version v1beta",
    "The model does not exist",
    "not_found",
])
def test_missing_model_ids_trigger_the_fallback(message: str) -> None:
    assert model_is_unavailable(RuntimeError(message)) is True


@pytest.mark.parametrize("message", [
    "API key not valid. Please pass a valid API key.",
    "429 RESOURCE_EXHAUSTED. Quota exceeded",
    "Request contains an invalid argument.",
])
def test_other_failures_do_not_trigger_the_fallback(message: str) -> None:
    """A bad key, a quota limit or a bad request must surface, not silently swap models."""
    assert should_try_next_model(RuntimeError(message)) is False


# ------------------------------------------------------------------ capacity errors

@pytest.mark.parametrize("message", [
    "503 UNAVAILABLE. This model is currently experiencing high demand.",
    "504 DEADLINE_EXCEEDED. Deadline expired before operation could complete.",
    "The model is overloaded, please try again later",
])
def test_busy_models_are_retried_on_the_next_candidate(message: str) -> None:
    assert model_is_overloaded(RuntimeError(message)) is True
    assert should_try_next_model(RuntimeError(message)) is True


@pytest.mark.parametrize("message", [
    "429 RESOURCE_EXHAUSTED. Quota exceeded",
    "API key not valid. Please pass a valid API key.",
])
def test_quota_and_key_errors_are_reported_not_retried(message: str) -> None:
    assert model_is_overloaded(RuntimeError(message)) is False
    assert should_try_next_model(RuntimeError(message)) is False


# ------------------------------------------------------------------ default model

def test_active_model_prefers_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash")
    assert active_model() == "gemini-3.5-flash"


def test_active_model_falls_back_to_the_packaged_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert active_model() == DEFAULT_GEMINI_MODEL


def test_no_usable_model_reports_every_id_it_tried() -> None:
    tried = ["gemini-2.0-flash", "gemini-3.6-flash"]
    error = NoUsableModel(tried, retired=list(tried))
    assert error.tried == tried
    assert "gemini-2.0-flash" in str(error)


def test_all_retired_is_distinguished_from_a_busy_provider() -> None:
    """The user needs a different message for "fix your config" than for "wait a moment"."""
    all_retired = NoUsableModel(["a", "b"], retired=["a", "b"])
    partly_busy = NoUsableModel(["a", "b"], retired=["a"])
    assert all_retired.every_id_retired is True
    assert partly_busy.every_id_retired is False
