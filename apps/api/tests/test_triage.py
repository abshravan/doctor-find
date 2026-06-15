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
