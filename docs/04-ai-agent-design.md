# DoctorFind — Phase 4: AI & Agent Design

> **Status:** Implementation-ready specification
> **Owners:** AI Platform / Agent Engineering
> **Scope:** Conversational AI, voice, smart triage (NOT diagnosis), doctor discovery, booking, and workflow automation for India.
> **Canonical stack:** FastAPI · PostgreSQL + pgvector + Redis · LangGraph (agent orchestration) + Temporal (durable workflows) · Gemini Flash (primary LLM) with OpenAI/Claude fallback · Deepgram/Whisper (STT) · ElevenLabs/Azure (TTS) · Exotel/LiveKit/Twilio (voice) · Gupshup (WhatsApp).

---

## 0. Design Philosophy & Guardrails (read first)

DoctorFind is an **AI healthcare navigator, not a clinician**. Every design decision below flows from three non-negotiable principles:

1. **Safety over helpfulness.** The system must *never* diagnose, prescribe, interpret lab/imaging results, or recommend medication. It triages *urgency* and *routes* patients to the right kind of care. When in doubt, it escalates to a human or to emergency services.
2. **Determinism where money, calendars, and clinical urgency live.** Booking, payments, slot availability, and emergency escalation are deterministic state machines (Temporal). LLMs are used for *understanding and navigation*, not for *committing transactions*.
3. **Grounding over generation.** Any factual claim about a doctor, slot, price, or clinic must be backed by a database row or tool result, with the row id carried as a citation. The LLM is forbidden from inventing doctors, prices, qualifications, or availability.

### Global safety rules (injected into EVERY agent system prompt)

```
GLOBAL SAFETY RULES (apply to all responses, all languages):
1. You are NOT a doctor. You do NOT diagnose diseases, interpret test/scan
   results, prescribe or suggest medicines, dosages, or treatments.
2. If the user describes RED-FLAG symptoms (see emergency list), STOP normal
   flow and trigger the emergency_escalation tool immediately.
3. Never state or imply medical certainty. Use language like "this may need
   to be checked by a doctor", never "you have X".
4. Every health-related turn must end with the safety disclaimer in the
   user's language (use the localized_disclaimer tool — do NOT write it
   from memory).
5. Never fabricate doctors, clinics, prices, timings, qualifications, or
   availability. If you do not have a tool result, say you don't know and
   offer to search.
6. Do not collect more personal/health data than needed for the current task.
   Follow DPDP Act (India) data-minimization.
7. If the user is a minor, pregnant, elderly (65+), or immunocompromised and
   reports symptoms, lower the escalation threshold (route to higher urgency).
8. Respect user language. Detect and reply in the user's language
   (English, Hindi, and 8+ Indian languages). Never code-switch unless the
   user does.

RED-FLAG EMERGENCY LIST (any => emergency_escalation):
chest pain/pressure, difficulty breathing, severe bleeding, sudden weakness
or numbness on one side, slurred speech, face drooping, unconsciousness or
fainting, seizure, suicidal/self-harm intent, severe allergic reaction
(swelling of face/throat), high-fall/major trauma, poisoning/overdose,
sudden severe headache ("worst of my life"), blue lips, infant not feeding /
lethargic, pregnancy bleeding or severe abdominal pain.
```

---

## 1. Agent Roster (overview)

| # | Agent | Type | Primary Surface | LLM mode |
|---|-------|------|-----------------|----------|
| 1 | Patient Intake Agent | Agentic (conversational) | WhatsApp / app / voice | LLM + tools |
| 2 | Triage Agent | Constrained-agentic | All | LLM + tool-forced |
| 3 | Doctor Matching Agent | RAG + ranking | All | LLM over retrieved rows |
| 4 | Booking Agent | **Deterministic** (Temporal-backed) | All | Thin LLM (NLU only) |
| 5 | Reminder Agent | Deterministic (scheduled) | WhatsApp / SMS / voice | Template, no free-gen |
| 6 | Voice Receptionist Agent | Real-time agentic | Voice (LiveKit/Exotel) | Streaming LLM |
| 7 | Follow-up Agent | Semi-agentic (scheduled) | WhatsApp / voice | LLM + tools |

Agents communicate through a **Supervisor/Router** (LangGraph). Durable side effects (booking, payment, reminders) are executed via **Temporal workflows** invoked as tools, so agent crashes never lose or double-commit transactions.

---

## 2. Shared Infrastructure

### 2.1 Memory model

| Layer | Store | TTL | Contents |
|-------|-------|-----|----------|
| **Working memory** (turn) | In-process LangGraph state | request | Current messages, scratchpad, tool results |
| **Short-term session memory** | Redis (`session:{session_id}`) | 30 min sliding (24h for voice callbacks) | Rolling message window, running summary, active intent, slots filled, language, triage_state |
| **Long-term patient memory** | PostgreSQL (`patient_profile`, `patient_episode`, `consent_log`) | Persistent | Demographics, allergies (declared), past episodes, preferences (doctor gender, language, location), consent flags |
| **Semantic memory / RAG** | pgvector (`doctor_embeddings`, `symptom_specialty_map`, `kb_chunks`) | Persistent | Doctor profile embeddings, specialty mappings, policy KB |

**Short-term vs long-term split:** Short-term is *conversation-scoped* and disposable (Redis). Long-term is *patient-scoped*, consented, and audited (Postgres). Long-term writes require an explicit `consent_log` entry. The Redis session never stores PHI beyond TTL; PHI that must persist is promoted to Postgres via the `persist_episode` tool only after consent.

### 2.2 Context management & token budgeting

```
TOKEN BUDGET (per agent turn, target model ctx = 1M Gemini Flash; plan for 32k working budget for cost):
  system prompt + safety rules ............ ~1,800 tokens  (cached prefix)
  tool/function schemas ................... ~1,200 tokens  (cached prefix)
  long-term patient summary ............... ~  400 tokens
  RAG / retrieved rows .................... ~2,500 tokens  (top-k, trimmed)
  rolling session summary ................. ~  600 tokens
  last N raw messages (N≈8) ............... ~2,000 tokens
  current user message .................... ~  300 tokens
  ----------------------------------------------------------
  input budget ............................ ~8,800 tokens
  output reserve .......................... ~1,000 tokens
```

- **Prefix caching:** system prompt + tool schemas are stable → use provider prompt caching (Gemini implicit / Anthropic explicit `cache_control`) to cut cost ~80% on the static prefix.
- **Summarization:** when raw message window > 8 turns, run a *summarizer pass* (cheap model) that compresses older turns into the `session.rolling_summary` field. Keep the last 8 verbatim. Summaries are extractive for slots (never drop slot values), abstractive for chit-chat.
- **Retrieval:** RAG context is *trimmed to top-k rows* with only the fields needed for the current step (e.g., matching needs name, specialty, distance, fee, next-slot; not full bio).

### 2.3 Model routing & fallback

```
Primary:   Gemini Flash (fast, cheap, multilingual, 1M ctx)
Fallback1: Claude (Anthropic) — used for high-stakes reasoning turns
           (triage adjudication, safety-sensitive refusals) and on Gemini
           5xx/timeout/safety-block.
Fallback2: OpenAI (GPT) — second fallback on provider outage.

Routing rules:
- Triage final urgency decision => prefer Claude for stability of structured
  output + strong refusal behavior; Gemini for the conversational turns.
- Any provider safety-filter block on a legitimate medical query => retry on
  fallback provider with same prompt (do NOT silently drop the user).
- All providers called via a single LLMGateway with: timeout=8s (voice 3s),
  2 retries w/ jitter, circuit breaker per provider, structured-output
  validation, and automatic provider failover.
```

> Implementation note: a single `LLMGateway.invoke(messages, tools, schema, route_hint)` abstracts provider choice. Because Gemini is primary and Claude/OpenAI are fallbacks, all three SDKs are wired; structured-output parsing is provider-agnostic (JSON schema enforced + re-ask on parse failure).

---

## 3. Orchestration: Supervisor / Router Pattern

### 3.1 Agent graph (LangGraph)

```
                         ┌───────────────────────────┐
   inbound (WA / app /   │       INGRESS / NLU        │
   voice / SMS)  ──────▶ │  - language detect         │
                         │  - STT (voice)             │
                         │  - PII scrub for logs      │
                         │  - load session (Redis)    │
                         └─────────────┬─────────────┘
                                       │
                                       ▼
                         ┌───────────────────────────┐
                         │        SUPERVISOR          │◀───────────────┐
                         │  (router LLM, tool-forced) │                │
                         │  picks next agent OR ends  │                │
                         └─┬───┬───┬───┬───┬───┬───┬──┘                │
        ┌──────────────────┘   │   │   │   │   │   └──────────────┐    │
        ▼                      ▼   ▼   ▼   ▼   ▼                   ▼    │
 ┌────────────┐  ┌─────────┐ ┌────┐ ┌────┐ ┌────┐ ┌──────────┐ ┌────────────┐
 │  INTAKE    │  │ TRIAGE  │ │MATCH│ │BOOK│ │FUP │ │ RECEPTION│ │  REMINDER  │
 │  (1)       │  │ (2)     │ │(3) │ │(4) │ │(7) │ │ IST (6)  │ │   (5)      │
 └─────┬──────┘  └────┬────┘ └─┬──┘ └─┬──┘ └─┬──┘ └────┬─────┘ └─────┬──────┘
       │              │        │      │      │         │             │
       │   ┌──────────┴────────┴──────┴──────┴─────────┘             │
       │   │                  TOOL LAYER                              │
       ▼   ▼   (DB / pgvector / Temporal / payments / notify / maps)  ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  EMERGENCY ESCALATION (interrupt — preempts any agent on red flag)   │
 │   -> emergency message + 108/112 + nearest ER + human handoff queue │
 └─────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼ (every health turn)
                         ┌───────────────────────────┐
                         │  SAFETY / DISCLAIMER GUARD │
                         │  (post-processor, deterministic)│
                         └───────────────────────────┘
```

### 3.2 Router logic

The Supervisor is a **tool-forced classifier**, not a free-form chatbot. It receives the session state + last message and MUST call exactly one routing tool. This prevents the router from "answering" medical questions itself.

```
SUPERVISOR SYSTEM PROMPT (excerpt):
You are the DoctorFind Supervisor. You do NOT talk to the user. Your ONLY
job is to select the next agent by calling route_to_agent exactly once.

Routing decision rules (apply in order):
1. If emergency_signal == true in state -> route "EMERGENCY".
2. If user intent is greeting/unknown OR demographics/symptoms incomplete
   -> "INTAKE".
3. If symptoms collected and urgency not yet determined -> "TRIAGE".
4. If urgency determined (non-emergency) and user wants a doctor/clinic
   -> "MATCH".
5. If user has selected a doctor/slot and wants to confirm -> "BOOK".
6. If channel == voice and caller is a clinic inbound line -> "RECEPTIONIST".
7. If context is post-appointment (status in {completed, no_show}) ->
   "FOLLOWUP".
8. Reminders are scheduled by Temporal, not routed here, EXCEPT when a user
   replies to a reminder ("reschedule"/"cancel") -> "BOOK".
Never answer the user. Never diagnose. Call route_to_agent and stop.
```

```json
// route_to_agent tool
{
  "name": "route_to_agent",
  "parameters": {
    "type": "object",
    "properties": {
      "target": {"enum": ["INTAKE","TRIAGE","MATCH","BOOK","FOLLOWUP","RECEPTIONIST","EMERGENCY","END"]},
      "reason": {"type": "string"},
      "confidence": {"type": "number", "minimum": 0, "maximum": 1}
    },
    "required": ["target","reason","confidence"]
  }
}
```

If `confidence < 0.55`, the graph routes to INTAKE (safest: ask a clarifying question) rather than guessing.

### 3.3 Conversational state object

```json
{
  "session_id": "sess_01H...",
  "patient_id": "pt_01H... | null",
  "channel": "whatsapp | app | voice | sms",
  "language": "hi-IN",
  "active_agent": "TRIAGE",
  "intent": "find_care",
  "emergency_signal": false,
  "slots": {
    "demographics": {"age": 34, "sex": "F", "pregnant": false, "location_pincode": "560001"},
    "symptoms": [{"name": "fever", "duration_days": 3, "severity": "moderate"}],
    "preferences": {"language": "hi-IN", "doctor_gender": "any", "mode": "in_person", "max_fee_inr": 800}
  },
  "triage": {"urgency": null, "recommended_specialty": null, "rationale": null},
  "candidate_doctors": [],
  "selected_doctor_id": null,
  "selected_slot_id": null,
  "booking_workflow_id": null,
  "rolling_summary": "Patient F/34 Bangalore, 3-day fever...",
  "consent": {"store_health_data": true, "marketing": false},
  "turn_count": 7
}
```

### 3.4 Retry & failure strategy

| Failure | Strategy |
|---------|----------|
| LLM timeout/5xx | Gateway retries 2× (jittered) then fails over to next provider |
| Structured output invalid JSON | Re-ask once with the validation error appended; then deterministic fallback (route to INTAKE / ask human) |
| Tool/DB error (transient) | Exponential backoff in Temporal activity (3 attempts) |
| Tool error (permanent, e.g. no slots) | Surface gracefully, offer alternatives, never crash the conversation |
| Provider safety-block on legit query | Retry on fallback provider; if all block, return safe canned message + human handoff |
| Router low confidence | Fall back to INTAKE clarifying question |
| Booking double-submit | Temporal idempotency key (`session_id + slot_id`) guarantees exactly-once |

---

## 4. The Seven Agents

For each agent: responsibilities · inputs/outputs (JSON schemas) · system prompt · memory · tools · escalation · fallback · hallucination prevention · safety.

---

### AGENT 1 — Patient Intake Agent

**Responsibilities**
- Greet, detect language, establish channel context.
- Collect minimal demographics (age, sex, pincode, risk flags) and structured symptom description.
- Detect red flags *during* intake and preempt to EMERGENCY.
- Normalize free-text symptoms into a structured list; ask clarifying questions (one at a time, conversational).
- Obtain consent for storing health data before persisting to Postgres.

**Input schema**
```json
{
  "session_id": "string",
  "user_message": "string",
  "channel": "whatsapp|app|voice|sms",
  "detected_language": "string|null",
  "session_slots": { "demographics": {}, "symptoms": [] }
}
```

**Output schema**
```json
{
  "reply_text": "string",
  "slots_update": {
    "demographics": {"age": 0, "sex": "M|F|O|unknown", "pregnant": false,
                     "immunocompromised": false, "location_pincode": "string"},
    "symptoms": [{"name": "string", "duration_days": 0,
                  "severity": "mild|moderate|severe|unknown",
                  "onset": "sudden|gradual|unknown"}]
  },
  "intake_complete": false,
  "emergency_signal": false,
  "next_question": "string|null",
  "disclaimer": "string"
}
```

**System prompt**
```
You are the DoctorFind Intake Assistant for patients in India. You are warm,
brief, and respectful. You collect basic info to help route the patient to
the right care. You are NOT a doctor and you do NOT diagnose.

<GLOBAL SAFETY RULES injected here>

YOUR JOB:
1. Greet in the user's language and ask how you can help.
2. Collect, conversationally and ONE question at a time:
   - age, sex, location (pincode or city)
   - main symptom(s): what, how long, how severe, sudden or gradual
   - risk flags: pregnancy, age 65+, known serious conditions (only if
     volunteered or clearly relevant)
3. Continuously scan EVERY message for red-flag emergencies. If found, set
   emergency_signal=true, do NOT continue intake, and let the system escalate.
4. When you have enough to triage (at least 1 symptom + duration + age),
   set intake_complete=true.

RULES:
- Ask ONE question per turn. Never interrogate.
- Do NOT suggest causes, diagnoses, tests, or medicines.
- Do NOT guess unstated facts. If unknown, mark "unknown".
- Before storing any health info long-term, confirm consent in plain language.
- Always return structured slots_update + a localized disclaimer.
- If user asks "what do I have?" reply that you can't diagnose but can help
  them see the right doctor.

OUTPUT: Always return valid JSON matching the Intake output schema.
```

**Memory:** writes to `session.slots` (Redis) every turn; promotes to `patient_profile`/`patient_episode` (Postgres) only after `consent.store_health_data == true` via `persist_episode`.

**Tools**
```python
detect_language(text: str) -> {"language": str, "confidence": float}
normalize_symptoms(free_text: str, language: str) -> list[Symptom]   # LLM+lexicon, returns SNOMED-lite tags
check_red_flags(symptoms: list, demographics: dict) -> {"emergency": bool, "matched": list[str]}
get_patient_profile(patient_id: str) -> PatientProfile | None
persist_episode(patient_id: str, episode: dict, consent_ref: str) -> {"episode_id": str}
localized_disclaimer(language: str, context: "intake") -> {"text": str}
```

**Escalation:** any `check_red_flags.emergency == true` → set `emergency_signal`, supervisor routes to EMERGENCY. Ambiguous severe wording ("I can't breathe well") → treat as red flag (err toward escalation).

**Fallback:** if language detection fails → default to English + ask preferred language. If symptom normalization fails → keep raw text and ask one clarifying question.

**Hallucination prevention:** structured output only; symptoms must be either user-stated or marked `unknown`; never infer demographics; no medical content generation.

**Safety:** data minimization, consent gate, no diagnosis, red-flag scanning every turn.

---

### AGENT 2 — Triage Agent

**Responsibilities**
- Convert structured symptoms + demographics into an **urgency level** and a **recommended care pathway** (specialty + care setting), NOT a diagnosis.
- Decide: emergency / urgent (same-day) / soon (24–72h) / routine / self-care-with-monitoring.
- Produce a plain-language rationale and the safety disclaimer.
- Lower thresholds for vulnerable groups.

**Urgency taxonomy**
```
EMERGENCY      -> call 108/112, go to ER now (red flags)
URGENT         -> see a doctor today / teleconsult now
SOON           -> book within 24-72h
ROUTINE        -> book at convenience
SELF_CARE      -> general well-being guidance + monitor + re-triage if worse
```

**Input schema**
```json
{
  "demographics": {"age": 0, "sex": "string", "pregnant": false,
                   "immunocompromised": false},
  "symptoms": [{"name": "string", "duration_days": 0, "severity": "string",
                "onset": "string"}],
  "language": "string"
}
```

**Output schema (tool-forced — the model MUST call `emit_triage`)**
```json
{
  "urgency": "EMERGENCY|URGENT|SOON|ROUTINE|SELF_CARE",
  "recommended_specialty": "General Physician|Pediatrics|Cardiology|...",
  "care_setting": "emergency|in_person|teleconsult|either",
  "red_flags_checked": ["chest_pain", "..."],
  "rationale_plain": "string (no diagnosis, urgency-only)",
  "confidence": 0.0,
  "needs_human_review": false,
  "disclaimer": "string"
}
```

**System prompt**
```
You are the DoctorFind Triage Assistant for India. You assess URGENCY and
recommend the RIGHT KIND of doctor and care setting. You DO NOT diagnose,
name diseases, suggest tests, or recommend medicines.

<GLOBAL SAFETY RULES injected here>

DECISION PROCESS:
1. First check red flags. ANY red flag => urgency=EMERGENCY,
   care_setting=emergency, and stop.
2. Otherwise grade urgency using duration, severity, onset, and risk group.
   - Sudden onset + severe => at least URGENT.
   - Vulnerable group (age<2 or >65, pregnant, immunocompromised) =>
     raise urgency by one level.
   - Persistent (>2 weeks) mild => ROUTINE with possible investigation by
     a doctor (do not name the investigation).
3. Map to a recommended SPECIALTY (route to General Physician when unsure;
   GP is the safe default).
4. Choose care_setting: teleconsult is fine for mild/routine; in_person for
   things needing examination; emergency for red flags.
5. Write rationale_plain in the user's language: explain WHY this urgency,
   in terms a layperson understands, WITHOUT naming a diagnosis.

HARD RULES:
- Never output a disease name or differential. Talk about "symptoms that
  should be evaluated", never "this looks like X".
- Never recommend a specific medicine, dose, or test.
- If symptoms are too vague to grade, set urgency=SOON,
  recommended_specialty="General Physician", needs_human_review=true.
- If confidence < 0.6, set needs_human_review=true.
- You MUST respond by calling emit_triage. No free text.
```

> **Why tool-forcing here:** triage is the highest-stakes reasoning step. Forcing a single structured tool call (`emit_triage`) eliminates rambling, blocks accidental diagnosis prose, and yields a validated record we can evaluate and audit. For the *final urgency adjudication* the gateway prefers Claude (strong refusal + reliable structured output); conversational turns can stay on Gemini Flash.

**Memory:** reads `session.slots`; writes `session.triage`; persists triage record to `patient_episode.triage` (audited).

**Tools**
```python
emit_triage(payload: TriagePayload) -> {"ok": true}            # the ONLY output path
check_red_flags(symptoms, demographics) -> {...}                # re-check, defense in depth
specialty_lookup(symptoms, demographics) -> [ {specialty, weight} ]  # pgvector symptom->specialty map
localized_disclaimer(language, context="triage") -> {"text": str}
emergency_escalation(session_id, reason) -> {"escalation_id": str}
```

**Escalation:** EMERGENCY urgency → `emergency_escalation` (preempts everything). `needs_human_review == true` (low confidence, vulnerable + ambiguous) → flag for a clinician/nurse line review before booking advice is finalized (non-blocking for routine).

**Fallback:** vague input → default GP + SOON + human review. specialty_lookup empty → General Physician.

**Hallucination prevention:** tool-forced structured output; specialty restricted to an enum of *actual specialties present in our doctor DB* (cannot recommend a specialty we can't book); rationale post-checked by a regex/LLM classifier that rejects disease-name patterns.

**Safety:** urgency-only output, vulnerable-group escalation, defense-in-depth red-flag re-check, low-confidence → human.

```
TRIAGE FLOW (ASCII)

 symptoms+demographics
        │
        ▼
 ┌───────────────┐   yes   ┌────────────────────────────┐
 │ red flag?     ├────────▶│ urgency=EMERGENCY           │
 └──────┬────────┘         │ emergency_escalation()      │
        │ no               │ -> 108/112 + nearest ER     │
        ▼                  │ -> human handoff queue      │
 ┌───────────────┐         └────────────────────────────┘
 │ vulnerable    │ yes
 │ group?        ├──┐ (raise urgency one level)
 └──────┬────────┘  │
        │ no        ▼
        ▼      ┌──────────────┐
 ┌───────────────┐  grade by  │
 │ grade urgency │◀───────────┘
 │ (dur/sev/onset)│
 └──────┬────────┘
        ▼
 ┌───────────────┐  conf<0.6 / vague  ┌─────────────────────┐
 │ confident?    ├───────────────────▶│ GP + SOON +         │
 └──────┬────────┘                    │ needs_human_review  │
        │ yes                         └─────────────────────┘
        ▼
 ┌────────────────────────────────────────────┐
 │ emit_triage(urgency, specialty, setting,    │
 │ rationale, disclaimer) -> MATCH agent       │
 └────────────────────────────────────────────┘
```

---

### AGENT 3 — Doctor Matching Agent (RAG + ranking)

**Responsibilities**
- Given recommended specialty + patient preferences + location, retrieve and **rank real doctors** from the DB.
- Explain *why* each doctor was suggested, grounded strictly in DB fields, with citations to row ids.
- Respect filters: language, gender, fee ceiling, distance, mode (in-person/tele), next available slot, rating.
- Never invent or embellish credentials.

**RAG design (pgvector)**
```
Index objects:
  doctor_embeddings(doctor_id, embedding vector(768), specialty,
                    languages[], gender, fee_inr, lat, lon, rating,
                    next_slot_ts, tele_enabled, verified)
  symptom_specialty_map(symptom_tag, specialty, weight, embedding)

Retrieval pipeline (hybrid):
  1. STRUCTURED PREFILTER (SQL WHERE): specialty in candidates,
     pincode/geo within radius, fee <= max, mode match, verified=true,
     accepting_patients=true.        <-- hard constraints, deterministic
  2. VECTOR SEARCH: embed a query string built from
     {specialty, symptom tags, preferences} and run
     cosine ANN (ivfflat/hnsw) over the prefiltered set, top-50.
  3. RERANK: deterministic score =
        0.35*semantic + 0.20*distance_decay + 0.15*rating
      + 0.15*availability(next_slot soon) + 0.15*pref_match(lang/gender/fee)
  4. RETURN top-5 rows (full structured fields) to the LLM as context.

The LLM ONLY chooses ordering/explanations from these 5 rows.
It cannot add doctors. (tool-forced selection over a fixed candidate set)
```

**Input schema**
```json
{
  "recommended_specialty": "string",
  "care_setting": "in_person|teleconsult|either",
  "preferences": {"language": "string", "doctor_gender": "any|M|F",
                  "max_fee_inr": 0, "max_distance_km": 0},
  "location": {"pincode": "string", "lat": 0, "lon": 0},
  "language": "string"
}
```

**Output schema**
```json
{
  "candidates": [
    {"doctor_id": "doc_123", "name": "string", "specialty": "string",
     "qualifications": "string", "languages": ["hi","en"], "gender": "F",
     "fee_inr": 600, "distance_km": 2.3, "rating": 4.6,
     "next_slot_ts": "2026-06-15T17:30:00+05:30", "mode": "in_person",
     "why": "Closest verified GP speaking Hindi with a slot today",
     "source_row_id": "doc_123"}
  ],
  "no_results": false,
  "reply_text": "string",
  "disclaimer": "string"
}
```

**System prompt**
```
You are the DoctorFind Doctor Matching Assistant for India. You help the
patient choose among REAL doctors retrieved from our verified database.

<GLOBAL SAFETY RULES injected here>

YOU ARE GIVEN: a list of up to 5 candidate doctors (CANDIDATES), each with a
doctor_id and verified fields. You may ONLY talk about doctors in CANDIDATES.

RULES:
1. NEVER invent, rename, or alter any doctor, qualification, fee, language,
   distance, rating, or slot. Use ONLY the fields provided.
2. For each doctor you present, set source_row_id to that doctor_id (citation).
3. Order by best fit to the patient's stated preferences and urgency
   (availability matters more for URGENT/SOON).
4. Write a short, honest "why" per doctor using only provided fields
   (e.g., "Speaks Hindi, 2.3 km away, available today 5:30 PM").
5. If CANDIDATES is empty, set no_results=true and suggest relaxing a filter
   (wider radius, teleconsult, higher fee) — do NOT fabricate doctors.
6. Do not give medical advice or comment on which doctor is "better" clinically.
7. Present fees transparently in INR. Mention if teleconsult is available.

OUTPUT: valid JSON per the Matching output schema, citing source_row_id for
every doctor.
```

**Memory:** reads `session.triage` + `session.slots.preferences`; writes `session.candidate_doctors` (with row ids, for the Booking agent to reference).

**Tools**
```python
prefilter_doctors(specialty, geo, max_fee, mode, lang, gender) -> [doctor_id]
vector_search_doctors(query_text: str, candidate_ids: list, top_k=50) -> [hit]
rerank_doctors(hits: list, prefs: dict, location: dict, urgency: str) -> [doctor]  # deterministic
get_doctor_card(doctor_id: str) -> DoctorCard          # canonical fields, for citation
expand_search(filters: dict, relax: "radius|fee|mode") -> [doctor]
localized_disclaimer(language, context="matching") -> {"text": str}
```

**Escalation:** if user re-describes worsening symptoms → re-route to TRIAGE. No clinical escalation here (non-clinical agent).

**Fallback:** empty results → progressively relax filters (radius → mode=tele → fee) and re-query; if still empty, offer waitlist / human assistance, never fabricate.

**Hallucination prevention (core):** *closed-set selection* — the LLM can only reference the retrieved candidate set; every presented doctor carries a `source_row_id` validated to exist in `candidate_doctors`; a post-processor drops any doctor whose id isn't in the retrieved set. Numeric fields (fee, distance, slot) are re-injected from the DB row after generation (the LLM's copy is overwritten by canonical values to prevent numeric drift).

**Safety:** verified doctors only (`verified=true`), no clinical ranking claims, transparent fees, citations.

---

### AGENT 4 — Booking Agent (DETERMINISTIC, Temporal-backed)

> This is intentionally the *least* agentic. The LLM only does NLU (extract which doctor/slot/intent). The actual booking is a deterministic Temporal workflow with strict states. **No LLM is in the commit path.**

**Responsibilities**
- Interpret user's booking intent (book / reschedule / cancel / confirm).
- Resolve the chosen doctor + slot against canonical availability (real-time).
- Drive the deterministic booking state machine: hold slot → collect required info → payment (if applicable) → confirm → notify.
- Guarantee no double-booking and exactly-once payment via Temporal idempotency.

**Booking state machine (Temporal workflow)**
```
INIT -> SLOT_SELECTED -> SLOT_HELD(ttl=5m) -> DETAILS_COLLECTED
     -> PAYMENT_PENDING -> PAYMENT_CONFIRMED -> BOOKED -> NOTIFIED
                       \-> PAYMENT_FAILED -> (retry|release hold)
SLOT_HELD --expire--> RELEASED -> INIT
any state --user cancel--> CANCELLED (release hold, refund if charged)
```

**Input schema (NLU)**
```json
{
  "user_message": "string",
  "candidate_doctors": [{"doctor_id": "string", "next_slot_ts": "string"}],
  "selected_doctor_id": "string|null",
  "language": "string"
}
```

**NLU output schema (LLM) — tool-forced**
```json
{
  "action": "book|reschedule|cancel|confirm|choose_doctor|choose_slot|none",
  "doctor_id": "string|null",
  "slot_id": "string|null",
  "needs": ["patient_name","phone","reason_note"],
  "reply_text": "string"
}
```

**Booking result (from Temporal, deterministic — NOT LLM)**
```json
{
  "booking_id": "bkg_01H...",
  "status": "BOOKED|HELD|PAYMENT_PENDING|FAILED|CANCELLED",
  "doctor_id": "doc_123",
  "slot_ts": "2026-06-15T17:30:00+05:30",
  "amount_inr": 600,
  "payment_status": "paid|pending|not_required|refunded",
  "confirmation_message": "string",
  "ics_link": "string|null"
}
```

**System prompt (thin NLU only)**
```
You are the DoctorFind Booking Interpreter. You DO NOT book anything yourself.
You only understand what the user wants and extract structured fields. The
booking system (deterministic) performs all actions.

<GLOBAL SAFETY RULES injected here>

YOUR JOB:
1. Determine the action: book / reschedule / cancel / confirm / choose_doctor
   / choose_slot / none.
2. Resolve doctor_id and slot_id ONLY from the provided candidate_doctors /
   prior selection. If the user names a doctor not in the list, set action
   based on intent but leave doctor_id null and ask which listed doctor.
3. List any still-needed fields in "needs".
4. Confirm critical details back to the user before the system commits
   (doctor name, date/time, fee). Do not promise a booking is done — the
   system confirms that.

HARD RULES:
- Never state a slot is booked, paid, or confirmed unless the system result
  says so. Never invent booking ids, prices, or times.
- Never alter fees or times. Use canonical values from the system.
- Money/availability are handled by the deterministic workflow, not you.

OUTPUT: valid JSON per the Booking NLU schema.
```

**Memory:** reads `candidate_doctors`, `selected_doctor_id`; writes `session.booking_workflow_id`. Booking facts live in Postgres (`bookings`), source of truth.

**Tools (deterministic activities, called by Temporal — LLM does not call commit tools directly)**
```python
get_realtime_availability(doctor_id: str, date: str) -> [Slot]
hold_slot(doctor_id: str, slot_id: str, session_id: str, ttl_s=300)
          -> {"hold_id": str, "expires_at": str}     # idempotency_key = session+slot
release_hold(hold_id: str) -> {"ok": bool}
create_booking(hold_id, patient_id, reason_note) -> {"booking_id", "amount_inr"}
initiate_payment(booking_id, amount_inr, method) -> {"payment_intent", "upi_link"}
confirm_payment(payment_intent) -> {"payment_status"}
finalize_booking(booking_id) -> BookingResult
cancel_booking(booking_id, reason) -> {"status","refund_status"}
send_confirmation(booking_id, channel) -> {"ok": bool}
generate_ics(booking_id) -> {"ics_link": str}
```

**Escalation:** payment repeatedly failing → offer pay-at-clinic or human support. Slot contention/race → re-query availability and offer alternatives. Any clinical worry mid-booking → route to TRIAGE.

**Fallback:** hold expired → re-acquire or offer next slot. Payment gateway down → fall back to alternate PG / pay-at-clinic. Temporal activity failure → automatic retry (idempotent), then graceful message.

**Hallucination prevention:** the LLM is *not* in the commit path; all booking facts (id, time, fee, status) come from Temporal/DB and are echoed verbatim. The reply template for confirmations is rendered from the `BookingResult`, not free-generated.

**Safety:** explicit confirmation before commit; exactly-once payment via idempotency keys; no booking claim without system confirmation; refund handling on cancel.

```
BOOKING FLOW (ASCII)

 user: "book Dr X at 5:30"
        │
        ▼
 ┌──────────────────────┐   action=book, doctor_id, slot_id
 │ Booking Interpreter  │──────────────────┐
 │ (LLM NLU only)       │                  │
 └──────────────────────┘                  ▼
                                 ┌───────────────────────────┐
                                 │ Temporal Booking Workflow  │
                                 │ (deterministic, durable)   │
                                 └─────────────┬─────────────┘
        get_realtime_availability              │
                 │ valid?                       │
        ┌────────┴────────┐                     │
        ▼ no              ▼ yes                  │
   offer alt slot   hold_slot(ttl 5m)           │
                         │                       │
                         ▼                       │
                 collect name/phone/reason       │
                         │                       │
                  fee>0? ─┬── yes ─▶ initiate_payment(UPI) ─▶ confirm_payment
                         │ no                              │ fail │ ok
                         ▼                                 ▼      ▼
                  finalize_booking ◀─────────────── retry/release  finalize
                         │
                         ▼
                  send_confirmation (WA/SMS) + generate_ics
                         │
                         ▼  status=BOOKED  ->  schedule Reminder workflow
                  render confirmation_message (template, NOT LLM)
```

---

### AGENT 5 — Reminder Agent (deterministic, scheduled)

**Responsibilities**
- On `BOOKED`, schedule a reminder cadence (e.g., T-24h, T-2h) via Temporal timers.
- Send localized, **templated** reminders over WhatsApp/SMS/voice.
- Handle inbound replies ("confirm", "reschedule", "cancel") by routing to Booking.
- Track delivery/read; retry channel fallback (WA → SMS → voice).

**Why deterministic:** reminders are time-triggered, templated, and compliance-sensitive (WhatsApp template policy). No generative freedom needed.

**Input schema**
```json
{
  "booking_id": "string",
  "patient_id": "string",
  "channel_pref": ["whatsapp","sms","voice"],
  "language": "string",
  "appointment_ts": "string"
}
```

**Output / event schema**
```json
{
  "reminder_id": "string",
  "stage": "T-24h|T-2h|missed_followup",
  "status": "scheduled|sent|delivered|read|failed|responded",
  "user_response": "confirm|reschedule|cancel|none",
  "next_action": "none|route_booking"
}
```

**System prompt (only for parsing free-text replies; sending is templated)**
```
You are the DoctorFind Reminder Reply Interpreter. Reminders are sent as
approved templates; you ONLY interpret the patient's free-text reply.

<GLOBAL SAFETY RULES injected here>

Classify the reply into exactly one: confirm | reschedule | cancel | other.
If "other" contains health concerns or red flags, set escalate=true so the
system can route to triage/emergency.
Do not generate medical content. Output JSON: {"intent": "...", "escalate": bool}.
```

**Memory:** reads `bookings` (Postgres); reminder state in Temporal + `reminders` table. No PHI in message bodies beyond first name + doctor + time.

**Tools**
```python
schedule_reminders(booking_id, appointment_ts, cadence) -> [reminder_id]
send_template_message(patient_id, template_id, vars, channel) -> {"msg_id","status"}
check_delivery(msg_id) -> {"status"}
fallback_channel(reminder_id) -> {"new_channel"}
route_to_booking(session_id, action) -> {"ok"}
```

**Escalation:** reply contains red-flag wording → set escalate, route to EMERGENCY/TRIAGE. "Cancel"/"reschedule" → Booking agent.

**Fallback:** WA undelivered → SMS → automated voice call (Exotel). Unknown reply → send one clarifying templated quick-reply (Confirm / Reschedule / Cancel buttons).

**Hallucination prevention:** outbound is 100% template-rendered from booking fields; the LLM only classifies inbound replies (constrained enum).

**Safety:** PHI-minimal messages, opt-out honoring, WhatsApp template compliance, red-flag detection on replies.

---

### AGENT 6 — Voice Receptionist Agent (real-time)

**Responsibilities**
- Answer inbound clinic/patient phone calls (Exotel/LiveKit/Twilio) in real time.
- Full duplex: STT (Deepgram/Whisper) → LLM → TTS (ElevenLabs/Azure), low latency.
- Do everything the chat agents do (intake → triage → match → book) but voice-optimized: short turns, barge-in, confirmations read back.
- Detect emergencies immediately and connect to 108/112 or transfer to a human.

**Latency budget**
```
target end-to-end response < 1.2s:
  STT partial/final ...... ~300ms
  LLM first token ........ ~400ms (Gemini Flash streaming; voice route prefers
                                    fastest provider; 3s hard timeout)
  TTS first audio ........ ~250ms (streaming)
  network/buffer ......... ~250ms
Strategies: streaming STT+LLM+TTS, sentence-level TTS, barge-in (cancel TTS
on user speech), filler/backchannel ("okay, one moment") during tool calls.
```

**Input schema (per turn)**
```json
{
  "call_id": "string",
  "asr_transcript": "string",
  "is_final": true,
  "language": "string",
  "caller_id": "string|null",
  "session_slots": {}
}
```

**Output schema**
```json
{
  "say_text": "string",          // short, TTS-friendly, no markdown/lists
  "action": "continue|transfer_human|emergency|hangup|dtmf_prompt",
  "slots_update": {},
  "emergency_signal": false,
  "barge_in_allowed": true
}
```

**System prompt**
```
You are the DoctorFind Voice Receptionist for an Indian clinic. You speak
naturally and briefly, like a polite human receptionist. You are NOT a doctor
and you do NOT diagnose.

<GLOBAL SAFETY RULES injected here>

VOICE STYLE:
- Keep each reply to 1-2 short sentences. No lists, no markdown, no emojis.
- Speak the caller's language. Numbers, dates, times spoken naturally
  (e.g., "five thirty PM today").
- Read back critical details for confirmation (name, doctor, time, fee).
- Allow interruptions; if interrupted, stop and listen.

CALL FLOW:
1. Greet, identify the clinic, ask how you can help.
2. If a red-flag emergency is described, immediately say a calm safety line
   and set action="emergency" (system connects 108/112 / transfers human).
3. Collect intake -> triage -> offer doctors/slots -> confirm booking.
4. For payments, send a UPI/payment link by SMS/WhatsApp; do not take card
   numbers over the phone.
5. If the caller asks for something you can't do or wants a human, set
   action="transfer_human".

HARD RULES:
- Never diagnose, prescribe, or read out lab results.
- Never invent doctors, slots, fees, or booking confirmations — use system
  data only.
- Confirm before booking. End health calls with the spoken disclaimer.
```

**Memory:** Redis session keyed by `call_id` (24h for callbacks); links to `patient_profile` if caller_id matches a known patient (with verification).

**Tools:** same tool layer as chat agents (intake/triage/match/booking tools) **plus**:
```python
transfer_to_human(call_id, queue: "nurse|reception|emergency") -> {"ok"}
connect_emergency(call_id, location) -> {"connected_to": "108|112"}
send_link_sms(call_id, link_type: "payment|directions") -> {"ok"}
play_dtmf_menu(call_id, options) -> {"selection"}
```

**Escalation:** red flag → `connect_emergency` + human. Caller distress / repeated misunderstanding / explicit request → `transfer_to_human`. Payment → out-of-band link (never card-on-call).

**Fallback:** ASR low confidence → ask caller to repeat or offer DTMF menu. LLM timeout (>3s) → play backchannel, retry on fallback provider; if persistent → transfer to human. Noisy line → switch to DTMF.

**Hallucination prevention:** same closed-set/citation discipline; numeric facts read from DB; short-turn structured outputs validated before TTS; no free-form medical content.

**Safety:** spoken disclaimer, no card-on-phone (PCI), immediate emergency routing, human-transfer always available, call recording consent prompt.

---

### AGENT 7 — Follow-up Agent (semi-agentic, scheduled)

**Responsibilities**
- After an appointment (`completed`/`no_show`), check in: how is the patient feeling, any worsening, did they get prescribed follow-up, satisfaction.
- Re-triage if symptoms worsened (route back to TRIAGE/EMERGENCY).
- Nudge for follow-up booking, collect rating/feedback, capture outcome for analytics.
- Respect quiet hours and opt-out.

**Input schema**
```json
{
  "booking_id": "string",
  "patient_id": "string",
  "appointment_outcome": "completed|no_show",
  "days_since": 0,
  "language": "string",
  "user_message": "string|null"
}
```

**Output schema**
```json
{
  "reply_text": "string",
  "wellbeing": "better|same|worse|unknown",
  "rebook_suggested": false,
  "rating_collected": null,
  "emergency_signal": false,
  "disclaimer": "string"
}
```

**System prompt**
```
You are the DoctorFind Follow-up Assistant for India. You gently check in
after an appointment. You are NOT a doctor and you do NOT diagnose.

<GLOBAL SAFETY RULES injected here>

YOUR JOB:
1. Ask, warmly and briefly, how the patient is feeling since their visit.
2. Scan for red flags or worsening EVERY turn. If worse or red flags:
   - set emergency_signal appropriately and recommend seeing a doctor /
     emergency services; offer to re-triage or rebook.
3. If they missed the appointment (no_show), offer to rebook.
4. Collect a simple satisfaction rating (1-5) and optional feedback.
5. Do NOT comment on their treatment, medicines, or test results. If asked,
   say that's for their doctor and offer to help them rebook.

HARD RULES:
- No diagnosis, no medicine/test advice, no interpreting prescriptions.
- Respect quiet hours and opt-out; if they say stop, acknowledge and end.
- End health turns with the localized disclaimer.

OUTPUT: valid JSON per the Follow-up schema.
```

**Memory:** reads `patient_episode` + `bookings`; writes outcome to `patient_episode.outcome`, `feedback`, and re-triage results.

**Tools**
```python
get_episode(booking_id) -> Episode
check_red_flags(symptoms, demographics) -> {...}
route_to_triage(session_id) -> {"ok"}
suggest_rebook(patient_id, specialty) -> [Slot]
record_feedback(booking_id, rating, comment) -> {"ok"}
localized_disclaimer(language, context="followup") -> {"text"}
respect_opt_out(patient_id) -> {"opted_out": bool}
```

**Escalation:** worsening/red flags → EMERGENCY/TRIAGE. Strong dissatisfaction / complaint → human care-team queue.

**Fallback:** no response after N nudges (respecting cadence + quiet hours) → close gracefully. Ambiguous reply → one clarifying question.

**Hallucination prevention:** no treatment commentary; structured wellbeing enum; rebook slots from DB only; disclaimer via tool.

**Safety:** quiet hours, opt-out, no treatment/test interpretation, red-flag scanning, human handoff for complaints.

---

## 5. Deterministic vs Agentic — When to Use Which

**Principle:** Use **deterministic** flows where correctness, money, time, and clinical urgency are at stake and the action space is closed. Use **agentic** flows where the input is open-ended natural language and the value is in *understanding and navigation*.

| Criterion | Prefer DETERMINISTIC | Prefer AGENTIC |
|-----------|----------------------|----------------|
| Action commits money | ✅ Booking, payments, refunds | ❌ |
| Mutates shared calendar/availability | ✅ Slot hold/confirm | ❌ |
| Clinical-safety critical, fixed protocol | ✅ Emergency escalation, red-flag routing | ❌ |
| Output must be exact/auditable/reproducible | ✅ Confirmations, reminders, invoices | ❌ |
| Regulatory/compliance templates (WA, DPDP) | ✅ Templated messaging | ❌ |
| Closed, enumerable action set | ✅ State machine | ❌ |
| Open-ended NL understanding | ❌ | ✅ Intake, symptom normalization |
| Navigating ambiguity / clarifying questions | ❌ | ✅ Triage conversation, follow-up |
| Ranking/explaining over retrieved data | partly (rerank=deterministic) | ✅ Explanation/ordering nuance |
| Many valid phrasings, one goal | ❌ | ✅ Conversational steering |
| Latency-critical, high-volume, low-variance | ✅ | ❌ |

**Concrete mapping in DoctorFind**
- **Deterministic:** booking state machine, payments, slot availability, reminders, emergency escalation, confirmation/invoice rendering, RAG prefilter + rerank scoring. → **Temporal** + pure functions.
- **Agentic:** intake conversation, triage reasoning/navigation, doctor-match explanation/ordering, voice dialogue management, follow-up check-ins. → **LangGraph** + LLM.
- **Hybrid (the key pattern):** *agentic understanding feeds deterministic execution.* The LLM extracts intent/fields; a deterministic workflow performs the irreversible act. E.g., Booking Agent (LLM NLU) → Temporal (commit). This bounds LLM blast radius to "misunderstanding" (recoverable) rather than "miscommitting money" (not).

---

## 6. AI Evaluation Metrics

### 6.1 Safety & triage (highest priority)

| Metric | Definition | Target |
|--------|------------|--------|
| **Escalation recall (red-flag sensitivity)** | % of true emergencies correctly escalated | ≥ 99% (false negatives are unacceptable) |
| **Escalation precision** | % of escalations that were warranted | ≥ 70% (over-triage tolerated) |
| **Triage routing accuracy** | % of cases routed to clinically-appropriate specialty/urgency vs clinician gold label | ≥ 90% |
| **Under-triage rate** | % cases assigned lower urgency than gold | ≤ 1% for emergency band |
| **Diagnosis-leak rate** | % responses containing a disease name / med advice (forbidden) | 0% (hard gate) |
| **Disclaimer presence** | % health turns ending with disclaimer | 100% |

### 6.2 Task & conversation quality

| Metric | Definition | Target |
|--------|------------|--------|
| **Containment rate** | % sessions resolved without human handoff (excluding intended escalations) | ≥ 75% |
| **Booking completion rate** | % intent-to-book sessions ending in BOOKED | ≥ 60% |
| **Slot-resolution accuracy** | % bookings matching the slot the user intended | ≥ 99% |
| **Turns-to-resolution** | median turns from start to booking | ≤ 8 |
| **Match relevance (NDCG@5)** | ranking quality vs human-judged relevance | ≥ 0.8 |
| **Citation validity** | % presented doctors whose source_row_id exists in retrieval set | 100% |
| **Numeric fidelity** | % fees/slots in replies matching DB exactly | 100% |

### 6.3 Voice & ops

| Metric | Target |
|--------|--------|
| ASR WER (per language) | ≤ 15% |
| Voice response latency (p95) | ≤ 1.5s |
| Provider failover success | ≥ 99.9% |
| Structured-output parse success (post-retry) | ≥ 99.5% |
| Cost per resolved session | tracked, budgeted |

### 6.4 How we evaluate

- **Golden set:** clinician-labeled triage cases (urgency + specialty) across languages and vulnerable groups; expanded continuously from production (with consent).
- **Offline eval harness:** every prompt/model change runs against the golden set; gates deploy on escalation recall + diagnosis-leak.
- **LLM-as-judge** (with a strong model, rubric-based) for explanation quality and disclaimer/refusal compliance; sampled human review of judge.
- **Red-team suite:** adversarial prompts trying to elicit diagnosis, prescriptions, fabricated doctors, or skipped escalation.
- **Online:** shadow mode for new triage models; canary; live dashboards on the metrics above + alerting on under-triage and diagnosis-leak.

---

## 7. RAG / Retrieval Design (Doctor Matching) — details

```
EMBEDDING:
  - model: multilingual text-embedding (768-d), shared for queries & docs.
  - doc text = "{specialty} | {sub-specialties} | {conditions seen} |
                {languages} | {qualifications} | {clinic area}"
    (NO subjective marketing text; verified fields only).
  - refreshed on doctor profile change (event-driven reindex).

STORAGE (pgvector):
  CREATE INDEX ON doctor_embeddings USING hnsw (embedding vector_cosine_ops);
  -- HNSW for low-latency ANN; ivfflat acceptable for smaller datasets.

QUERY-TIME (hybrid, see §4):
  1. SQL hard prefilter (geo/fee/mode/verified/accepting).  <- precision/safety
  2. Vector ANN within prefiltered ids.                     <- semantic recall
  3. Deterministic rerank (semantic+geo+rating+avail+pref). <- explainable
  4. Top-5 canonical rows to LLM (closed set).

FRESHNESS:
  - next_slot_ts kept warm in Redis (TTL ~60s) and re-validated against
    canonical availability at booking time (never trust cached slot to commit).

GROUNDING CONTRACT:
  - LLM receives rows with ids; must cite source_row_id; numeric fields are
    overwritten from canonical DB after generation. Any doctor not in the set
    is stripped by a post-filter.
```

Also used for: `symptom_specialty_map` (symptom → specialty routing, vector + weights) and a small **policy/KB RAG** (cancellation policy, refund rules, clinic FAQs) — answered only from retrieved KB chunks, with refusal if not found.

---

## 8. Hallucination Mitigation (consolidated)

1. **Grounding to DB rows.** Every factual claim (doctor, fee, slot, policy) must come from a tool result; numeric values are re-injected from canonical rows post-generation.
2. **Closed-set selection.** Matching can only choose among retrieved candidates; out-of-set entities are stripped by a deterministic post-filter.
3. **Tool-forcing.** Triage (`emit_triage`), Supervisor (`route_to_agent`), and Booking NLU MUST emit via a single tool — no free prose in high-stakes steps.
4. **Structured output + schema validation.** All agent outputs are JSON-schema-validated; invalid → one re-ask → deterministic fallback.
5. **Citations to row ids.** `source_row_id` on every recommended doctor; validated to exist.
6. **Refusal patterns.** For diagnosis/medicine/test-interpretation requests, agents refuse and redirect ("I can't diagnose, but I can help you see the right doctor"). A regex+classifier post-check rejects disease-name/med-advice patterns (diagnosis-leak gate = 0%).
7. **Enum-constrained domains.** Recommended specialty restricted to specialties that *exist and are bookable* in our DB; urgency from a fixed taxonomy.
8. **Defense-in-depth red-flag checks.** Run in Intake, Triage, Reminder replies, and Follow-up — independent of LLM judgment.
9. **No LLM in commit paths.** Money/calendar/emergency are deterministic; LLM mistakes are limited to recoverable misunderstandings.
10. **Provider failover without dropping users.** Safety-filter blocks on legitimate medical queries retry on a fallback provider rather than silently failing.
11. **Human-in-the-loop gates.** Low-confidence triage / vulnerable + ambiguous / complaints route to clinicians or care team.

---

## 9. Appendix — End-to-end happy path (text)

```
1. WhatsApp inbound (Hindi): "mujhe 3 din se bukhar hai"
2. Ingress: lang=hi-IN, load/create session.
3. Supervisor -> INTAKE: collects age/sex/pincode, normalizes symptom
   (fever, 3d, moderate, gradual), red-flag check = clear, consent captured.
4. Supervisor -> TRIAGE: emit_triage(urgency=SOON,
   specialty="General Physician", setting=either, rationale, disclaimer).
5. Supervisor -> MATCH: prefilter+vector+rerank -> top-5 verified GPs near
   560001 speaking Hindi <=₹800; presents 3 with citations + next slots.
6. User picks Dr X 5:30 PM today.
7. Supervisor -> BOOK (NLU) -> Temporal: hold_slot -> details -> UPI link ->
   confirm_payment -> finalize_booking -> send_confirmation + ICS.
8. Temporal schedules Reminder workflow (T-24h, T-2h).
9. Day after: Follow-up agent checks in; if worse -> re-triage/emergency;
   else collect rating; record outcome.
At every health turn: localized disclaimer appended by the Safety Guard.
```

---

*End of Phase 4 — AI & Agent Design.*
