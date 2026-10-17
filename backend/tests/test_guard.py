"""Guard regression tests — run with ``pytest backend/tests/test_guard.py``.

These test the finance-scope guard at the level that actually blocks the user: the
``is_finance_prompt`` helper. The project has no app factory to test through FastAPI
without wiring a live Supabase JWKS endpoint, so the guard itself is unit-tested here.

Tests are grouped by what they are actually testing, so a failure means something
specific:
- `test_legitimate_*`        — real finance topics the guard must let through.
- `test_refused_*`           — real non-finance requests the guard must still refuse.
- `test_finance_word_in_prompt_*` — prompts that already name the topic themselves
                                (these must pass; the old dictionary handles them).
- `test_followup_in_chat_*`  — the real user bug. A follow-up with no own topic word
                                must be allowed **only after the chat loop attaches the
                                previous answer as context**, which makes the topic visible
                                to the same dictionary.
- `test_standalone_ambiguous_*` — a bare follow-up with no finance context at all must
                                be refused; the guard genuinely cannot tell the topic.
"""

from __future__ import annotations

import pytest

from backend.main import is_finance_prompt


# ------------------------------------------------------------------ legitimate finance

@pytest.mark.parametrize("prompt,expected", [
    ("What is SIP in mutual funds", True),
    ("What is a stock", True),
    ("S&P 500 earnings preview", True),
    ("Explain options", True),
    ("Fed raises rates", True),
    ("Bitcoin halving", True),
    ("portfolio allocation", True),
    ("What is NVDA trading at", True),
])
def test_legitimate_finance_prompts_still_pass(prompt: str, expected: bool) -> None:
    assert is_finance_prompt(prompt) == expected


# ------------------------------------------------------------------ non-finance still refused

@pytest.mark.parametrize("prompt", [
    "Who will win the football match tonight",
    "Book me a flight to Paris",
    "Tell me a joke about cats",
    "My cat is cute, write a poem",
    "How do I bake a cake",
])
def test_refused_non_finance_prompts_are_still_refused(prompt: str) -> None:
    assert is_finance_prompt(prompt) is False


# ------------------------------------------------------------------ prompts that name the topic themselves

@pytest.mark.parametrize("prompt", [
    "SIP in mutual funds explained as if ur teaching a beginer",
    "What is a bond, in plain language a beginner would understand",
])
def test_finance_word_in_prompt_is_allowed(prompt: str) -> None:
    # The prompt itself names a finance topic *and* frames it as a beginner-friendly
    # explanation. The dictionary already has the topic, so these pass on their own.
    assert is_finance_prompt(prompt) is True


# ------------------------------------------------------------------ follow-up phrasing that needs topic context

@pytest.mark.parametrize("prompt,with_history,expected", [
    # These are the follow-up phrasings the user actually writes. On their own they
    # are ambiguous, so they are refused; once the chat loop has attached a finance
    # answer as context, they are allowed.
    ("I still don't get it - say it like you are teaching a beginner", False, False),
    ("I still don't get it - say it like you are teaching a beginner", True, True),
    ("say it like you are teaching a beginner", False, False),
    ("say it like you are teaching a beginner", True, True),
    ("explain it like i am 5", False, False),
    ("explain it like i am 5", True, True),
    ("can you break that down more simply", False, False),
    ("can you break that down more simply", True, True),
])
def test_followup_phrasing_needs_topic_context(prompt: str, with_history: bool, expected: bool) -> None:
    history: list[ChatTurn] | None = None
    if with_history:
        from backend.main import ChatTurn
        history = [
            ChatTurn(role="assistant", content="SIP stands for Systematic Investment Plan. It is a way to invest a fixed amount in a mutual fund at regular intervals - monthly, quarterly, or weekly - regardless of the NAV at that moment."),
        ]
    assert is_finance_prompt(prompt, history) is expected


# ------------------------------------------------------------------ the actual user bug: follow-up in chat

class TestFollowupInChat:
    """The real bug is not a standalone sentence — it is a follow-up to a finance answer
    that already exists. The chat loop builds the chat prompt by attaching the last
    answer as visible context, so the topic the follow-up refers to is back in the same
    string the dictionary scans.

    These tests reproduce that join exactly and assert on the result.
    """

    @staticmethod
    def chat_prompt(previous_answer: str, followup: str) -> str:
        return f"{followup} (context from last turn: {previous_answer.strip()})"

    def test_plain_follow_up_to_sip_answer_passes(self) -> None:
        ans_sip = (
            "SIP stands for Systematic Investment Plan. It is a way to invest a fixed amount in a mutual fund "
            "at regular intervals - monthly, quarterly, or weekly - regardless of the NAV at that moment."
        )
        assert is_finance_prompt(
            self.chat_prompt(ans_sip, "explain that to me like you are teaching a beginner")
        ) is True

    def test_plain_follow_up_to_bond_answer_passes(self) -> None:
        ans_bond = (
            "A bond is a loan an investor makes to a borrower (a company or government). The borrower repays "
            "the loan over time and pays interest until the bond matures and the principal is repaid."
        )
        assert is_finance_prompt(
            self.chat_prompt(ans_bond, "i still don't get it - say it like you are teaching a beginner")
        ) is True

    def test_plain_follow_up_to_sip_answer_with_broken_english_passes(self) -> None:
        ans_dca = (
            "Dollar-cost averaging (DCA) is an investment strategy where an investor divides the total "
            "amount to be invested across periodic purchases of a target asset to reduce the impact of "
            "volatility on the overall purchase."
        )
        assert is_finance_prompt(
            self.chat_prompt(ans_dca, "sorry i cant understand can u say as if ur teaching for a beginer")
        ) is True

    def test_simpify_follow_up_to_sip_answer_passes(self) -> None:
        ans_sip = (
            "SIP stands for Systematic Investment Plan. It is a way to invest a fixed amount in a mutual fund "
            "at regular intervals - monthly, quarterly, or weekly - regardless of the NAV at that moment."
        )
        assert is_finance_prompt(
            self.chat_prompt(ans_sip, "can you break that down more simply")
        ) is True

    def test_plain_follow_up_to_a_non_finance_answer_still_refused(self) -> None:
        ans_cake = (
            "To bake a cake, preheat the oven to 180C, grease the tin, whisk the dry ingredients, "
            "add the wet ingredients, fold gently, and bake for 30 minutes."
        )
        assert is_finance_prompt(
            self.chat_prompt(ans_cake, "explain that to me like you are teaching a beginner")
        ) is False

    def test_standalone_explain_that_to_a_beginner_is_ambiguous_and_refused(self) -> None:
        # A single sentence with no finance context at all is too vague to judge.
        assert is_finance_prompt("explain that to me like you are teaching a beginner") is False

    def test_standalone_break_that_down_more_simply_is_ambiguous_and_refused(self) -> None:
        # Same judgement for the other follow-up shape.
        assert is_finance_prompt("can you break that down more simply") is False
