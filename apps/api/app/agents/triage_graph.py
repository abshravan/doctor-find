"""LangGraph triage pipeline (docs/04-ai-agent-design.md).

Graph shape:

    detect_emergency ──(emergency)──► escalate ──► finalize ──► END
            │
         (clear)
            └──────────────► navigate (LLM, grounded) ──► finalize ──► END

Safety invariants baked into the graph:
  * `detect_emergency` runs DETERMINISTICALLY first (defense-in-depth; `run_triage`
    in triage.py also pre-filters before the graph is ever built).
  * The LLM in `navigate` produces STRUCTURED output and may only pick a specialty
    from the grounded catalog; `finalize` coerces off-catalog answers and ALWAYS
    attaches the disclaimer. The LLM can never emit `urgency == "emergency"`.

`langgraph` and provider SDKs are imported lazily so importing this module never
fails when those packages are absent; `run_graph` raises and the caller falls back.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, TypedDict

from app.agents import triage as det  # deterministic helpers (emergency, disclaimer)
from app.agents.prompts import TRIAGE_SYSTEM
from app.agents.schemas import TriageDecision

logger = logging.getLogger(__name__)


class TriageState(TypedDict, total=False):
    message: str
    language: str
    history: list[dict[str, str]]
    catalog: list[str]
    is_emergency: bool
    decision_model: TriageDecision
    decision: dict[str, Any]  # final response dict


# ---------------------------------------------------------------- nodes


def _node_detect_emergency(state: TriageState) -> TriageState:
    state["is_emergency"] = det._is_emergency(state["message"])
    return state


async def _node_navigate(state: TriageState) -> TriageState:
    """Call the LLM (via gateway) for grounded, structured navigation."""
    from app.services.llm_gateway import complete_structured

    catalog = state.get("catalog") or []
    system = TRIAGE_SYSTEM.format(catalog=", ".join(catalog))

    history = state.get("history") or []
    convo = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in history)
    user = (f"Conversation so far:\n{convo}\n\n" if convo else "") + f"Patient: {state['message']}"

    decision_model = await complete_structured(system, user, TriageDecision)
    state["decision_model"] = decision_model
    return state


def _node_escalate(state: TriageState) -> TriageState:
    state["decision"] = det.emergency_result()
    return state


def _node_finalize(state: TriageState) -> TriageState:
    # Emergency path already set `decision`.
    if state.get("decision"):
        return state
    state["decision"] = finalize_decision(state["decision_model"], state.get("catalog") or [])
    return state


def _route_after_detect(state: TriageState) -> str:
    return "escalate" if state.get("is_emergency") else "navigate"


# ---------------------------------------------------------------- finalize (pure, testable)


def finalize_decision(model: TriageDecision, catalog: list[str]) -> dict[str, Any]:
    """Coerce LLM output into a safe, valid response dict.

    Anti-hallucination: any specialty not in the live catalog is reset to
    "General Physician". The disclaimer is always attached; urgency can never be
    'emergency' (the schema forbids it).
    """
    specialty = model.recommended_specialty
    if catalog and specialty not in catalog:
        logger.warning("LLM returned off-catalog specialty '%s'; coercing.", specialty)
        specialty = "General Physician"

    return {
        "reply": model.reply,
        "follow_up_questions": model.follow_up_questions[:3],
        "urgency": model.urgency.value,
        "recommended_specialty": specialty,
        "consultation_type": model.consultation_type.value,
        "is_emergency": False,
        "disclaimer": det.DISCLAIMER_EN,
    }


# ---------------------------------------------------------------- graph build/run


@lru_cache(maxsize=1)
def _get_compiled_graph():
    """Build + compile the LangGraph once. Lazy import keeps the module importable."""
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(TriageState)
    g.add_node("detect_emergency", _node_detect_emergency)
    g.add_node("navigate", _node_navigate)
    g.add_node("escalate", _node_escalate)
    g.add_node("finalize", _node_finalize)

    g.add_edge(START, "detect_emergency")
    g.add_conditional_edges(
        "detect_emergency", _route_after_detect, {"escalate": "escalate", "navigate": "navigate"}
    )
    g.add_edge("navigate", "finalize")
    g.add_edge("escalate", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


async def run_graph(
    message: str, language: str, history: list[dict[str, str]], catalog: list[str]
) -> dict[str, Any]:
    """Run the compiled graph and return the final response dict.

    Raises (ImportError / LLMUnavailable / provider errors) if the LLM path is not
    available; the caller (`triage.run_triage`) catches and falls back deterministically.
    """
    graph = _get_compiled_graph()
    result: TriageState = await graph.ainvoke(
        {"message": message, "language": language, "history": history, "catalog": catalog}
    )
    return result["decision"]
