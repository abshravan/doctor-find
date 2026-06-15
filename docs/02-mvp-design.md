# DoctorFind — Phase 2: MVP Design

> **Goal:** A lean, validation-focused MVP that proves the core loop — *symptom → right specialty → matched verified doctor → confirmed booking → clinic value* — with **rapid dev velocity, low ops overhead, and a clear monetization on-ramp (clinic automation).**
>
> **Design principle running through this doc:** **Start with the simplest thing that tests the hypothesis. Add intelligence only where it changes the user's decision.** Each module includes a *"Simpler alternative first"* callout so we don't over-build.

**Canonical stack (fixed, not re-debated here):** FastAPI · Next.js · React Native (Expo) · PostgreSQL + pgvector + Redis · LangGraph (agent orchestration) + Temporal (durable workflows) · Gemini Flash (primary LLM) + OpenAI/Claude (fallback) · Deepgram/Whisper (STT) · ElevenLabs/Azure (TTS) · Exotel (telephony, India) + LiveKit (web/app) + Twilio WhatsApp · MSG91 (OTP) · Gupshup / Meta WhatsApp Cloud API.

---

## 0. MVP Shape at a Glance

```
              ┌──────────────────────────────────────────────────────────┐
  CHANNELS    │  WhatsApp (primary)   Web (SEO)   Missed-call/IVR (Exotel) │
              └───────────────┬──────────────────────────────────────────┘
                              │  (voice notes, text, calls)
                              ▼
              ┌──────────────────────────────────────────────────────────┐
  ENTRY       │   STT (Deepgram/Whisper) → Language detect → Normalize     │
              └───────────────┬──────────────────────────────────────────┘
                              ▼
              ┌──────────────────────────────────────────────────────────┐
  BRAIN       │   AI Symptom Navigator  (LangGraph agent)                  │
              │   Gemini Flash + fallback · red-flag rules · disclaimers   │
              │   OUT: urgency · specialty · consult-type · matched query  │
              └───────────────┬──────────────────────────────────────────┘
                              ▼
              ┌──────────────────────────────────────────────────────────┐
  MATCH       │   Doctor Discovery (Postgres + pgvector + filters)         │
              └───────────────┬──────────────────────────────────────────┘
                              ▼
              ┌──────────────────────────────────────────────────────────┐
  ACT         │   Booking (Temporal workflows: confirm/remind/reschedule)  │
              │   WhatsApp confirmations & reminders (Gupshup/Twilio)      │
              └───────────────┬──────────────────────────────────────────┘
                              ▼
              ┌──────────────────────────────────────────────────────────┐
  CLINIC      │   Clinic Dashboard + Voice Receptionist + AI call summary  │
              └──────────────────────────────────────────────────────────┘
```

**Why this order is lean:** WhatsApp removes app-install friction; a single LangGraph agent fronts everything; Temporal makes the async booking lifecycle reliable without us hand-rolling retries/cron. We can ship the consumer loop and the clinic on-ramp on **one backend**.

---

## 1. MoSCoW Prioritization

### 1.1 MUST HAVE (the MVP is meaningless without these)

| Feature | Rationale |
|---|---|
| AI Symptom Navigator (text + voice, EN + Hindi + 1 regional) | The wedge. Without triage we're a directory clone. |
| Specialty + urgency + consult-type output with **safety disclaimers + red-flag escalation** | Core value *and* the safety/legal backbone. Non-negotiable. |
| Doctor Discovery with verified profiles + core filters (specialty, location, fee, language, availability, gender, online/offline) | The "right doctor" half of the promise; verification = trust moat. |
| Booking with real availability + **WhatsApp confirmation & reminders** | Closes the loop; reminders directly attack no-shows (clinic value). |
| WhatsApp as primary channel (Gupshup/Meta Cloud API) | India's default; lowest friction; mass-market reach. |
| OTP auth (MSG91) | Identity + anti-abuse, minimal friction. |
| Clinic Dashboard (lite): appointments, availability, patient comms | The B2B on-ramp; needed to seed supply + earn revenue. |
| Admin verification tooling | Trust depends on verified-only listings. |

### 1.2 SHOULD HAVE (high value, add fast-follow after core validates)

| Feature | Rationale |
|---|---|
| Voice AI Assistant: **missed-call → AI callback** for clinics | Strong B2B hook; differentiator; but needs telephony hardening. |
| AI **pre-visit summary** delivered to clinic | Improves matching + saves consult time; depends on triage maturity. |
| Rescheduling / cancellation self-service via WhatsApp | Reduces no-shows + ops load; build once booking is stable. |
| 2–3 more regional languages | Expands TAM; add after core language quality proven. |
| Verified-visit reviews | Trust layer; needs booking volume first. |
| Web SEO landing pages (symptom/specialty/city) | Cheap top-of-funnel; do once routing logic is solid. |

### 1.3 AVOID FOR NOW (explicitly deferred — protect focus & avoid liability)

| Feature | Why defer |
|---|---|
| Anything resembling **diagnosis / disease naming / prescriptions** | Regulatory + clinical liability; off-mission. **Permanently out.** |
| Native mobile app (Expo) at launch | WhatsApp + web cover MVP; app adds dev + distribution cost. Build after PMF. |
| Full EHR / clinical records | Heavy, regulated, slow; not needed to validate discovery. |
| In-house teleconsult video at scale | Use LiveKit only if/when supply is real; don't build a tele marketplace yet. |
| Pharmacy / diagnostics / lab integration | Partner later; ops + capital heavy. |
| Insurance / TPA integration | Phase 3 B2B2C. |
| Payments/escrow for consults | Start with pay-at-clinic + optional booking fee; avoid PG/refund complexity early. |
| Multi-city scale | Concentrate 1 metro + 1 Tier-2 for density and supply liquidity. |
| Wearables / IoT / continuous monitoring | Not the wedge. |

> **Tradeoff callout:** The temptation is to build the app + teleconsult + pharmacy ("super-app") immediately. That kills velocity and dilutes the wedge. The MVP wins by being **narrow and excellent at navigation + booking + clinic automation**, on WhatsApp/web only.

---

## 2. Module Designs

Conventions: **U** = user story, flows in ASCII, **Data**, **Edge cases**, **Defer**.

---

### MODULE 1 — AI Symptom Navigator

**Purpose:** Turn a free-form, multilingual, voice-or-text symptom description into a **safe, actionable navigation output**: urgency level, recommended specialty, consultation type (in-person vs teleconsult), and a search query — never a diagnosis.

#### User stories
- **U1:** As Aarti, I describe my child's symptoms by Hindi voice note and learn whether to go now or tomorrow and to which doctor.
- **U2:** As Rohan, I type "throat pain + fever 2 days" and get a routed recommendation + bookable doctors in one tap.
- **U3:** As Priya, I privately ask a sensitive question and get judgment-free guidance + a discreet teleconsult option.
- **U4:** As any user, if I describe a red-flag (chest pain + breathlessness), I'm immediately told to seek emergency care.

#### Key flow

```
 Patient input (voice/text, any language)
        │
        ▼
 [STT if voice] ── Deepgram/Whisper ──► transcript
        │
        ▼
 Language detect + normalize  (store original + canonical EN intent)
        │
        ▼
 ┌─────────────────────── LangGraph agent ───────────────────────┐
 │ Node A: RED-FLAG CHECK (deterministic rules FIRST, pre-LLM)    │
 │   chest pain+SOB, stroke signs, severe bleeding, suicidal      │
 │   ideation, infant high fever, anaphylaxis... → ESCALATE       │
 │                          │ no red flag                         │
 │                          ▼                                     │
 │ Node B: CLARIFY (max 2–3 follow-ups: duration? severity?       │
 │   age? key associated symptoms?)                               │
 │                          │                                     │
 │                          ▼                                     │
 │ Node C: ROUTE (LLM + curated specialty map)                    │
 │   → specialty  → urgency(now/24h/routine)  → tele vs in-person │
 │                          │                                     │
 │                          ▼                                     │
 │ Node D: SAFETY WRAP (disclaimer + "see a doctor to confirm")   │
 └───────────────────────────┬───────────────────────────────────┘
                             ▼
   Output card:  "Sounds like something a [Dermatologist] can help with.
                  Not urgent — within a few days is fine. Teleconsult works."
                  + DISCLAIMER + [Show doctors] [Talk to a human]
                             │
                             ▼
                  Hand off query → Module 2 (Discovery)
```

#### Why this architecture is safe & lean
- **Red-flag rules run BEFORE the LLM** (deterministic, auditable) — we never depend on the model to catch emergencies.
- **Curated specialty map** (a maintained taxonomy of symptom→specialty) constrains the LLM; conservative defaults (route to **GP/General Physician** or **urgent care** when uncertain — never guess a niche specialty).
- **Cap follow-ups at 2–3** — beyond that, route to GP. Avoids endless questioning and "playing doctor."

#### Data needed
- Symptom taxonomy + symptom→specialty mapping table (curated, versioned).
- Red-flag rule set (versioned, clinically reviewed).
- Disclaimer/copy library per language.
- Session transcript (original + normalized), with consent + retention policy.
- Urgency + consult-type decision log (for audit and quality tuning).
- pgvector embeddings of symptom phrasings (for retrieval consistency + analytics, *not* for diagnosis).

#### Edge cases
- **Ambiguous/multi-system symptoms** → default to GP, flag for in-person.
- **Emergency/red-flag** → stop flow, show emergency guidance + nearest hospital + 112/108; do NOT route to booking.
- **Mental-health crisis** → crisis helpline + compassionate copy; never minimize.
- **Pediatric/elderly/pregnancy** → lower urgency thresholds (more conservative).
- **Off-topic / abusive input** → graceful decline + redirect.
- **Low STT confidence / heavy dialect** → confirm transcript back / offer text or human.
- **Repeat/chronic** ("my usual BP follow-up") → shortcut to known specialty + booking.
- **User wants a diagnosis/medicine** → firmly decline, restate navigation-only role.

#### Defer
- More than 2–3 languages; deep medical-history intake; image-based triage (rash photos); integration with personal health records; multi-turn "symptom diary." 

> **Simpler alternative first:** Before a full LangGraph multi-node agent, ship a **single-prompt Gemini Flash call with a hard-coded red-flag pre-filter + a fixed specialty list in the system prompt**, returning structured JSON `{specialty, urgency, consult_type, disclaimer}`. Validate routing quality with real users, *then* graduate to LangGraph nodes once we need branching, tool calls, and clarify loops. Don't build the graph on day one.

---

### MODULE 2 — Doctor Discovery

**Purpose:** Present **verified, well-matched** doctors for the navigated need, with the filters Indian patients actually care about — and earn trust through transparency.

#### User stories
- **U1:** As Rohan, after triage I see 3–5 verified dermatologists near me with real open slots, sorted by fit.
- **U2:** As Suresh, I filter by **Tamil-speaking** and **in-person near my pin code**.
- **U3:** As Priya, I filter for **female doctor + teleconsult** for a sensitive concern.
- **U4:** As Aarti, I trust the listing because it shows a **Verified** badge and the registration is real.

#### Key flow

```
 Query from Navigator: {specialty, location, consult_type, language?, gender?}
        │
        ▼
 Candidate fetch (Postgres):  specialty + city/geo + active + verified
        │
        ▼
 Filter layer: fee range · language · gender · online/offline · availability(now/today/this week)
        │
        ▼
 Rank:  fit(specialty match, distance, availability) + trust(verified, rating) 
        + (NO pay-to-win in core ranking at MVP — preserve neutrality)
        │
        ▼
 Result cards: name · specialty · verified✔ · fee · languages · next slot · distance · [Book]
        │
        ▼
 Tap doctor → full verified profile → Module 3 (Booking)
```

#### Verified profile contents
Name, photo, qualifications, **medical registration (verified)**, specialty/sub-specialty, years of experience, languages spoken, clinic(s) + geo, consultation fee, in-person/teleconsult, availability, verified-visit reviews (Should-have), gender.

#### Data needed
- `doctors` (profile, registration no., verification status/date, languages[], gender, fee, modes).
- `clinics` (geo, address, pincode, hours).
- `doctor_clinic` (many-to-many, per-clinic fee/schedule).
- `availability` / slots (source of truth for booking).
- `specialties` taxonomy (shared with Module 1).
- `reviews` (verified-visit linked, fast-follow).
- Geo index (lat/long, pincode) for distance filtering.

#### Edge cases
- **Zero results** (rare specialty / small city) → widen radius, offer teleconsult, offer GP, or "notify when available."
- **Stale availability** → never show a slot we can't honor; reconcile with clinic source; mark "call to confirm" if unsynced.
- **Unverified/pending doctor** → exclude from core results (verified-only) or clearly label.
- **Duplicate listings** (same doctor, multiple clinics) → dedupe by registration no.
- **Fee/language data missing** → show "not specified," don't fabricate.
- **Distance vs availability tension** → let user re-sort; default to balanced fit.

#### Defer
- Sophisticated ML ranking, paid placement, insurance-network filters, sub-specialty deep trees, doctor-side profile self-editing portal (start admin-curated), review moderation at scale.

> **Simpler alternative first:** **pgvector semantic matching is overkill for MVP discovery** — the navigator already outputs a clean specialty enum. Start with **plain SQL filters + a deterministic ranking formula** on a small, hand-verified doctor set. Reserve pgvector for fuzzy symptom-phrase analytics (Module 1), not for the core doctor lookup. Manually onboard/verify the first ~100–300 doctors per city; don't build a self-serve verification pipeline yet.

---

### MODULE 3 — Booking System

**Purpose:** Convert a chosen doctor + slot into a **confirmed, reliable appointment**, with WhatsApp confirmations, reminders, and easy rescheduling — directly attacking no-shows.

#### User stories
- **U1:** As Rohan, I pick a slot and get an instant WhatsApp confirmation with clinic location + map.
- **U2:** As Aarti, I get a reminder the day before and an hour before so I don't forget.
- **U3:** As Priya, I reschedule by replying to the WhatsApp message — no phone call.
- **U4:** As Dr. Mehta, no-shows drop because patients are reminded and can self-reschedule.

#### Key flow (Temporal-orchestrated lifecycle)

```
 Select slot ──► Hold slot (Redis lock, short TTL) ──► Confirm
                                                          │
            ┌─────────────────────────────────────────────┘
            ▼   Temporal workflow: AppointmentLifecycle
   ┌───────────────────────────────────────────────────────────────┐
   │ t0   Booked        → WhatsApp confirmation (+ map, fee, prep)   │
   │ t-1d Reminder      → "Tomorrow 5pm with Dr. X. Reply R=resched, │
   │                       C=cancel, Y=confirm"                      │
   │ t-2h Reminder      → final nudge + directions                  │
   │ post Follow-up     → "How did it go?" + review prompt (later)  │
   │ anytime Reschedule → release slot, re-book, restart timers      │
   │ anytime Cancel     → release slot, notify clinic, update dash   │
   └───────────────────────────────────────────────────────────────┘
            │
            ▼
   Clinic dashboard updates in real time (Module 5)
```

#### Why Temporal here
The appointment lifecycle is **long-running, multi-step, and failure-prone** (messages, retries, timers, reschedules). Temporal gives **durable timers + retries + exactly-once-ish semantics** without us building cron + dead-letter queues. This is the *right* place for the heavier infra in the stack.

#### Data needed
- `appointments` (patient, doctor, clinic, slot, status: held/booked/confirmed/rescheduled/cancelled/completed/no_show, channel, consult_type).
- `slots` / availability source of truth.
- Patient contact + consent (WhatsApp opt-in).
- Message log (template, status, delivery).
- Workflow state (Temporal).

#### Edge cases
- **Double-booking race** → Redis slot lock + DB unique constraint; hold TTL releases abandoned carts.
- **Patient no WhatsApp opt-in** → SMS fallback (MSG91); collect opt-in at booking.
- **Clinic cancels / doctor unavailable** → proactive WhatsApp + auto-suggest alternates.
- **Reschedule loops** → cap reschedules; escalate to human after N.
- **Timezone/DST** → store UTC, render IST.
- **Message delivery failure** → retry via Temporal; fallback channel; mark "unconfirmed."
- **Walk-in vs booked conflict** → dashboard authority; clinic can block slots.
- **No-show** → mark + (optional) future deposit policy (deferred).

#### Defer
- Online payments / deposits / refunds (start **pay-at-clinic**; optional small booking fee later), waitlists, recurring appointment series, calendar (Google/ICS) sync, dynamic slot pricing.

> **Simpler alternative first:** For the *very* first pilot you could send confirmations via a simple background job. But the **reminder/reschedule timers are exactly what Temporal is for** — and they drive the no-show ROI that sells the clinic SaaS — so invest here early. Conversely, **do not build payments/escrow**: pay-at-clinic eliminates an entire class of refund/PG complexity while still validating the loop.

---

### MODULE 4 — Voice AI Assistant

**Purpose:** Multilingual voice front-door + clinic **receptionist automation**: answer/return calls, handle FAQs, capture intent, book/reschedule, and produce **AI call summaries** — turning missed calls into booked patients.

#### User stories
- **U1:** As Suresh, I call and speak Tamil; the assistant understands and books my follow-up.
- **U2:** As a patient who called Dr. Mehta's clinic after hours and got no answer, I receive an **AI callback** that books me.
- **U3:** As Dr. Mehta, the assistant handles routine "are you open / what's the fee / can I reschedule" calls so my receptionist isn't buried.
- **U4:** As Dr. Mehta, I get a **concise AI summary** of every handled call.

#### Key flow (missed-call → callback)

```
 Inbound call to clinic (Exotel)  ──► busy / unanswered / after-hours
        │
        ▼
 Missed-call event ──► queue AI callback (Temporal)
        │
        ▼
 ┌──────────────── Voice agent (LiveKit/Exotel media) ─────────────┐
 │  TTS greeting (clinic-branded, patient's likely language)        │
 │  STT (Deepgram) ↔ LangGraph dialog ↔ TTS (ElevenLabs/Azure)      │
 │  Intent: book / reschedule / FAQ / human-needed                  │
 │     • book → check availability → confirm → WhatsApp confirm     │
 │     • FAQ → answer from clinic knowledge base                    │
 │     • complex/uncertain → "I'll have the clinic call you" (esc.) │
 └───────────────────────────────┬─────────────────────────────────┘
                                 ▼
        AI CALL SUMMARY → clinic dashboard (+ booking if made)
        {caller, language, intent, outcome, action items, transcript}
```

#### Telephony split (per stack)
- **Exotel** for PSTN/India phone calls + missed-call detection (regulatory + reach).
- **LiveKit** for in-app/web voice sessions.
- Shared **STT→LangGraph→TTS** core regardless of transport.

#### Data needed
- Clinic phone config + call-handling rules + business hours.
- Clinic knowledge base (FAQs, fees, location, prep instructions).
- Call records: audio (consent!), transcript, intent, outcome, summary.
- Language preference (inferred + stored).
- Booking integration (Module 3).

#### Edge cases
- **Recording consent** → disclose at call start (legal); honor opt-out.
- **STT failure / heavy noise / dialect** → repeat-back, fall back to "human will call."
- **Medical advice request on a call** → assistant refuses, routes to navigator/human (same safety rules as Module 1).
- **Emergency on a call** → immediate emergency guidance, do not attempt to book.
- **Barge-in / interruptions / latency** → tune for low latency; allow interruption.
- **Wrong number / spam** → graceful exit.
- **Multiple clinics, one number** → routing config.

#### Defer
- Fully autonomous complex clinical conversations, outbound marketing calls, payment-over-phone, voice biometrics, sentiment analytics dashboards, >2 voice languages at launch.

> **Simpler alternative first:** The **biggest, safest win is missed-call → WhatsApp/callback for booking + FAQs** — not a fully conversational AI receptionist for every call. Phase the voice agent: **(a)** missed-call → auto WhatsApp with booking link (cheap, instant value); **(b)** missed-call → AI callback for booking only; **(c)** live AI answering with FAQs. Don't attempt full live answering until STT quality + latency + escalation are proven, because a bad voice bot erodes clinic trust fast.

---

### MODULE 5 — Clinic Dashboard

**Purpose:** The B2B surface (and revenue engine): manage appointments + availability, communicate with patients, and review **AI call summaries + pre-visit triage** — the value that makes clinics pay.

#### User stories
- **U1:** As Dr. Mehta's receptionist, I see today's appointments and confirm/reschedule in one screen.
- **U2:** As Dr. Mehta, I set availability + block slots for walk-ins/leave.
- **U3:** As Dr. Mehta, I read each patient's **pre-visit AI summary** before they walk in.
- **U4:** As Dr. Mehta, I see **AI call summaries** of every missed call we recovered.
- **U5:** As the clinic, I message patients (reminders, follow-ups) without dialing.

#### Key flow

```
 ┌──────────────────────────── Clinic Dashboard ───────────────────────────┐
 │  TODAY            │  SCHEDULE/AVAILABILITY  │  PATIENT COMMS             │
 │  ───────────────  │  ────────────────────   │  ─────────────────        │
 │  • Upcoming appts │  • Set weekly hours     │  • WhatsApp threads       │
 │  • Status chips   │  • Block/leave slots    │  • Reminders sent/failed  │
 │    booked/confirm │  • Per-doctor calendars │  • Templated messages     │
 │    /no-show       │  • Walk-in toggle       │                           │
 │                   │                         │                           │
 │  AI INSIGHTS      │  • Pre-visit triage summary per appointment          │
 │                   │  • AI call summaries (missed-call recoveries)        │
 │                   │  • No-show & recovery metrics (ROI proof)            │
 └──────────────────────────────────────────────────────────────────────────┘
        │                          ▲
        ▼                          │ real-time sync
   Updates appointments  ◀────► Booking (Module 3) & Voice (Module 4)
```

#### Why this earns money
It directly **shows the ROI**: "We recovered X missed calls and prevented Y no-shows this month." That metric *is* the sales pitch and the retention hook. Keep the dashboard **simple and outcome-focused**, not a feature-bloated EHR.

#### Data needed
- `clinics`, `clinic_users` (roles: owner/receptionist), auth.
- Appointments + statuses (shared with Module 3).
- Availability rules + overrides.
- Message logs / WhatsApp threads.
- AI summaries (call + pre-visit), linked to appointments.
- KPIs: bookings, no-show rate, missed-call recovery, response time.

#### Edge cases
- **Concurrent edits** (receptionist + AI both booking) → server-authoritative, locks, audit log.
- **Multi-doctor / multi-location** clinics → scoping + per-doctor calendars.
- **Low-tech receptionist** → ultra-simple UI; WhatsApp-driven ops as fallback; mobile-friendly.
- **Patient PII access control** → role-based, minimum-necessary, audit.
- **Offline / poor connectivity** → graceful degradation, retry sync.
- **Data trust** (clinic disputes a booking) → immutable activity log.

#### Defer
- Billing/invoicing, inventory, full EHR/clinical notes, analytics suite, staff payroll/roster, multi-branch enterprise admin, white-label.

> **Simpler alternative first:** For the first ~10–20 pilot clinics, you can run the "dashboard" partly as a **WhatsApp Business + a thin web view** rather than a full app — let clinics manage via chat while you observe what they actually need. Build the real dashboard around the **2–3 features that drive payment** (appointment view, availability, AI summaries + ROI metrics), and resist turning it into a practice-management suite.

---

## 3. Cross-Cutting Tradeoffs & Decisions

| Decision | Choice for MVP | Tradeoff |
|---|---|---|
| Channel priority | **WhatsApp first**, web for SEO, app later | Less control vs WhatsApp template/policy limits; but massive reach + zero install. |
| Triage engine | **Single structured LLM call + rule pre-filter → graduate to LangGraph** | Slightly less flexible early; far faster to ship + easier to audit. |
| Doctor matching | **SQL filters + deterministic rank** (pgvector for analytics only) | Less "smart" ranking; but explainable, neutral, fast. |
| Booking infra | **Temporal for lifecycle timers** | Heavier infra; justified by no-show ROI + reliability. |
| Payments | **Pay-at-clinic + optional booking fee** | Lower take-rate now; avoids PG/refund complexity; faster trust. |
| Voice | **Missed-call→WhatsApp/callback before live AI answering** | Slower to full automation; protects clinic trust from bad bots. |
| Supply | **Manually verified ~100–300 docs/city, geo-concentrated** | Ops effort; but liquidity + trust + quality control. |
| LLM | **Gemini Flash primary, OpenAI/Claude fallback** | Vendor risk managed via fallback; cost-optimized for high-volume triage. |
| Languages | **EN + Hindi + 1 regional at launch** | Limited reach early; quality over breadth, then expand. |

---

## 4. Safety, Trust & Compliance (woven through every module)

- **Navigation, never diagnosis.** No disease names, no prescriptions, no dosage — enforced in prompts, rules, and copy across text and voice.
- **Persistent disclaimers** on every triage output and call ("informational only; consult a qualified doctor; in an emergency call 112/108").
- **Deterministic red-flag → emergency escalation**, evaluated before any LLM routing, in chat *and* voice.
- **Verified-only listings** (medical registration verification) as the trust foundation.
- **Consent + privacy:** explicit WhatsApp opt-in, call-recording disclosure, data minimization, retention limits, role-based PII access; design with India's DPDP Act in mind.
- **Human escalation** always one tap/utterance away ("Talk to a human").
- **Conservative-by-default routing** (uncertain → GP/urgent care; vulnerable groups → lower urgency thresholds).
- **Auditability:** versioned taxonomies/rules and logged decisions for clinical review and iteration.

---

## 5. MVP Build Sequence (suggested)

```
 Sprint 0–1  Foundations: auth (MSG91), data model, WhatsApp (Gupshup), admin verify
 Sprint 2–3  Symptom Navigator v1 (single LLM + red-flag prefilter) + disclaimers
 Sprint 4–5  Doctor Discovery (SQL filters + verified profiles) + handoff
 Sprint 6–7  Booking + Temporal lifecycle (confirm/remind/reschedule)
 Sprint 8    Clinic Dashboard lite (appts, availability, comms)
 Sprint 9    Voice phase-a: missed-call → WhatsApp/callback + AI call summary
 ── PILOT (1 metro + 1 Tier-2, 3 specialties, ~10–20 clinics) ──► measure:
     • triage routing accuracy   • booking conversion
     • no-show reduction         • missed-call recovery   • clinic willingness-to-pay
```

> **North-star validation:** Do patients trust the navigation enough to book, and do clinics pay because DoctorFind measurably recovers missed calls and reduces no-shows? Everything in this MVP is sequenced to answer that as cheaply and quickly as possible.
