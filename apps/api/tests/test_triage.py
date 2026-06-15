"""Tests for the safety-critical triage agent. The emergency path is the single
most important behavior in the product — it must never silently fail."""

from app.agents import triage


def test_emergency_chest_pain_escalates():
    result = triage.navigate("I have severe chest pain and can't breathe")
    assert result["is_emergency"] is True
    assert result["urgency"] == "emergency"
    assert "112" in result["reply"]


def test_emergency_self_harm_escalates():
    result = triage.navigate("I want to harm myself")
    assert result["is_emergency"] is True


def test_routine_routes_to_specialty():
    result = triage.navigate("I have a skin rash and acne for two weeks")
    assert result["is_emergency"] is False
    assert result["recommended_specialty"] == "Dermatology"
    assert result["urgency"] == "routine"


def test_unknown_defaults_to_general_physician():
    result = triage.navigate("I feel generally unwell and tired")
    assert result["recommended_specialty"] == "General Physician"


def test_disclaimer_always_present():
    for msg in ["chest pain", "skin rash", "random text"]:
        assert "not a doctor" in triage.navigate(msg)["disclaimer"]


# ---- run_triage orchestrator (deterministic pre-filter + LLM + fallback) ----


async def test_run_triage_emergency_pre_filter_skips_llm():
    """Emergencies must be handled deterministically, never via the LLM path."""
    result = await triage.run_triage("I have severe chest pain", db=None)
    assert result["is_emergency"] is True
    assert result["urgency"] == "emergency"
    assert "112" in result["reply"]


async def test_run_triage_falls_back_when_no_llm(monkeypatch):
    """With no LLM provider available, run_triage degrades to deterministic routing."""
    from app.services import llm_gateway

    monkeypatch.setattr(llm_gateway, "_candidate_models", lambda *a, **k: [])
    result = await triage.run_triage("I have a skin rash and acne", db=None)
    assert result["is_emergency"] is False
    assert result["recommended_specialty"] in ("Dermatology", "General Physician")
    assert "not a doctor" in result["disclaimer"]


# ---- finalize_decision anti-hallucination ----


def test_finalize_coerces_offcatalog_specialty():
    from app.agents.schemas import ConsultPreference, TriageDecision, Urgency
    from app.agents.triage_graph import finalize_decision

    bogus = TriageDecision(
        reply="ok",
        urgency=Urgency.routine,
        recommended_specialty="Astrology",  # not a real specialty
        consultation_type=ConsultPreference.either,
    )
    out = finalize_decision(bogus, catalog=["General Physician", "Dermatology"])
    assert out["recommended_specialty"] == "General Physician"
    assert out["is_emergency"] is False
    assert "not a doctor" in out["disclaimer"]


def test_finalize_keeps_valid_specialty_and_caps_followups():
    from app.agents.schemas import ConsultPreference, TriageDecision, Urgency
    from app.agents.triage_graph import finalize_decision

    decision = TriageDecision(
        reply="see a dermatologist",
        follow_up_questions=["a", "b", "c", "d", "e"],
        urgency=Urgency.soon,
        recommended_specialty="Dermatology",
        consultation_type=ConsultPreference.online,
    )
    out = finalize_decision(decision, catalog=["General Physician", "Dermatology"])
    assert out["recommended_specialty"] == "Dermatology"
    assert out["urgency"] == "soon"
    assert out["consultation_type"] == "online"
    assert len(out["follow_up_questions"]) == 3
