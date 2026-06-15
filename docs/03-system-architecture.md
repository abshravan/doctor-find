# DoctorFind — Phase 3: System Architecture

> **Codename:** DoctorFind · **Document:** Phase 3 — System Architecture · **Status:** Implementation-ready · **Audience:** Engineering, Platform, Infra, AI
>
> **Product in one line:** An AI-first healthcare *navigator* for India — conversational + voice + WhatsApp-first discovery, smart triage, doctor discovery, appointment booking, and workflow automation. Multilingual, mobile-first.
>
> ⚠️ **Safety boundary (non-negotiable, repeated throughout):** DoctorFind provides **informational guidance and discovery only. It does NOT diagnose, prescribe, or replace a clinician.** Every AI surface (chat, voice, WhatsApp) must render a safety disclaimer and an emergency-escalation path. Triage classifies *urgency and likely specialty* — it never asserts a disease. This is an architectural constraint, not just copy: the triage subsystem (§4) hard-codes red-flag routing to emergency messaging.

---

## 0. How to read this document

This is the architecture reference for the MVP build and the 18-month scale path. It is deliberately opinionated: where there is a choice, this document **makes the call, states the alternative, and explains the tradeoff** — because an architecture doc that only lists options is a liability, not a decision.

Section map:

1. Guiding principles & the "simplest thing that works" rule
2. High-level system architecture (+ ASCII diagram)
3. Frontend architecture
4. AI orchestration architecture (LangGraph + Temporal + the triage safety machine)
5. Backend architecture & service boundaries (the modular-monolith decision)
6. API gateway, authentication (phone OTP + JWT), and RBAC
7. Database design, vector DB usage, and caching
8. Event-driven workflows, queues, and async processing
9. Request-flow & event-flow diagrams
10. The BEST stack — comparison tables and the *why* for every layer
11. Scaling strategy & the microservices extraction path
12. Technical risks, tradeoffs, and the register
13. API sketches (FastAPI)

---

## 1. Guiding principles

1. **Boring infra, interesting AI.** Spend novelty budget on the agent/voice layer. Everything else (DB, queue, auth) should be the most boring, well-understood option that works.
2. **Start with the simplest alternative; earn complexity.** Every section below leads with "the simple version" before the scaled version. Don't build Kafka on day one. Don't build microservices on day one. Don't build a custom vector store when `pgvector` is in the database you already run.
3. **One database until it hurts.** PostgreSQL is the system of record. We reach for additional stores (Redis, object storage) only for jobs Postgres is genuinely bad at.
4. **Safety is a code path, not a disclaimer.** Triage red-flags, disclaimers, and emergency routing are enforced in the orchestration graph and validated in tests.
5. **India-first constraints are first-class:** flaky mobile networks, low-RAM Android, voice/IVR over PSTN via Exotel, WhatsApp as a primary surface, multilingual (Hindi, English, + major regional languages), data residency expectations, and cost sensitivity (Gemini Flash primary precisely because per-interaction cost matters at India scale).
6. **Stateless services, stateful stores.** App tier scales horizontally; all state lives in Postgres/Redis/object storage/Temporal.

---

## 2. High-level system architecture

### 2.1 The shape of the system

DoctorFind is a **modular monolith** FastAPI backend (one deployable, internally partitioned into modules with hard boundaries), fronted by an API gateway, talking to PostgreSQL (+ pgvector) and Redis, orchestrating AI via **LangGraph** (reasoning) and **Temporal** (durable business workflows), and reaching users across web (Next.js), mobile (React Native/Expo), voice (Exotel/LiveKit), and WhatsApp (Gupshup/Meta).

```
                                   ┌──────────────────────────────────────────────────┐
                                   │                   USER SURFACES                    │
                                   │                                                    │
   ┌────────────┐  ┌────────────┐  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐ │
   │  Next.js   │  │ React      │  │  WhatsApp    │  │  Voice (IVR) │  │  Web/App     │ │
   │  Web (PWA) │  │ Native/Expo│  │  (Gupshup/   │  │  Exotel      │  │  Voice       │ │
   │            │  │  Mobile    │  │   Meta WABA) │  │  (PSTN/India)│  │  LiveKit     │ │
   └─────┬──────┘  └─────┬──────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
         │               │                │                 │                 │         │
         └───────────────┴────────┬───────┴─────────────────┴─────────────────┘         │
                                   │  HTTPS / WSS / Webhooks                             │
                                   └────────────────────┬───────────────────────────────┘
                                                        │
                                          ┌─────────────▼─────────────┐
                                          │      API GATEWAY / EDGE     │
                                          │  TLS term · WAF · rate-limit│
                                          │  routing · authn check      │
                                          │  (Cloud LB → Nginx/Kong)    │
                                          └─────────────┬───────────────┘
                                                        │
                    ┌───────────────────────────────────┼───────────────────────────────────┐
                    │                       FastAPI MODULAR MONOLITH (stateless pods)         │
                    │                                                                          │
                    │  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
                    │  │ Identity│ │Discovery│ │ Booking  │ │ Triage / │ │  Channels        │ │
                    │  │ & Auth  │ │ /Search │ │ Schedule │ │ AI Orch  │ │ (WA/Voice/Web)   │ │
                    │  └─────────┘ └─────────┘ └──────────┘ └────┬─────┘ └──────────────────┘ │
                    │  ┌─────────┐ ┌─────────┐ ┌──────────┐      │       ┌──────────────────┐ │
                    │  │ Provider│ │Notif.   │ │ Payments │      │       │  Admin / RBAC    │ │
                    │  │ Mgmt    │ │ /Comms  │ │ (later)  │      │       │                  │ │
                    │  └─────────┘ └─────────┘ └──────────┘      │       └──────────────────┘ │
                    └───────────────┬───────────────────────────┼───────────────┬────────────┘
                                    │                            │               │
              ┌─────────────────────┼─────────────┐             │               │
              │                     │             │             │               │
        ┌─────▼─────┐      ┌────────▼───────┐ ┌───▼────┐  ┌─────▼──────┐  ┌─────▼────────────┐
        │PostgreSQL │      │     Redis      │ │ Object │  │  LangGraph │  │   Temporal       │
        │ + pgvector│      │ cache · session│ │ Storage│  │ agent runtime│ │ durable workflow │
        │ (primary) │      │ · streams/queue│ │(S3-like)│ │ (in-process │  │  worker cluster  │
        │ + replicas│      │ · rate-limit   │ │ media  │  │  or sidecar)│  │                  │
        └───────────┘      └────────────────┘ └────────┘  └──────┬──────┘  └─────────┬────────┘
                                                                  │                   │
                                                  ┌───────────────▼───────────────────▼────────┐
                                                  │           EXTERNAL AI / COMMS PLANE         │
                                                  │                                             │
                                                  │  LLM:  Gemini Flash (primary)               │
                                                  │        → OpenAI / Claude (fallback)         │
                                                  │  STT:  Deepgram (primary) / Whisper         │
                                                  │  TTS:  ElevenLabs / Azure (Indic voices)    │
                                                  │  OTP:  MSG91   ·  WhatsApp: Gupshup/Meta     │
                                                  │  Telephony: Exotel (India) · LiveKit (web)  │
                                                  └─────────────────────────────────────────────┘
```

### 2.2 Layer responsibilities

| Layer | Responsibility | Key tech |
|---|---|---|
| **Surfaces** | Capture user intent across web, app, WhatsApp, voice | Next.js, RN/Expo, Gupshup/Meta, Exotel, LiveKit |
| **Edge / Gateway** | TLS, WAF, rate-limiting, request routing, coarse authn | Cloud LB + Nginx (MVP) → Kong/APISIX (scale) |
| **App tier** | Business logic, AI orchestration entrypoints, channel adapters | FastAPI modular monolith |
| **Orchestration** | Agent reasoning + durable multi-step workflows | LangGraph + Temporal |
| **Data plane** | System of record, cache, vectors, media | Postgres + pgvector, Redis, object storage |
| **External plane** | LLM, STT/TTS, OTP, WhatsApp, telephony | Gemini/OpenAI/Claude, Deepgram/Whisper, ElevenLabs/Azure, MSG91, Exotel/LiveKit |

---

## 3. Frontend architecture

### 3.1 Decision

- **Web:** **Next.js (App Router)** as a PWA — public discovery pages need SEO + fast first paint; logged-in flows are app-like.
- **Mobile:** **React Native + Expo** — one TypeScript codebase for iOS + Android, OTA updates via EAS Update (critical in India where store-update adoption lags), and code/skill sharing with the web team.
- **Shared:** a `packages/shared` workspace (TypeScript) for API client, types (generated from the FastAPI OpenAPI spec), validation schemas (Zod), i18n strings, and the design system tokens.

### 3.2 Why this split (not Flutter, not RN-for-web-too)

- Next.js gives **SSR/ISR for SEO** on `/doctors/...`, `/clinics/...`, `/specialties/...` — organic discovery is a primary acquisition channel in India; a pure SPA would bleed that traffic.
- Expo gives the fastest path to both stores plus **OTA hotfixes** without re-review — essential when a triage-prompt bug must ship in hours.
- One language (TypeScript) end-to-end on the client lowers hiring friction and lets the same engineers move between surfaces.

### 3.3 Frontend internals

```
apps/
  web/        Next.js (App Router, RSC for content pages, client components for chat)
  mobile/     Expo (expo-router mirrors web routes where sensible)
packages/
  api-client/ typed fetch/ws client generated from OpenAPI
  ui/         design system (web: React + Tailwind/shadcn; native: own primitives, shared tokens)
  i18n/       locale bundles (en, hi, + regional); ICU message format
  domain/     shared zod schemas + enums (matches backend contracts)
```

Key patterns:

- **Multilingual-first:** every string is keyed; language is a user/session attribute resolved at the edge and passed to the backend so AI responses match UI language.
- **Voice-first UI:** push-to-talk component backed by **LiveKit** (web/app real-time audio) — streams to backend → Deepgram STT → orchestration → TTS back. Phone-only users go through **Exotel** IVR (no app needed).
- **WhatsApp parity:** WhatsApp is not a second-class channel — the same orchestration backend powers it. The frontend apps and WhatsApp differ only in the *renderer* (rich UI vs. WA message templates / interactive lists / buttons).
- **Offline-tolerant:** PWA + RN cache last results; booking confirmations queued and retried (poor-network resilience).

### 3.4 Frontend ↔ backend transport

| Interaction | Transport |
|---|---|
| Discovery, booking, CRUD | REST/JSON over HTTPS |
| Conversational chat (text) | Server-Sent Events (SSE) for token streaming; falls back to chunked HTTP on hostile proxies |
| Voice (web/app) | LiveKit WebRTC media + a control WebSocket |
| Voice (phone) | Exotel webhooks ↔ backend (no client app) |
| WhatsApp | Gupshup/Meta webhooks ↔ backend |

**Why SSE over WebSockets for chat:** SSE is one-directional (server→client) which is exactly the token-streaming shape, survives more Indian mobile proxies/CDNs than WS, and is trivially load-balanced. User input is a normal POST. Reserve WebSockets/LiveKit for true bidirectional audio.

---

## 4. AI orchestration architecture

This is the heart of DoctorFind and the layer that justifies the codename "navigator."

### 4.1 The two-engine model: LangGraph + Temporal

There are two *different* orchestration problems, and conflating them is the most common architectural mistake:

| Problem | Nature | Engine |
|---|---|---|
| **Agent reasoning** — interpret an utterance, decide which tool to call (search doctors, check slots, run triage), loop until the user's goal is met | Short-lived (seconds), in-memory, model-driven, needs streaming | **LangGraph** |
| **Durable business workflow** — "book → take payment → confirm → send WhatsApp reminder 24h before → handle reschedule/cancel → no-show follow-up" | Long-lived (hours→days), must survive process restarts, needs retries/timers/compensation | **Temporal** |

**Rule:** LangGraph decides *what the user wants right now*; Temporal guarantees *the multi-step thing actually completes*. The LangGraph agent, when it concludes "the user wants to book slot X," **starts a Temporal workflow** and returns — it does not itself babysit reminders 24 hours later.

### 4.2 LangGraph agent graph

```
                    ┌──────────────────────────────────────────────────────┐
                    │                LangGraph: "Navigator" agent            │
                    │                                                        │
   user turn  ──►   │   ┌──────────┐     ┌───────────────┐                   │
   (text/voice)     │   │ Language │     │   Intent /    │                   │
                    │   │ detect + │ ──► │   Router      │                   │
                    │   │ normalize│     │  (Gemini Flash)│                  │
                    │   └──────────┘     └──────┬────────┘                   │
                    │                            │                           │
                    │      ┌─────────────────────┼─────────────────────┐     │
                    │      ▼                     ▼                     ▼     │
                    │  ┌────────┐         ┌────────────┐        ┌──────────┐ │
                    │  │ TRIAGE │         │ DISCOVERY  │        │ BOOKING  │ │
                    │  │ node   │         │ node       │        │ node     │ │
                    │  │(safety │         │(vector +   │        │(slot     │ │
                    │  │ machine)│        │ filters)   │        │ lookup)  │ │
                    │  └───┬────┘         └─────┬──────┘        └────┬─────┘ │
                    │      │                    │                    │       │
                    │   ┌──▼───────────┐        │                    │       │
                    │   │ RED-FLAG?    │        │                    │       │
                    │   │ → emergency  │        │                    │       │
                    │   │   routing +  │        │                    │       │
                    │   │   disclaimer │        │                    │       │
                    │   └──────────────┘        │                    │       │
                    │      └────────────────────┼────────────────────┘       │
                    │                            ▼                            │
                    │                   ┌─────────────────┐                   │
                    │                   │  Response       │                   │
                    │                   │  composer +     │  ──► start        │
                    │                   │  SAFETY guard   │      Temporal wf  │
                    │                   │  (disclaimer)   │      if booking   │
                    │                   └────────┬────────┘                   │
                    │                            │ stream tokens              │
                    └────────────────────────────┼───────────────────────────┘
                                                 ▼  to channel renderer
```

**Tools exposed to the agent** (each is a typed function backed by a monolith module):
- `search_doctors(query, location, specialty, language, filters)` → vector + structured search
- `get_availability(provider_id, date_range)` → Scheduling module
- `triage_assess(symptoms, context)` → triage classifier (urgency + suggested specialty, **never a diagnosis**)
- `create_booking_intent(...)` → returns a draft; the *commit* is a Temporal workflow
- `get_provider_profile(provider_id)`
- `escalate_emergency()` → returns emergency numbers / nearest emergency facility messaging

**Why LangGraph over CrewAI / n8n for reasoning:** LangGraph gives an explicit, inspectable **state graph** with conditional edges, checkpointing, and deterministic control flow. For a healthcare-adjacent product, *being able to assert "a red-flag symptom always routes to the emergency node"* in a graph + test is a safety requirement. CrewAI's role-playing autonomous agents are emergent and hard to constrain — unacceptable on a safety-critical path (see §10.5). n8n is great ops glue but is not an LLM reasoning runtime.

### 4.3 The triage safety state machine

The triage node is the one place where AI behavior is **constrained, not trusted**:

```
symptoms ─► [LLM extracts structured features] ─► [DETERMINISTIC red-flag ruleset]
                                                          │
                                       ┌──────────────────┴──────────────────┐
                                       │ red flag present?                    │
                                       ▼ YES                                  ▼ NO
                              ┌──────────────────┐               ┌──────────────────────┐
                              │ EMERGENCY ROUTE  │               │ urgency band (low/    │
                              │ - stop triage    │               │ medium/high) +        │
                              │ - show 108/112   │               │ suggested specialty   │
                              │ - nearest ER msg │               │ + disclaimer          │
                              │ - log + alert    │               │ → handoff to Discovery│
                              └──────────────────┘               └──────────────────────┘
```

- Red-flag detection is a **hand-written deterministic ruleset over LLM-extracted features**, not "ask the model if it's an emergency." The model extracts (`chest_pain: true`, `duration_minutes: 20`, `radiating: true`); code decides.
- Output is always **urgency + specialty + disclaimer**, never a condition name.
- Every triage interaction is logged immutably for audit.

### 4.4 LLM provider strategy (primary + fallback)

**Primary: Gemini Flash.** Cheapest per-token at India scale, fast, strong multilingual (including Indic languages), good enough for routing/extraction/composition. This is the cost-driving default.

**Fallbacks (resilience + quality tiers):** route through a thin **`LLMRouter`** abstraction so the provider is a config decision, not a code rewrite.

| Tier | Provider / model | Role |
|---|---|---|
| Primary | **Gemini Flash** | Default for routing, extraction, response composition — cheap, fast, multilingual |
| Fallback A (availability) | **OpenAI** (cost-tier model) | Used on Gemini outage / rate-limit; comparable cost/quality |
| Fallback B (hard reasoning + reliability) | **Claude** — `claude-opus-4-8` (most capable), with `claude-sonnet-4-6` for balanced and `claude-haiku-4-5` for cheap classification | Complex triage reasoning, safety-sensitive composition, and a high-reliability fallback |

**Claude (Anthropic) model IDs & pricing — accurate as of this writing (cross-checked against the Claude API skill):**

| Model | Model ID | Context | Input $/1M | Output $/1M | Use in DoctorFind |
|---|---|---|---:|---:|---|
| Claude Opus 4.8 | `claude-opus-4-8` | 1M | $5.00 | $25.00 | Hardest triage reasoning / safety composition fallback |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | 1M | $3.00 | $15.00 | Balanced fallback for general conversation |
| Claude Haiku 4.5 | `claude-haiku-4-5` | 200K | $1.00 | $5.00 | Cheap, fast classification / routing fallback |

> Use the **exact** model ID strings above — do not append date suffixes. Pricing is per million tokens.

**Implementation notes for the Claude path (these are real API constraints, not stylistic):**
- Use **adaptive thinking** for triage-grade reasoning: `thinking={"type": "adaptive"}` plus `output_config={"effort": "high"}`. The old `budget_tokens` parameter is **removed** on Opus 4.8 / Sonnet 4.6 and will 400 — do not use it.
- **No assistant prefills** on these models (returns 400). Force structured triage output with `output_config.format` (JSON schema) instead.
- **Stream** any response with large `max_tokens` (use `.stream()` / `get_final_message()`), and handle `stop_reason == "refusal"` before reading `response.content` — a safety refusal returns HTTP 200 with empty/partial content.
- Always parse tool-call `input` with `json.loads()` — never string-match the serialized JSON.

**Provider-router contract (pseudocode):**

```python
class LLMRouter:
    async def complete(self, *, task: LLMTask, messages, schema=None, stream=False):
        # task carries: criticality (routine|safety), language, cost_ceiling
        provider_chain = self._chain_for(task)   # e.g. [gemini_flash, openai, claude]
        for provider in provider_chain:
            try:
                return await provider.invoke(messages, schema=schema, stream=stream)
            except (RateLimit, ProviderOutage, RefusalNeedsFallback):
                continue
        raise AllProvidersFailed()
```

For safety-critical tasks the chain is reordered to prefer the most reliable model and tighter validation; for high-volume routing it prefers Gemini Flash for cost.

### 4.5 Voice pipeline

```
Phone user ─► Exotel (PSTN, India) ─┐
Web/app    ─► LiveKit (WebRTC)     ─┴─► audio frames ─► Deepgram STT (primary) / Whisper
                                                              │ transcript (streaming)
                                                              ▼
                                              LangGraph Navigator agent (§4.2)
                                                              │ response text
                                                              ▼
                                        ElevenLabs / Azure TTS (Indic voices) ─► audio ─► user
```

- **Deepgram primary** for streaming STT (low latency, good for IVR); **Whisper** as batch/fallback (cost or self-host option).
- **ElevenLabs / Azure TTS** for natural Indic-language voices; Azure is the cost/coverage fallback.
- Barge-in supported on LiveKit; Exotel IVR uses DTMF + speech.

---

## 5. Backend architecture & service boundaries

### 5.1 The decision: **Modular Monolith for MVP**

**Recommendation: Build a modular monolith. Do NOT start with microservices.**

#### Justification

1. **The domain isn't understood yet.** Premature service boundaries become wrong boundaries you can't move. A monolith lets boundaries *emerge* from real coupling, then you extract along the seams that actually exist.
2. **Team size.** An MVP team (≈5–15 engineers) cannot absorb the operational tax of N services: per-service deploys, distributed tracing, network failure modes, schema-version skew, and an order-of-magnitude more infra.
3. **Transactional integrity is free.** Booking touches identity, scheduling, payments, and notifications. In a monolith these are one Postgres transaction. Across services you'd need sagas on day one — accidental complexity for an MVP.
4. **Latency & cost.** No inter-service network hops; one connection pool; one deploy artifact. Cheaper to run, which matters at India price points.
5. **You still get modularity.** Enforced module boundaries (below) give 80% of the "microservices discipline" benefit with 10% of the cost.

#### What "modular" means here (enforced, not aspirational)

```
app/
  modules/
    identity/        # auth, OTP, users, sessions, RBAC
      api.py         # FastAPI routers (the ONLY public surface)
      service.py     # business logic
      repository.py  # all DB access for this module's tables
      models.py      # SQLAlchemy models (owns its tables)
      schemas.py     # pydantic DTOs
      events.py      # events this module emits/consumes
    discovery/       # search, vector, provider profiles (read side)
    provider/        # provider/clinic onboarding, profile write side
    scheduling/      # slots, availability, calendars
    booking/         # booking intents + Temporal workflow triggers
    triage/          # triage safety machine
    aiorch/          # LangGraph runtime + LLMRouter + tool registry
    channels/        # whatsapp / voice / web adapters
    notifications/   # WhatsApp/SMS/push fan-out
    payments/        # (post-MVP) escrow/settlement
    admin/           # platform admin + RBAC management
  core/              # config, db, redis, gateway middleware, observability
  workflows/         # Temporal workflow + activity definitions
```

**Boundary rules (enforced by import-linting in CI):**
- A module may call another module **only through its `service.py` public functions or via events** — never reach into another module's `repository.py` or `models.py`.
- Each module **owns its tables**; cross-module reads go through the owning module's service (or a read-model/event), never a raw cross-table JOIN that ignores ownership.
- Modules communicate asynchronously via the in-process event bus (Redis Streams backing) where eventual consistency is acceptable (e.g., "booking confirmed" → notifications).

This is the discipline that makes the **extraction path** (§11) cheap: a module whose only inbound coupling is `service.py` + events can be lifted into its own service by replacing in-process calls with RPC and the in-process bus with the network bus — without rewriting the module's internals.

### 5.2 Service boundaries (logical, even inside the monolith)

| Module | Owns | Talks to (via service/events) |
|---|---|---|
| Identity & Auth | users, otp, sessions, roles, permissions | everyone (authn/authz) |
| Discovery | search index, provider read-models, vectors | provider (events), aiorch (tool) |
| Provider Mgmt | provider/clinic/staff records | discovery (emits update events) |
| Scheduling | slots, availability, calendars | booking, discovery |
| Booking | booking intents, status | scheduling, payments, notifications (events), triggers Temporal |
| Triage | triage sessions, audit log | aiorch (tool), notifications (emergency alerts) |
| AI Orchestration | agent runs, tool registry, LLMRouter | all domain modules (as tools) |
| Channels | channel sessions, message mapping | aiorch, notifications |
| Notifications | outbound message log | WhatsApp/SMS/push providers |
| Admin | admin actions, audit | identity (RBAC) |

---

## 6. API gateway, authentication & RBAC

### 6.1 API gateway design

**MVP:** Cloud load balancer → **Nginx** (or the cloud's managed gateway) doing TLS termination, basic WAF, IP/region rate-limiting, and routing to FastAPI pods. The FastAPI app itself does the *fine-grained* concerns (authn token validation, RBAC, per-user rate-limits via Redis).

**Scale:** introduce **Kong or APISIX** when you need: per-route rate-limit policies, API keys for B2B/clinic integrations, plugin-based auth, canary routing, and centralized observability. Defer until there's a second consumer class (partners) — for a single first-party app, a managed LB + Nginx is sufficient and far simpler.

**Gateway responsibilities (layered):**

| Concern | MVP location | Scale location |
|---|---|---|
| TLS termination | Cloud LB | Cloud LB |
| WAF / DDoS | Cloud LB + Cloudflare | same |
| Coarse rate-limit (IP) | Nginx | Kong/APISIX |
| Per-user / per-endpoint rate-limit | FastAPI + Redis | gateway plugin or FastAPI |
| AuthN (JWT verify) | FastAPI middleware | gateway plugin can pre-verify |
| AuthZ (RBAC) | FastAPI dependency | FastAPI (stays in app — it's domain logic) |
| Routing | Nginx | Kong/APISIX |

> **Principle:** the gateway does *transport & coarse* concerns; *domain* authorization (RBAC) stays in the app where it can see the resource. Don't push RBAC into the gateway — it can't know "is this doctor the owner of this appointment."

### 6.2 Authentication strategy — phone OTP + JWT + refresh

India is phone-first; email is secondary. Primary auth is **phone-number OTP via MSG91**.

**Flow:**

```
1. POST /auth/otp/request { phone }            → MSG91 sends OTP; server stores hash+expiry in Redis
2. POST /auth/otp/verify  { phone, code }      → verify; create/find user; issue tokens
   → returns: access_token (JWT, ~15 min)  +  refresh_token (opaque, ~30 days, stored server-side)
3. Authenticated requests: Authorization: Bearer <access_token>
4. POST /auth/refresh     { refresh_token }    → rotate refresh; issue new access_token
5. POST /auth/logout                           → revoke refresh token (delete from store)
```

**Token design:**

| Token | Type | Lifetime | Storage | Contents |
|---|---|---|---|---|
| Access token | **JWT (signed, RS256)** | 15 min | client memory / secure storage | `sub` (user_id), `roles`, `scopes`, `tenant` (clinic_id if staff), `jti`, `exp` |
| Refresh token | **opaque, random** | 30 days, **rotating** | server (Redis/Postgres) keyed by hash; client secure storage | n/a (lookup token) |

**Why this shape:**
- **JWT access token** = stateless verification at the app tier (no DB hit per request); short-lived to bound blast radius if leaked.
- **Opaque, server-stored, rotating refresh token** = revocability (logout, ban, device theft) that pure-JWT can't give. Rotation detects token theft (reuse of an old refresh token → revoke the whole chain).
- **OTP secrets in Redis** with TTL + attempt counter (rate-limited; lockout after N failures) to stop OTP brute-force and SMS-bombing (also throttle `otp/request` per phone + per IP).
- **WhatsApp/voice identity:** the channel (verified WhatsApp number, or Exotel caller ID) maps to the same user identity. WhatsApp's verified phone is a first-class authentication signal; a one-time OTP links a phone to an account on first contact.

**Security specifics:** RS256 (rotateable signing keys via JWKS), `jti` for optional access-token denylist on critical revocation, mandatory TLS, refresh-reuse detection, and per-phone OTP cost caps (SMS is real money + an abuse vector).

### 6.3 RBAC system

**Roles:** `patient`, `doctor`, `clinic_admin`, `receptionist`, `platform_admin`.

Model: **role + scoped permissions**, with **resource-scoping** for clinic staff (a `receptionist` can only act within their `clinic_id`). The JWT carries roles and the tenant scope; the app enforces both the permission *and* the scope.

#### Permission matrix

Legend: ✅ allowed · 🟡 allowed but scoped (own clinic / own records) · ❌ denied

| Permission | patient | doctor | clinic_admin | receptionist | platform_admin |
|---|:---:|:---:|:---:|:---:|:---:|
| Search/discover providers | ✅ | ✅ | ✅ | ✅ | ✅ |
| Use AI chat / triage | ✅ | ✅ | ✅ | ✅ | ✅ |
| Book appointment (as self) | ✅ | ✅ | — | — | ✅ |
| Book appointment (on behalf of patient) | ❌ | 🟡 own patients | 🟡 own clinic | 🟡 own clinic | ✅ |
| View own appointments | ✅ | ✅ | 🟡 own clinic | 🟡 own clinic | ✅ |
| Cancel/reschedule appointment | 🟡 own | 🟡 own patients | 🟡 own clinic | 🟡 own clinic | ✅ |
| View patient PII/medical context | ❌ others | 🟡 own patients | 🟡 own clinic | 🟡 own clinic (limited) | ✅ (audited) |
| Manage doctor profile | ❌ | 🟡 own | 🟡 own clinic's doctors | ❌ | ✅ |
| Manage clinic profile & settings | ❌ | ❌ | 🟡 own clinic | ❌ | ✅ |
| Manage doctor schedule/availability | ❌ | 🟡 own | 🟡 own clinic | 🟡 own clinic | ✅ |
| Manage clinic staff (add/remove) | ❌ | ❌ | 🟡 own clinic | ❌ | ✅ |
| View clinic analytics/reports | ❌ | 🟡 own | 🟡 own clinic | 🟡 limited | ✅ |
| Configure workflow automations | ❌ | 🟡 own | 🟡 own clinic | ❌ | ✅ |
| Manage platform users / roles | ❌ | ❌ | ❌ | ❌ | ✅ |
| Access audit logs | ❌ | ❌ | 🟡 own clinic | ❌ | ✅ |
| Manage LLM/triage prompts & safety config | ❌ | ❌ | ❌ | ❌ | ✅ |
| Suspend/ban accounts | ❌ | ❌ | 🟡 own clinic staff | ❌ | ✅ |

**Enforcement pattern (FastAPI dependency):**

```python
def require(permission: Permission, scope: Scope = Scope.NONE):
    async def dep(user: User = Depends(current_user), resource=Depends(load_resource)):
        if not rbac.allows(user, permission):
            raise HTTPException(403, "permission_denied")
        if scope is Scope.CLINIC and resource.clinic_id != user.clinic_id and not user.is_platform_admin:
            raise HTTPException(403, "out_of_scope")
        return user
    return dep

@router.post("/appointments/{id}/cancel")
async def cancel(id: UUID, user = Depends(require(Permission.CANCEL_APPT, Scope.CLINIC))):
    ...
```

> **Principle:** permission answers *"can this role do this verb?"*; scope answers *"on this specific resource?"*. Both are required for staff actions. Patient self-service is scoped to `own`.

---

## 7. Database design, vector DB & caching

### 7.1 PostgreSQL as the single system of record

**Recommendation: PostgreSQL primary, Redis for cache/ephemeral, pgvector for embeddings. One database until it genuinely hurts.**

Core entities (each owned by its module):

```
users(id, phone, email?, name, default_language, created_at, ...)
roles(user_id, role, clinic_id?)                      -- a user can hold a scoped role
otp_attempts  -> Redis (not Postgres): {phone -> hash, exp, tries}
refresh_tokens(id, user_id, token_hash, family_id, exp, revoked_at)

providers(id, type[doctor|clinic], name, ...)
doctors(id, provider_id, specialties[], languages[], reg_no, verified, ...)
clinics(id, provider_id, address, geo POINT, ...)
clinic_staff(clinic_id, user_id, role)                -- receptionist/clinic_admin scoping

availability(doctor_id, clinic_id, weekday, start, end, slot_minutes, ...)
slots(id, doctor_id, clinic_id, starts_at, status[open|held|booked])
bookings(id, slot_id, patient_id, booked_by, status, channel, workflow_id, ...)

triage_sessions(id, user_id, channel, urgency, suggested_specialty,
                red_flag, transcript_ref, created_at)         -- immutable audit
ai_runs(id, user_id, channel, graph_state_ref, provider_used, tokens, latency, ...)

provider_embeddings(provider_id, embedding vector(768), ...)   -- pgvector
channel_messages(id, channel, external_id, user_id, direction, payload_ref, ...)
notifications(id, user_id, channel, template, status, ...)
audit_log(id, actor_id, action, target, scope, at)             -- append-only
```

Design choices:
- **UUID PKs**, `created_at/updated_at`, soft-deletes on user-facing entities.
- **Geo** via PostGIS `geography(POINT)` for "doctors near me" radius search (Discovery combines geo + structured filters + vector relevance).
- **Slot holds** use a short-TTL `held` status (with the hold expiry enforced by a Temporal timer or a sweeper) to prevent double-booking during the booking conversation.
- **Read replicas** for Discovery's heavy read traffic; writes go to primary.
- **Partitioning** later: `channel_messages`, `ai_runs`, `audit_log` are append-heavy → time-partition when volume warrants (not at MVP).

**Why Postgres over MongoDB as primary:** the domain is **relational and transactional** — bookings, scoped roles, slot integrity, payments. ACID across these in one transaction is exactly Postgres's strength. Mongo would force application-level integrity for the most safety-relevant operation in the product (don't double-book, don't lose a payment). JSONB columns cover the genuinely schemaless bits (channel payloads, agent state snapshots) without giving up relational guarantees.

### 7.2 Vector DB usage (pgvector)

**Recommendation: pgvector inside the same Postgres. Do not add a separate vector database for MVP.**

Use cases:
1. **Semantic provider/specialty search** — embed doctor profiles, specialties, conditions-treated, and clinic descriptions; embed the user's natural-language need ("skin doctor who speaks Tamil near Adyar for acne"); retrieve by cosine similarity, then re-rank with structured filters (geo, language, availability, verified).
2. **Triage knowledge retrieval (RAG)** — retrieve vetted, curated informational content (symptom → likely specialty mappings, *not* diagnoses) to ground the triage node's suggestions. Source content is curated and reviewed; the model summarizes, it does not invent medical claims.
3. **FAQ / help retrieval** for the assistant.

Why pgvector:
- One datastore = one backup, one ops surface, transactional consistency between a provider row and its embedding (no dual-write skew).
- Embedding volume (tens of thousands of providers, not billions of vectors) is well within pgvector + HNSW/IVFFlat index performance.
- **Migrate to a dedicated vector store (e.g. a managed ANN service) only if** vector count or QPS outgrows pgvector — the `Discovery` module's repository is the single seam to swap.

**Hybrid search pattern:** `vector similarity (recall)` → `structured filter (geo/lang/specialty/verified)` → `business re-rank (availability, rating, distance)`. Pure vector search is recall; the ranking that matters to users is structured.

### 7.3 Caching strategy

**Redis, with intentional cache classes — not one giant bag:**

| Cache class | Example | TTL / eviction | Invalidation |
|---|---|---|---|
| **Hot read cache** | provider profiles, specialty lists | minutes | event-driven (provider-update event busts key) |
| **Search results** | popular query → result page | short (1–5 min) | TTL only (acceptable staleness) |
| **Session / auth** | OTP secrets, rate-limit counters, refresh-token lookups | TTL = token/OTP lifetime | explicit on logout/revoke |
| **Agent context** | per-conversation LangGraph short-term state | conversation lifetime | explicit on session end |
| **Rate-limit** | per-user/IP/endpoint counters | sliding window | automatic |
| **Idempotency** | booking/payment idempotency keys | minutes–hours | TTL |

Rules:
- **Cache-aside** as default (read-through complicates invalidation).
- **Never cache PII or medical context with permissive TTLs**; auth/PII caches are short and explicitly invalidated.
- **Event-driven busting** for anything with a clear owner (provider edits their profile → emit event → bust).
- Prompt/LLM-response caching: the Gemini/Claude calls themselves can use provider-side prompt caching for stable system prompts to cut cost (e.g., the large multilingual triage system prompt is a stable cacheable prefix).

---

## 8. Event-driven workflows & async processing

### 8.1 Two distinct async mechanisms

| Mechanism | For | Tech (MVP → scale) |
|---|---|---|
| **Event bus** (fire-and-forget, pub/sub) | decoupling modules: "booking.confirmed" → notifications, analytics | **Redis Streams** → **Kafka** |
| **Durable workflows** (stateful, multi-step, retried, timed) | the booking lifecycle, reminders, payment settlement, no-show follow-up | **Temporal** |
| **Background jobs** (simple deferred work) | send one SMS, generate one embedding, resize one image | **Celery / RQ on Redis** → Kafka-consumer workers |

**Don't confuse them:** events announce that something happened; workflows guarantee a process completes; jobs do one deferred task. Reminders are a Temporal *timer*, not a cron + DB scan.

### 8.2 The booking workflow (Temporal)

```
Temporal Workflow: BookingLifecycle(booking_id)
  1. activity: hold_slot(slot_id)                       (retry; compensation: release_slot)
  2. activity: collect_payment(...)        [post-MVP]   (retry; compensation: refund)
  3. activity: confirm_booking()
  4. signal-or-timer: until appt_time - 24h
        activity: send_whatsapp_reminder()
  5. signal-or-timer: until appt_time - 2h
        activity: send_final_reminder()
  6. await appt_time + grace
        activity: mark_status (attended | no_show)
  7. if no_show: activity: send_followup() / offer_rebook()
  ── handles SIGNALS at any point: reschedule, cancel (→ run compensations) ──
```

Why Temporal for this (not cron, not Celery-beat, not n8n):
- **Durability:** the workflow survives deploys/restarts; a 24-hour timer doesn't depend on a process staying alive.
- **Retries + compensation (saga):** payment failed after slot held → automatic compensating release. This is the correct tool for "money + slots + messages must stay consistent."
- **Visibility & determinism:** every step is recorded; you can query "where is booking X?" Temporal's deterministic replay makes long-running logic debuggable.
- **vs n8n:** n8n is for **ops glue and internal automations** (e.g., "new clinic signed up → notify sales → create CRM entry"), not for prod-critical, money-touching, must-not-lose workflows. Keep n8n out of the booking/payment path (see §10.5).

### 8.3 Queue recommendation: Redis Streams → Kafka

**Start: Redis Streams (you already run Redis).** Consumer groups give at-least-once delivery, replay, and per-consumer offsets — enough for module decoupling and background fan-out at MVP volume. Celery/RQ ride on the same Redis for simple jobs.

**Move to Kafka when:** event volume, multi-consumer fan-out, long retention/replay, or stream-processing/analytics needs exceed Redis Streams (typically: many high-throughput event types, a data/analytics team consuming the same streams, or retention beyond what Redis memory comfortably holds). The event-bus abstraction (`events.py` publish/subscribe contract) is the seam; swapping the transport doesn't touch module logic.

> **Sequence:** Redis Streams + Celery (MVP) → Kafka (when fan-out/retention/throughput demands it). Don't pay Kafka's operational cost before you have the load to justify it.

### 8.4 Async processing patterns

- **Webhooks (WhatsApp/Exotel/payment) are ingested fast and processed async:** the webhook endpoint validates signature, enqueues, returns 200 immediately. Processing (which may call the LLM) happens off the request path. This prevents provider retries/timeouts and absorbs spikes.
- **Idempotency everywhere on the boundary:** WhatsApp and payment providers redeliver — every webhook handler dedupes on the provider's event ID.
- **Outbox pattern** for "DB write + must-emit event" atomicity: write the event to an outbox table in the same transaction, a relay publishes it. Prevents the classic dual-write loss between Postgres and the bus.

---

## 9. Request-flow & event-flow diagrams

### 9.1 Conversational booking request flow (WhatsApp example)

```
Patient ─"book a dermatologist near me tomorrow"─► WhatsApp (Gupshup/Meta)
   │
   ▼  webhook (signed)
[Gateway] ─► [Channels module]  ── validate sig, dedupe, map to user identity (OTP-linked)
   │                                  enqueue + 200 OK to provider
   ▼ (async)
[AI Orchestration] LangGraph Navigator
   ├─ language detect → intent: BOOKING + DISCOVERY
   ├─ tool: search_doctors(...)  ─► [Discovery] ─► pgvector + geo + filters (Postgres + replica)
   ├─ presents options (WA interactive list) ◄─ stream/compose (Gemini Flash)
   ├─ patient picks slot
   ├─ tool: get_availability(...) ─► [Scheduling]
   └─ tool: create_booking_intent(...) ─► [Booking]
                                            └─► START Temporal BookingLifecycle workflow
   ▼
[Booking] returns confirmation draft ─► [Channels] renders WA confirmation
   │
   └─ emits event "booking.created" ─► [Notifications], analytics
Temporal workflow now owns reminders/payment/no-show (runs for hours/days)
```

### 9.2 Triage request flow (safety path)

```
User ─"severe chest pain for 20 min, spreading to arm"─► (any channel)
   ▼
[AI Orch] → TRIAGE node
   ├─ LLM extracts features {chest_pain:true, duration:20, radiating:true}
   ├─ DETERMINISTIC red-flag ruleset → RED FLAG = true
   ▼
EMERGENCY ROUTE (no further triage)
   ├─ respond with emergency numbers (108/112) + nearest ER messaging + disclaimer
   ├─ write immutable triage_sessions row (red_flag=true)
   └─ emit "triage.emergency" event ─► [Notifications]/ops alert
(NO booking, NO diagnosis — hard stop)
```

### 9.3 Event flow (decoupling)

```
                          ┌──────────────── Redis Streams (→ Kafka later) ────────────────┐
[Booking] ──booking.confirmed──►│                                                          │
[Provider] ─provider.updated───►│   topic: domain-events                                   │
[Triage] ──triage.emergency───►│                                                          │
                          └───┬───────────────┬───────────────┬────────────────┬──────────┘
                              ▼               ▼               ▼                ▼
                       [Notifications]   [Discovery cache  [Analytics/      [Ops alerting]
                       (WA/SMS/push)      invalidation]     warehouse]
```

### 9.4 AI orchestration internal flow

```
turn ─► LangGraph state ─► [router node: Gemini Flash]
                               │ (on outage/ratelimit/refusal) LLMRouter falls back
                               ▼            ──► OpenAI ──► Claude (claude-opus-4-8, adaptive thinking)
                       conditional edges
                ┌──────────────┼──────────────┐
            [triage]       [discovery]      [booking]
                │              │ tools           │ tools
          safety machine   Discovery svc    Scheduling/Booking svc
                └──────────────┼──────────────┘
                               ▼
                     [composer + SAFETY guard: inject disclaimer] ─► stream to channel
```

---

## 10. The BEST stack — comparisons & the *why*

Each table marks **▶ recommended**. The recommendation column is the decision; the rest is the justification.

### 10.1 Backend framework

| Option | Strengths | Weaknesses | Verdict |
|---|---|---|---|
| **▶ FastAPI (Python)** | Async-native, best-in-class for **AI/LLM ecosystem** (LangGraph, SDKs, ML libs all Python), auto OpenAPI, pydantic validation, fast to build | Python CPU-bound throughput < Go; needs discipline for large codebases | **MVP winner** — the AI ecosystem is Python; collocating orchestration with the API removes a whole network boundary |
| Django | Batteries-included, admin, ORM, mature | Sync-first (async retrofitted), heavier, less natural for streaming/LLM-async | Good for CRUD-heavy, weaker for our streaming/AI core |
| Node.js (Express/Fastify) | Same language as frontend, great async I/O | AI ecosystem weaker than Python; would split the team's AI logic from the API | Viable but loses Python's AI gravity |
| NestJS | Structured, DI, TS end-to-end | Same AI-ecosystem gap as Node; more ceremony | Structured Node, same core gap |
| Go | Best raw throughput/latency, low memory, great concurrency | Weakest LLM/agent ecosystem; slower feature velocity for AI glue | **Reserve for hot paths later** |

**Decision:** **FastAPI for the MVP and the system core; Go for specific hot paths later** (e.g., a high-QPS availability/search read service, or a latency-critical voice-media bridge) — extracted as the monolith splits (§11). The cost of Go is feature velocity on the AI layer, which is exactly where we move fastest; the win of Go is throughput, which only a few endpoints actually need.

### 10.2 Frontend

| Option | Strengths | Weaknesses | Verdict |
|---|---|---|---|
| **▶ Next.js (web)** | SSR/ISR for SEO, fast first paint, React ecosystem, PWA | SSR ops overhead | **Web winner** — discovery SEO is an acquisition channel |
| **▶ React Native + Expo (mobile)** | One TS codebase iOS+Android, **OTA updates** (EAS), shares code/types with web | Native-module edge cases | **Mobile winner** — OTA + shared TS is decisive for India |
| Flutter | Excellent perf, single codebase, great UI control | Dart (separate language/skills from web), no code sharing with Next.js web | Strong tech, but splits the stack and team |

**Decision:** **Next.js (web) + React Native/Expo (mobile)**, unified TypeScript, shared `packages/`. Flutter loses on *code/type sharing with the web* and *introducing a second language* — at MVP, stack cohesion beats Flutter's raw rendering edge.

### 10.3 Database

| Option | Role | Verdict |
|---|---|---|
| **▶ PostgreSQL** | system of record (relational, ACID, geo via PostGIS, JSONB for schemaless bits) | **Primary** — bookings/payments/roles demand transactions |
| **▶ Redis** | cache, sessions, rate-limit, ephemeral OTP, Streams (queue) | **Companion** — the right tool for hot/ephemeral/queue |
| **▶ pgvector** | embeddings inside Postgres | **Vector** — no separate store needed at MVP |
| MongoDB | document store | Not primary — would push integrity into app code for the riskiest operations; JSONB covers our document needs |

**Decision:** **Postgres (primary) + Redis (cache/ephemeral/queue) + pgvector (embeddings).** One transactional source of truth; Redis for what Postgres is bad at; vectors collocated. Add a dedicated ANN store / Kafka / warehouse only when scale forces it.

### 10.4 AI components — role of each

| Component | Choice | Role | Why |
|---|---|---|---|
| **LLM (primary)** | **Gemini Flash** | routing, extraction, multilingual composition | cheapest at India scale, fast, strong Indic-language coverage |
| **LLM (fallback A)** | **OpenAI** (cost tier) | availability fallback | provider diversity; comparable cost |
| **LLM (fallback B)** | **Claude** (`claude-opus-4-8` / `claude-sonnet-4-6` / `claude-haiku-4-5`) | hard triage reasoning, safety-sensitive composition, high-reliability fallback | top reasoning + strong safety behavior; adaptive thinking for triage |
| **Local models** | optional, later | PII redaction / cheap classification on-device or self-hosted | cost control + data-residency for sensitive preprocessing; **not** for primary reasoning at MVP (ops burden) |
| **STT (primary)** | **Deepgram** | streaming speech-to-text for voice/IVR | low-latency streaming, good accuracy |
| **STT (fallback)** | **Whisper** | batch / self-host fallback | cost control + offline option |
| **TTS** | **ElevenLabs / Azure** | natural Indic-language voice output | ElevenLabs quality; Azure for coverage/cost fallback |
| **Telephony (India)** | **Exotel** | PSTN/IVR for phone-only users | India-native, regulatory fit, virtual numbers |
| **Real-time (web/app)** | **LiveKit** | in-app/web voice (WebRTC) | low-latency media, barge-in, SFU |
| **WhatsApp** | **Gupshup / Meta WABA** | primary messaging surface | India WhatsApp ubiquity; template + interactive messages |
| **OTP** | **MSG91** | phone OTP delivery | India SMS deliverability |

**On local vs hosted LLMs:** hosted (Gemini/OpenAI/Claude) for all reasoning at MVP — the operational cost of self-hosting GPU inference is not worth it early. Reserve local/self-hosted models for *narrow, high-volume, privacy-sensitive preprocessing* (e.g., PII redaction before sending to a third party, or a cheap language/intent classifier) where cost-at-scale and data residency justify the burden.

### 10.5 Workflow orchestration — the four-way split

This is the most-misunderstood layer; the recommendation uses **three tools for three jobs and explicitly rejects one for the prod-critical path.**

| Tool | Best at | Use in DoctorFind | Verdict |
|---|---|---|---|
| **▶ LangGraph** | LLM agent reasoning as an explicit, inspectable state graph (conditional edges, checkpointing) | the Navigator agent: routing, triage safety machine, tool-calling | **Agent reasoning** — constrainable & testable, which a safety path requires |
| **▶ Temporal** | durable, long-running, retried, timed business workflows with compensation (sagas) | booking lifecycle, reminders, payment settlement, no-show follow-up | **Durable workflows** — money + slots + timers must not be lost |
| **▶ n8n** | low-code ops glue / internal automations / 3rd-party connectors | ops: CRM sync, lead routing, internal alerts, simple integrations | **Ops glue only** — keep it off the patient/booking/payment path |
| **✗ CrewAI** | autonomous multi-agent role-play | — | **Avoid for prod-critical paths** |

**Why avoid CrewAI on critical paths:** CrewAI's value is emergent, autonomous multi-agent collaboration. For a healthcare-adjacent product, **emergent and autonomous are exactly the wrong properties on the triage/booking path** — we need *deterministic, auditable, constrainable* control flow where "a red-flag symptom always routes to emergency" is a graph invariant you can test, not an emergent behavior you hope for. CrewAI is harder to constrain, harder to test deterministically, and harder to make accountable for safety. (It can be fine for *internal, non-critical* experiments — content drafting, analysis — but never on a path that touches a patient's safety or a user's money.)

**The mental model:**
- **LangGraph** = *think* (what does the user want now?)
- **Temporal** = *guarantee* (the multi-step thing completes, durably)
- **n8n** = *glue* (internal ops automations)
- **CrewAI** = *not here* (on critical paths)

---

## 11. Scaling strategy & microservices extraction path

### 11.1 Scale the monolith first

1. **Stateless app pods → horizontal autoscale** behind the LB. All state in Postgres/Redis/Temporal/object storage, so adding pods is free.
2. **Read replicas** for Discovery's read-heavy traffic; route reads to replicas, writes to primary.
3. **Connection pooling** (PgBouncer) — Postgres connection limits are the first wall a scaling Python app hits.
4. **Cache aggressively** (the §7.3 classes) to shield Postgres.
5. **Async off the request path** — webhooks, LLM calls (where UX allows), notifications.
6. **Separate worker fleets** by workload: web pods, Temporal workers, Celery/Streams consumers, voice-media bridges — scale independently even while sharing one codebase.
7. **Provider-side LLM prompt caching** + Gemini-Flash-default to keep AI cost flat as volume grows.

### 11.2 When (and how) to extract microservices

Extract a module into its own service **only when it has a distinct scaling profile, a distinct failure-isolation need, or a distinct team** — never on schedule.

**Likely extraction order (along the seams that already exist):**

| Order | Extract | Trigger | Likely rewrite to Go? |
|---|---|---|---|
| 1 | **Discovery/Search** | read QPS dwarfs the rest; needs independent scaling & maybe a dedicated ANN store | **Yes** (hot path) |
| 2 | **Voice-media bridge** | latency-critical, CPU/IO profile unlike CRUD; spiky | **Yes** (hot path) |
| 3 | **Notifications/Channels** | high fan-out, provider-rate-limit isolation, bursty | maybe |
| 4 | **AI Orchestration** | independent deploy cadence for prompts/graphs; isolate provider outages | stays Python |
| 5 | **Payments** | compliance isolation, independent audit boundary | stays (correctness > throughput) |

**Why this is cheap given the modular monolith:** each module's only inbound coupling is its `service.py` public functions and events. Extraction = (a) put the module behind an RPC interface, (b) replace in-process event publish/subscribe with the network bus, (c) give it its own schema/migrations. Module internals don't change. The `events.py` bus contract and `service.py` boundaries we enforced from day one *are* the extraction interface.

```
Monolith (MVP)                          After extraction (scale)
┌───────────────────────┐               ┌──────────┐   ┌────────────┐
│ identity discovery     │               │ Monolith │──►│ Discovery  │ (Go, own ANN)
│ booking  scheduling    │   ─────►      │ (core)   │──►│ Voice      │ (Go)
│ triage   aiorch ...    │               │          │──►│ Notif/Chan │
│  (in-process bus)      │               └────┬─────┘   └────────────┘
└───────────────────────┘                  network bus (Kafka)
```

### 11.3 Data scaling

- Time-partition append-heavy tables (`ai_runs`, `channel_messages`, `audit_log`).
- Move analytics off the OLTP DB to a warehouse (consume the event stream) before analytical queries hurt OLTP.
- Promote pgvector → dedicated ANN store only when vector QPS/count demands it.
- Redis Streams → Kafka when fan-out/retention/throughput demands it (§8.3).

---

## 12. Technical risks, tradeoffs & register

| # | Risk | Impact | Mitigation | Tradeoff accepted |
|---|---|---|---|---|
| R1 | **AI gives unsafe medical advice** | Patient harm, legal | Deterministic red-flag machine; disclaimers as code; RAG over *curated* content only; triage outputs urgency+specialty, never diagnosis; audit log | Less "smart"/free-form triage in exchange for safety |
| R2 | **LLM provider outage / rate-limit / refusal** | Core UX down | `LLMRouter` fallback chain Gemini→OpenAI→Claude; Claude server-side `fallbacks` param; circuit breakers | Multi-provider prompt-tuning & cost variance |
| R3 | **Cost blowup at India scale** | Unit economics break | Gemini Flash default; prompt caching; cheap-model routing (Haiku for classification); cache results | Slightly more routing complexity |
| R4 | **Double-booking / slot races** | Trust loss | Slot `held` TTL; DB constraints; Temporal saga with compensation | Hold complexity; slight friction during booking |
| R5 | **Premature microservices** | Velocity collapse, ops tax | **Modular monolith**; extract only on real triggers (§11.2) | Must enforce module discipline (import-lint) |
| R6 | **OTP/SMS abuse (cost + bombing)** | Money + reputation | Per-phone/IP rate-limits, attempt lockout, OTP cost caps | Slight friction for legit retry |
| R7 | **Voice/IVR latency over PSTN** | Poor voice UX | Deepgram streaming STT, barge-in, Exotel India POPs; later Go media bridge | Engineering effort on the media path |
| R8 | **Webhook redelivery / dual-write loss** | Lost bookings/messages | Idempotency on all webhooks; outbox pattern; at-least-once + dedupe | Idempotency bookkeeping |
| R9 | **Multilingual quality variance** | Wrong/awkward responses across Indic languages | Gemini Flash (strong Indic) + per-language eval sets; human-reviewed templates for transactional messages | Eval/QA investment per language |
| R10 | **CrewAI/n8n creeping onto critical paths** | Non-deterministic, unauditable safety/money flows | Architectural ban (§10.5); critical paths only on LangGraph+Temporal | Some convenience automations stay in n8n only for ops |
| R11 | **Data residency / privacy (health data, India)** | Compliance | Postgres in-region; PII minimization; short PII cache TTLs; redaction before 3rd-party LLM where feasible; audited PII access | Possible perf cost of redaction/region pinning |
| R12 | **JWT can't be revoked instantly** | Stolen access token valid till exp | Short (15 min) access tokens; revocable rotating refresh tokens; `jti` denylist for critical revocation | Slightly more auth machinery |

---

## 13. API sketches (FastAPI)

Illustrative — shapes and patterns, not final contracts. Note the safety disclaimer is part of the response contract on AI endpoints.

### 13.1 OTP request + verify

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, constr

router = APIRouter(prefix="/auth", tags=["auth"])

class OtpRequest(BaseModel):
    phone: constr(pattern=r"^\+?[0-9]{10,15}$")

@router.post("/otp/request", status_code=202)
async def request_otp(body: OtpRequest, rl=Depends(rate_limit("otp_request", per_phone=5, per_ip=20)),
                      otp=Depends(get_otp_service)):
    # rate-limited per phone AND per IP to stop SMS-bombing
    await otp.issue(body.phone)          # generates code, stores hash+TTL in Redis, sends via MSG91
    return {"status": "otp_sent"}        # never reveal whether the phone exists

class OtpVerify(BaseModel):
    phone: str
    code: constr(min_length=4, max_length=8)

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900

@router.post("/otp/verify", response_model=TokenPair)
async def verify_otp(body: OtpVerify, otp=Depends(get_otp_service), auth=Depends(get_auth_service)):
    if not await otp.verify(body.phone, body.code):    # checks hash, TTL, attempt counter
        raise HTTPException(401, "invalid_or_expired_otp")
    user = await auth.get_or_create_user(phone=body.phone)
    return await auth.issue_token_pair(user)           # short JWT + rotating opaque refresh
```

### 13.2 Conversational endpoint (streams, enforces disclaimer)

```python
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/ai", tags=["assistant"])

class ChatTurn(BaseModel):
    session_id: str | None = None
    message: str
    language: str | None = None        # resolved at edge if absent
    channel: str = "web"

@router.post("/chat")
async def chat(turn: ChatTurn,
               user=Depends(require(Permission.USE_AI)),
               nav=Depends(get_navigator)):          # LangGraph runtime + LLMRouter
    async def stream():
        async for chunk in nav.run(user=user, turn=turn):
            # composer node guarantees a safety disclaimer is attached to medical/triage content
            yield chunk
    return StreamingResponse(stream(), media_type="text/event-stream")
    # Booking intents discovered mid-conversation start a Temporal workflow inside nav.run(...)
```

### 13.3 Discovery (hybrid vector + structured) and booking intent

```python
@router.get("/providers/search")
async def search_providers(q: str, lat: float | None = None, lng: float | None = None,
                           specialty: str | None = None, language: str | None = None,
                           svc=Depends(get_discovery_service)):
    # 1) vector recall over embeddings (pgvector)  2) structured filter (geo/lang/specialty/verified)
    # 3) business re-rank (availability/distance/rating)
    return await svc.hybrid_search(q, lat=lat, lng=lng, specialty=specialty, language=language)

class BookingIntent(BaseModel):
    slot_id: str
    patient_id: str | None = None          # staff may book on behalf (scoped)

@router.post("/bookings/intents", status_code=201)
async def create_booking_intent(body: BookingIntent,
                                user=Depends(require(Permission.BOOK_APPT, Scope.CLINIC)),
                                booking=Depends(get_booking_service)):
    draft = await booking.create_intent(body, actor=user)   # places a short TTL hold on the slot
    workflow_id = await booking.start_lifecycle(draft)      # → Temporal BookingLifecycle
    return {"booking_id": draft.id, "workflow_id": workflow_id, "status": "pending_confirmation"}
```

---

## Appendix A — Stack decision summary (one-glance)

| Layer | Decision | Reach for next when… |
|---|---|---|
| Backend | **FastAPI modular monolith** | extract Go hot paths when QPS/latency demands |
| Web | **Next.js (PWA, SSR/ISR)** | — |
| Mobile | **React Native + Expo (OTA)** | — |
| Primary DB | **PostgreSQL (+PostGIS)** | shard/partition; warehouse for analytics |
| Vector | **pgvector (in Postgres)** | dedicated ANN store at high vector QPS |
| Cache/ephemeral/queue | **Redis (+ Streams) + Celery** | **Kafka** at high fan-out/retention/throughput |
| Agent reasoning | **LangGraph** | — |
| Durable workflows | **Temporal** | — |
| Ops automation | **n8n** (off critical paths) | — |
| LLM | **Gemini Flash** → OpenAI → **Claude** | per-task routing tuning |
| STT / TTS | **Deepgram/Whisper · ElevenLabs/Azure** | — |
| Telephony / RTC / WA / OTP | **Exotel · LiveKit · Gupshup-Meta · MSG91** | — |
| Auth | **Phone OTP + JWT access + rotating refresh** | — |
| Gateway | **LB + Nginx** | **Kong/APISIX** when partners/B2B arrive |

## Appendix B — The repeating safety invariant

Every AI surface MUST: (1) display a disclaimer that DoctorFind is informational and not a diagnosis; (2) route deterministic red-flags to emergency messaging before any other processing; (3) never name a disease — only urgency + suggested specialty; (4) immutably log triage interactions for audit. These are enforced in the LangGraph composer/triage nodes and verified by tests — they are architecture, not copy.
```

