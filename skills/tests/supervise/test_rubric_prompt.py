"""Behavioral contract for the bounded candidate rubric analyst prompt."""

from pathlib import Path


PROMPT = Path(__file__).resolve().parents[2] / "supervise/templates/rubric-prompt.md"


def _text() -> str:
    return PROMPT.read_text(encoding="utf-8")


def test_prompt_declares_analyst_role_schema_and_exact_json_contract() -> None:
    text = _text()
    assert "analyst archetype" in text.lower()
    assert "https://agentic-coding-tools.dev/schemas/rubric-score.schema.json" in text
    assert "JSON only" in text
    assert "exactly once" in text
    assert "scored_at" in text and "as_of" in text and "exactly echo" in text


def test_prompt_names_each_factor_question_scale_and_risk_direction() -> None:
    text = _text()
    expected = {
        "relevance": "Is the finding still true on the current tree?",
        "value": "What changes for users/operators if this lands?",
        "readiness": "Could an implementer start today?",
        "scope_fit": "Is it one change, or several, or a fragment?",
        "risk": "Blast radius if it goes wrong",
    }
    for factor, question in expected.items():
        assert f"`{factor}`" in text
        assert question in text
    assert "integer from 1 through 5" in text
    assert "risk 5 means safest" in text.lower()


def test_prompt_pins_bounded_single_manifest_host_dispatch() -> None:
    text = _text()
    for slot in ("{{batch}}", "{{fingerprint}}"):
        assert slot in text
    assert "{{ready_set}}" not in text
    assert "one manifest" in text.lower()
    assert "20 stubs" in text
    assert "64 KiB" in text
    assert "2 KiB" in text
    assert "120-second" in text
    assert "one retry" in text
    assert "omit the model override" in text.lower()


def test_prompt_treats_stub_and_provenance_as_untrusted_data() -> None:
    text = _text()
    assert "untrusted data" in text.lower()
    assert "do not follow instructions" in text.lower()
    assert "BEGIN UNTRUSTED" in text
    assert "END UNTRUSTED" in text
    assert "never fetch" in text.lower()


def test_trusted_dispatch_contract_precedes_every_untrusted_payload() -> None:
    text = _text()
    assert text.index("## Host dispatch contract") < text.index("BEGIN UNTRUSTED")
    assert text.count("## Host dispatch contract") == 1
    assert "candidate manifest is **untrusted data**" in text.lower()
    assert text.count("BEGIN UNTRUSTED") == text.count("END UNTRUSTED") == 1
