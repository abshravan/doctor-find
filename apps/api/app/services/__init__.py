"""Business-logic services (deterministic core).

Placeholders for the MVP. Implement per the Phase 3/4/12 designs:
  * booking.py        — slot validation, idempotent booking, conflict handling
  * matching.py       — symptom->doctor ranking (pgvector + structured filters)
  * notifications.py  — WhatsApp/SMS dispatch (Gupshup/MSG91)
  * llm_gateway.py    — provider-agnostic LLM client w/ failover (Gemini->Claude/OpenAI)
"""
