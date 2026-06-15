# Phase 11 — Execution Roadmap (DoctorFind)

> Milestone-based execution across workstreams: Frontend · Backend · AI · DevOps · Voice · Integrations · QA · Analytics.
> Stack anchor: FastAPI · Postgres+Redis+pgvector · LangGraph+Temporal · Gemini Flash · Deepgram/Whisper · ElevenLabs/Azure · Exotel/LiveKit/Twilio · Gupshup. Deploy single VM/PaaS early → cloud k8s later.

Guiding principle: **ship the AI receptionist (clinic-paying value) before anything consumer-facing.** Every milestone ties to a GTM/business outcome in docs 09–10.

---

## 11.1 Operating model & sequencing

- **0–30 days:** Prove the AI receptionist works on ONE real clinic line (WhatsApp + 1 voice flow). Manual where needed.
- **31–90 days:** Productize onboarding, multi-clinic, voice robustness, billing. Support first 40 clinics.
- **3–6 months:** Scale to ~150 clinics, self-serve, analytics, reliability hardening. Begin consumer discovery pilot.
- **6–12 months:** Consumer marketplace + commission, multi-city, enterprise pilots, k8s migration, EMR integrations.

---

## 11.2 30-Day Roadmap — "One real clinic, live"

**Goal:** A live pediatric clinic whose WhatsApp + one phone line is handled by DoctorFind AI, booking real appointments. Success = first real patient booked via AI, clinic owner says "keep it on."

| Workstream | Milestone | Success metric |
|---|---|---|
| **Backend** | Core domain models (clinic, doctor, slot, appointment, patient), FastAPI booking API, Postgres schema | Booking create/cancel/reschedule via API |
| **AI** | LangGraph triage+discovery+booking graph on Gemini Flash; RAG over clinic catalog (pgvector); guardrails (no diagnosis, escalation) | 80%+ correct specialty routing on test set; zero diagnosis leakage in red-team |
| **Integrations** | Gupshup WhatsApp inbound/outbound, utility templates (confirm/remind) | End-to-end WhatsApp booking works |
| **Voice** | One inbound voice flow: Exotel → STT (Deepgram) → LangGraph → TTS (Azure) → booking; barge-in basic | 3-min booking call completes successfully |
| **Frontend** | Minimal clinic dashboard (today's appointments, AI transcript log) | Owner can see bookings |
| **DevOps** | Single VM deploy, managed Postgres+Redis, Sentry, basic CI (GitHub Actions: lint+test+deploy) | One-command deploy; error alerts |
| **QA** | Red-team triage (diagnosis/escalation/abuse), happy-path booking suite | Critical-flow tests green |
| **Analytics** | Event logging (conversation, booking, handoff) to Postgres; founder dashboard | Can answer "how many AI-handled bookings today" |

**Team:** Solo/founding eng + founder on sales. Manual-ops acceptable (founder configures catalogs by hand).

---

## 11.3 90-Day Roadmap — "Repeatable, ~40 clinics"

**Goal:** Productized onboarding, robust voice, billing, multi-clinic isolation. Support 40 paying clinics with <8% churn.

| Workstream | Milestone | Success metric |
|---|---|---|
| **Backend** | Multi-tenant isolation, no-show recovery + waitlist auto-fill, reminders engine, billing/metering (voice-min, conv counts) | Per-clinic usage metered accurately for invoicing |
| **AI** | Multilingual triage (EN/HI/KN), prompt-caching for cost, Temporal for long-running/retry workflows, escalation-to-human handoff | Cost/conv <₹0.20 cached; lang auto-detect >90% |
| **Voice** | Outbound recall calls, multi-line, voice quality tuning, fallback IVR on failure | <2% call-drop; p95 response latency <1.2s |
| **Integrations** | Number porting/forwarding playbook, Google Calendar sync, payment (Razorpay) for prepaid bookings | Prepaid booking + payout works |
| **Frontend** | Clinic dashboard v2 (ROI panel: missed calls recovered, no-shows recovered), settings/self-config | Owner sees monthly ROI report |
| **DevOps** | Staging env, automated DB migrations, backups+restore drill, uptime monitoring, secrets mgmt | Restore drill passes; 99.5% uptime |
| **QA** | Regression suite, load test (concurrent calls), conversation-quality eval harness | Handles 50 concurrent voice calls |
| **Analytics** | Cohort retention, per-clinic health score, churn-risk flags, funnel (demo→trial→paid) | Churn-risk alerts firing |

**Team to hire:** 1 backend eng, 1 AI/ML eng, 1 BD rep, 1 part-time CSM. Founder still leads sales + product.

---

## 11.4 6-Month Roadmap — "Scale + consumer pilot, ~150 clinics"

**Goal:** Self-serve onboarding, hardened reliability, first consumer discovery pilot in dense localities.

| Workstream | Milestone | Success metric |
|---|---|---|
| **Backend** | Self-serve onboarding API, catalog auto-import (scrape/parse), commission/booking attribution engine | Self-serve clinic live in <30 min unattended |
| **AI** | Consumer discovery agent (cross-clinic), symptom→specialty quality model, A/B eval pipeline, self-host Whisper at volume | Discovery booking conversion measured; STT cost down 30% |
| **Voice** | Custom/branded voices (ElevenLabs) for premium tier, accent robustness, sentiment-based escalation | Premium voice tier live |
| **Integrations** | First EMR/PMS connectors (popular Indian clinic software), e-pharmacy/diagnostics referral pilot | 1 EMR integration in production |
| **Frontend** | Consumer WhatsApp + lightweight web/PWA discovery, review collection flow, patient health profile | First consumer self-serve booking |
| **DevOps** | Light k8s (or stay managed PaaS if stable), autoscaling for voice spikes, IaC (Terraform), DR plan | Autoscale handles 3x call spike |
| **QA** | Multilingual eval at scale, security review (DPDP compliance), pen-test | DPDP gap assessment closed; pen-test passed |
| **Analytics** | Marketplace liquidity metrics, LTV/CAC dashboard, attribution reporting, data warehouse | Per-cohort LTV:CAC visible to leadership |

**Team to hire:** +1 full-stack, +1 voice/infra eng, +2 BD, +1 dedicated CSM, +1 part-time compliance/legal advisor.

---

## 11.5 1-Year Roadmap — "Marketplace + multi-city + enterprise"

**Goal:** Functioning two-sided marketplace in city #1, second city launched, first enterprise/hospital deals, k8s production.

| Workstream | Milestone | Success metric |
|---|---|---|
| **Backend** | Commission GMV at scale, premium listings, multi-city tenancy, enterprise multi-location | Commission revenue stream live; 2 cities |
| **AI** | Continuous eval + fine-tuned routing, voice agent quality on par with human front-desk, proactive health nudges | AI-handled call CSAT ≥ human baseline |
| **Voice** | Twilio/LiveKit redundancy, global-grade reliability, concurrent scale (1000s) | 99.9% voice availability |
| **Integrations** | HIS/EMR for hospitals, lab/pharmacy network, insurance/cashless pilots | First enterprise integration in prod |
| **Frontend** | Full consumer app (iOS/Android), clinic mobile app, white-label for enterprise | App store live; enterprise white-label deployed |
| **DevOps** | Production k8s, multi-region readiness, SOC2/ISO prep, observability maturity | k8s prod stable; compliance roadmap started |
| **QA** | Automated E2E across channels, chaos testing, continuous red-team | <0.1% critical incident rate |
| **Analytics** | Predictive churn, dynamic pricing experiments, marketplace health, board metrics | Self-serve board pack generated |

**Team:** Eng team of ~10–12, CTO/eng lead, GTM lead + 4–6 BD, CS team, compliance, data. Founder transitions from doing to leading.

---

## 11.6 Hiring recommendations by stage

| Stage | Critical hires | Why |
|---|---|---|
| **0–30d (solo/founding)** | 1 senior full-stack/AI eng (or founder codes) | Speed of iteration on the one product that matters |
| **31–90d** | Backend eng, AI eng, BD rep, part-time CSM | Productize + start the sales engine |
| **3–6mo** | Full-stack, voice/infra eng, 2 BD, CSM, compliance advisor (PT) | Scale supply + reliability + DPDP |
| **6–12mo** | Eng lead/CTO, GTM lead, more BD/CS, data eng, mobile dev | Build organization, marketplace, enterprise |

**Hire BD before scaling eng** once the demo closes — supply density is the constraint, not features, in months 1–6.

---

## 11.7 Solo-founder strategy

- **Own:** product direction, first 20 clinic sales (you learn the objections), the AI prompt/triage quality, vendor negotiation.
- **Do manually, don't build yet:** catalog setup, onboarding, support — do it by hand for the first 20 clinics; automate only the steps that actually repeat.
- **Sequence ruthlessly:** WhatsApp text booking before voice; one specialty before many; one locality before a city.
- **Use managed everything early:** managed Postgres/Redis, BSP, telephony, TTS — buy time, don't run infra.
- **Founder-as-CSM** initially — direct line to churn signals.

---

## 11.8 What to outsource vs build

| Build (core/defensible) | Outsource/buy (commodity) |
|---|---|
| Triage + discovery + booking AI graph (LangGraph) | STT (Deepgram), TTS (Azure/ElevenLabs) |
| Catalog + matching + attribution engine | Telephony carrier (Exotel/Twilio/LiveKit) |
| Clinic dashboard + ROI analytics | WhatsApp BSP (Gupshup) |
| Multi-tenant data model & metering | Payments (Razorpay) |
| Conversation-quality eval harness | Auth, email, basic observability (managed) |
| | Initial marketing creatives, legal/DPDP review, accounting |

Outsource cautiously: **don't outsource the AI conversation logic or voice orchestration** — that's the product. Agencies will give you a brittle demo, not a reliable receptionist.

---

## 11.9 Technical-debt warnings

1. **Multi-tenancy must be designed in early** — retrofitting tenant isolation after 40 clinics is painful and a data-leak risk. Bake `clinic_id` scoping + row-level security from day one.
2. **Voice latency is unforgiving** — don't let the LangGraph/Temporal path balloon round-trip latency; keep voice on a low-latency path, push heavy/long work async. p95 <1.2s or callers hang up.
3. **Metering/billing accuracy** — log every billable unit (voice-min, conversation) immutably from the start; reconstructing usage for invoices retroactively is a nightmare.
4. **Prompt sprawl** — version prompts, keep an eval harness; "vibes-based" prompt edits regress triage safety silently. Diagnosis-leakage is a regulatory and trust hazard.
5. **Don't k8s too early** — single VM/managed PaaS until reliability demands otherwise; premature k8s burns months.
6. **Call recording / PII** — encrypt at rest, define retention, get consent. DPDP Act 2023 + health data sensitivity = build privacy in, not on.
7. **Catalog data quality** — garbage doctor/timing/fee data poisons discovery and bookings; invest in import validation early.
8. **Temporal/LangGraph coupling** — keep workflow orchestration (Temporal) and reasoning (LangGraph) cleanly separated so either can be swapped.

---

## 11.10 Cross-cutting success metrics

| Metric | 30d | 90d | 6mo | 1yr |
|---|---|---|---|---|
| Paying clinics | 4 | 40 | 150 | 500+ |
| AI-handled bookings/mo | ~50 | ~2,000 | ~12,000 | ~60,000 |
| Voice p95 latency | <1.5s | <1.2s | <1.0s | <0.9s |
| Cost / conversation (cached) | <₹0.25 | <₹0.20 | <₹0.15 | <₹0.13 |
| Monthly clinic churn | n/a | <8% | <5% | <4% |
| Uptime | best-effort | 99.5% | 99.9% | 99.9% |
| Cities | 1 | 1 | 1 (dense) | 2–3 |
| Diagnosis-leakage incidents | 0 | 0 | 0 | 0 |

> The non-negotiable across every milestone: **zero diagnosis leakage, accurate metering, and voice latency low enough that humans don't hang up.** Everything else is iteration.
