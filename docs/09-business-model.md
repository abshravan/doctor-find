# Phase 9 — Business Model (DoctorFind)

> AI-first healthcare discovery & booking for India. Conversational + voice + WhatsApp triage (NOT diagnosis), doctor discovery, booking, and clinic workflow automation.
> Canonical stack: FastAPI · Postgres + Redis + pgvector · LangGraph + Temporal · Gemini Flash · Deepgram/Whisper STT · ElevenLabs/Azure TTS · Exotel/LiveKit/Twilio · Gupshup WhatsApp.

All figures in INR unless noted. FX assumption for USD-priced vendors: **₹86/USD**. Numbers are planning estimates — validate against live invoices monthly.

---

## 9.1 Strategic framing

The Indian outpatient market is **supply-fragmented** (12+ lakh registered allopathic doctors, ~70% in solo or 1–3 doctor clinics with no software) and **demand-chaotic** (patients discover via word-of-mouth, Google Maps, JustDial, and Practo). The incumbent (Practo) monetizes primarily via subscriptions + paid leads and is widely resented by clinics for lead-quality and pricing. Our wedge is **doing the work, not selling listings**: an AI receptionist that answers calls/WhatsApp, triages, and books — clinics pay because we *reduce labour and recover missed calls*, not because we promise vague "visibility".

Core monetization thesis: **B2B2C with the clinic as the paying anchor.** Consumer free, clinic pays for automation, marketplace commission layers on top once liquidity exists.

---

## 9.2 Monetization models compared

| Model | How it works | Pros | Cons | Timing | Realistic India price |
|---|---|---|---|---|---|
| **Commission per booking** | % or flat fee per completed/attended appointment routed through us | Aligned with value; scales with GMV; consumer-friendly (free) | Hard at cold-start (no liquidity); leakage (patients pay clinic directly, attribution disputes); doctors resist "tax on my own patient" | Phase 2 (after liquidity, month 6+) | ₹15–40 flat / new-patient booking; avoid % of consult fee (disputes) |
| **SaaS for clinics (AI receptionist core)** | Monthly subscription: AI answers calls + WhatsApp, books, reminders, EMR-lite | Predictable MRR; sticky (becomes front-desk infra); defensible | Requires real product reliability; sales-led; churn if ROI not visible | **Phase 1 — primary wedge (month 0)** | ₹1,999–7,999/clinic/mo by tier |
| **Premium listings / featured placement** | Pay for top placement in discovery, "verified" badge | High margin; familiar to clinics (Practo trained them) | Erodes consumer trust if results become pay-to-win; weak until demand-side traffic is real | Phase 3 (month 9+, once consumer DAU exists) | ₹2,000–10,000/mo add-on |
| **Patient subscriptions** | Consumer plan: priority booking, family health record, unlimited AI triage, teleconsult discounts | Recurring B2C revenue; data depth | Indian consumers rarely pay for "health convenience"; high CAC; low willingness-to-pay | Phase 3+ (opportunistic) | ₹99–299/mo or ₹999/yr family |
| **AI receptionist usage plans (metered)** | Per-minute (voice) / per-conversation overage on top of SaaS base | Captures heavy users; pure-usage option for hospitals | Billing complexity; needs airtight metering | Phase 2 | ₹4–8 / handled voice-minute; ₹3–6 / WhatsApp conversation |
| **Enterprise / hospital partnerships** | Multi-location deployment, integration with HIS/EMR, SLA, white-label | Large contract value; reference logos; defensible integration moat | Long sales cycle (3–9 mo); customization burden; procurement/compliance | Phase 3 (month 9–18) | ₹50,000–5,00,000/mo per enterprise |
| **Pharmacy / diagnostics referral** | Commission on lab tests & e-pharmacy orders triggered post-consult | High-intent, high-margin adjacency | Regulatory sensitivity; trust risk; needs partner network | Phase 4 | 8–15% referral on diagnostics |

**Sequencing logic:** Land with SaaS AI-receptionist (clear ROI, no liquidity needed) → add metered usage → layer commission + premium listings once consumer traffic is real → enterprise + adjacencies for expansion.

---

## 9.3 Cost estimates

### 9.3.1 AI inference — per text/WhatsApp conversation

Assumptions per "conversation" (a complete triage + discovery + booking flow, multi-turn):
- ~8 LLM turns, RAG-grounded (doctor catalog via pgvector).
- Avg **2,500 input tokens/turn** (system prompt + retrieved context + history) and **350 output tokens/turn**.
- Gemini 2.x Flash indicative pricing: **$0.075 / 1M input**, **$0.30 / 1M output** (≈ ₹6.45 / 1M in, ₹25.8 / 1M out).

Per conversation:
- Input: 8 × 2,500 = 20,000 tokens → 0.02M × ₹6.45 = **₹0.129**
- Output: 8 × 350 = 2,800 tokens → 0.0028M × ₹25.8 = **₹0.072**
- Embeddings (query embeds, ~5 calls): negligible, ≈ ₹0.01
- **LLM cost ≈ ₹0.21 / text conversation** (round to **₹0.25** with retries/guardrail re-prompts).

Prompt-caching the static system prompt + catalog context cuts input by ~50% at scale → **~₹0.13–0.15/conversation**. Budget **₹0.25** un-cached for conservative planning.

### 9.3.2 Voice call — per minute, fully loaded

A live voice call burns STT (continuous) + LLM (per turn) + TTS (per spoken response) + telephony. Per **minute** of conversation (~1.5 turn exchanges/min, ~120 spoken words ≈ 800 TTS chars):

| Component | Vendor & rate | Per-minute cost (INR) |
|---|---|---|
| STT | Deepgram Nova streaming ~$0.0043/min (₹0.37) — or self-host Whisper at GPU amortization | **₹0.37** (Deepgram) |
| LLM | Gemini Flash, ~1.5 turns/min ≈ ₹0.04 | **₹0.04** |
| TTS | ElevenLabs Flash ~₹0.07–0.15 / 1k chars premium, or **Azure Neural ₹0.014 / 1k chars** → 800 chars | **₹0.01 (Azure)** / ₹0.10 (ElevenLabs) |
| Telephony | Exotel inbound/outbound ~₹0.50–0.80/min; LiveKit SIP + carrier ~₹0.40–0.70 | **₹0.65** |
| **Total (Azure TTS, Deepgram)** | | **≈ ₹1.07 / min** |
| **Total (ElevenLabs premium voice)** | | **≈ ₹1.16 / min** |

**Planning number: ₹1.20–1.50 / voice-minute** loaded (buffer for silence, retries, barge-in re-synthesis). A typical 3-minute booking call ≈ **₹3.60–4.50 cost**.

> Cost lever: ElevenLabs only for premium/branded clinics; Azure Neural (Indian voices: Swara, Madhur) as default. Self-hosted Whisper-large on a shared GPU breaks even vs Deepgram above ~40k min/mo.

### 9.3.3 Infrastructure — monthly

**MVP scale (≤1k MAU, <50 clinics, single VM/PaaS):**

| Item | Spec | ₹/mo |
|---|---|---|
| App VM (FastAPI + Temporal worker) | 4 vCPU / 16 GB (Hetzner/DO/AWS Lightsail) | 3,500 |
| Managed Postgres + pgvector | Small (2 vCPU/8GB, e.g. Neon/RDS/Supabase) | 2,500 |
| Redis (managed/small) | 1 GB | 1,200 |
| Object storage + CDN (recordings, assets) | <100 GB | 600 |
| Gupshup WhatsApp BSP | Platform fee + per-conversation (see below) | 2,000 |
| Monitoring/logging (Grafana Cloud/Sentry free→paid) | | 1,000 |
| Domain, email, misc SaaS | | 1,200 |
| **Subtotal infra (MVP)** | | **≈ ₹12,000/mo** |

**10k MAU scale (~200–400 clinics, pre-k8s or light k8s):**

| Item | ₹/mo |
|---|---|
| App tier (2–3 VMs / small k8s, autoscale) | 18,000 |
| Postgres (4 vCPU/16GB + read replica) | 12,000 |
| Redis (HA, 4 GB) | 6,000 |
| Object storage + CDN (call recordings grow fast) | 4,000 |
| Vector workload (pgvector on PG; OK at this scale) | (incl.) |
| Observability (APM, logs, traces) | 6,000 |
| WhatsApp BSP platform fee | 8,000 |
| Misc SaaS / backups / DR | 6,000 |
| **Subtotal infra (10k MAU)** | **≈ ₹60,000/mo** |

> Note: variable AI + voice + WhatsApp message costs are **on top** of the above and scale with usage (see unit economics).

### 9.3.4 WhatsApp messaging (Meta + Gupshup)

Meta charges per 24-hour **conversation** by category (India rates, indicative): Utility ~₹0.12–0.35, Authentication ~₹0.12, Marketing ~₹0.70–0.90; **Service (user-initiated) free** since Nov 2024 within the service window. Gupshup adds a small per-message/platform markup. Budget:
- Booking/reminder (Utility): **~₹0.30/conversation**
- Triage chats (Service, user-initiated): **~₹0/messaging** + LLM ₹0.25.
- Re-engagement (Marketing): **~₹0.85/conversation** — use sparingly.

---

## 9.4 Pricing model (clinic SaaS — the anchor)

| Tier | Target | Price (₹/mo) | Included | Overage |
|---|---|---|---|---|
| **Starter** | Solo doctor / 1-doctor clinic | **₹1,999** | WhatsApp AI receptionist, 500 conversations, booking + reminders, listing | ₹3/conv |
| **Pro** | 2–4 doctor clinic | **₹4,999** | Above + **AI voice receptionist 1,500 min**, calendar/EMR-lite, no-show recovery, analytics | ₹5/voice-min, ₹3/conv |
| **Clinic+** | Busy multi-doc clinic | **₹7,999** | Above + 4,000 voice min, multi-line, custom voice, priority support, premium listing | ₹4/voice-min |
| **Enterprise/Hospital** | Hospitals, chains | **₹50k–5L** (custom) | Multi-location, HIS/EMR integration, SLA, white-label, dedicated CSM | negotiated |

Annual prepay: 2 months free (≈17% discount) — improves cash flow and retention.

**Why these numbers work:** a clinic front-desk hire costs ₹15,000–25,000/mo and still misses ~30% of calls (lunch, after-hours, busy). Pro at ₹4,999 recovers missed bookings + cuts labour — ROI story is "one recovered ₹500 consult/day pays for it."

---

## 9.5 Unit economics

### Per text/WhatsApp booking
| Line | Value |
|---|---|
| Revenue (commission, Phase 2) | ₹25 |
| LLM/triage cost | ₹0.25 |
| WhatsApp (utility conf) | ₹0.30 |
| Allocated infra (variable) | ₹0.45 |
| Payment processing (if prepaid consult, ~2%) | ₹0–10 |
| **Contribution / booking** | **₹14–24** (≈ 75–90% margin on commission) |

### Per AI-receptionist voice minute
| Line | Value |
|---|---|
| Revenue (overage / metered) | ₹5.00 |
| Loaded delivery cost | ₹1.35 |
| **Contribution / voice-min** | **₹3.65 (≈ 73% margin)** |

Bundled minutes inside a plan: at ₹4,999 Pro with 1,500 included min, if a clinic uses 1,200 min the marginal delivery cost ≈ ₹1,620, leaving the SaaS fee ~67% contribution before fixed allocation.

### Per clinic / month (Pro tier, steady state)
| Line | ₹/mo |
|---|---|
| SaaS revenue | 4,999 |
| Variable AI+voice+WA delivery (avg active clinic) | ~1,800 |
| Support/CS allocation (per clinic) | ~400 |
| **Contribution / clinic / month** | **≈ ₹2,800 (56%)** |

### CAC, LTV, payback
- **CAC (feet-on-street, early):** ~₹3,000–5,000/clinic (BD salary + incentive + demo time). Self-serve later: ₹800–1,500.
- **LTV:** Pro contribution ₹2,800/mo × expected life. At **5% monthly churn → ~20 mo life → LTV ≈ ₹56,000**. Push churn to 3% → ~33 mo → LTV ≈ ₹92,000.
- **LTV:CAC ≈ 11–18×** (feet-on-street); payback **<2 months**. Healthy, even with generous CAC.

### Retention strategies
1. **Embed in the workflow** — once the AI owns the phone line/WhatsApp number, ripping it out means going back to missed calls. Port their number through us.
2. **Visible ROI dashboard** — monthly "We recovered N missed calls = ₹X potential revenue, handled Y after-hours bookings."
3. **No-show recovery + reactivation** — automated recall of lapsed patients = found revenue, raises switching cost.
4. **Annual contracts** with onboarding success milestone.
5. **Local CSM / WhatsApp support in regional language** — Indian SMB churn is heavily service-driven.

---

## 9.6 Sample P&L sketch — 50 clinics (early steady state)

Assumptions: 50 paying clinics; mix = 20 Starter (₹1,999), 25 Pro (₹4,999), 5 Clinic+ (₹7,999). Some metered overage. Consumer side still free/no commission yet.

**Monthly revenue**
| Source | Calc | ₹/mo |
|---|---|---|
| Starter | 20 × 1,999 | 39,980 |
| Pro | 25 × 4,999 | 1,24,975 |
| Clinic+ | 5 × 7,999 | 39,995 |
| Metered overage (voice/conv) | est. | 25,000 |
| **Total revenue** | | **≈ ₹2,29,950** |

**Monthly costs**
| Item | ₹/mo |
|---|---|
| Variable delivery (AI + voice + WhatsApp across all clinics) | ~70,000 |
| Infrastructure (between MVP and 10k scale) | ~35,000 |
| Vendor/platform fees (BSP, telephony minimums) | ~10,000 |
| Customer success / support (1 CSM partial) | ~45,000 |
| **Total COGS + direct opex** | **≈ ₹1,60,000** |
| **Gross/contribution margin** | **≈ ₹70,000 (≈ 30%)** |

**Below the line (team & overhead)** — typical lean team (2–3 eng, 1 founder GTM, 2 BD): ₹8–12L/mo salaries → **company is pre-profit at 50 clinics**; this stage is product-market-fit validation, not profitability.

**Path to contribution breakeven on direct costs:** ~30–40 active Pro-equivalent clinics. **Path to covering a lean team:** ~250–350 clinics at current ARPU (₹4,000 blended) → ~₹10–14L MRR. Improve via: raise Pro attach, add commission GMV layer, enterprise logos.

> Sensitivity: the single biggest swing is **voice usage per clinic**. Cap included minutes tightly and meter overage; a runaway high-call clinic on an unlimited plan can go contribution-negative.

---

## 9.7 Key risks to the model
- **Voice cost creep** (ElevenLabs/telephony) — mitigate with Azure default + Whisper self-host at scale.
- **Commission leakage** — patients pay clinic directly; attribution is the hard part. Solve with prepaid booking / deposit, or de-emphasize commission in favor of SaaS.
- **WhatsApp policy + Meta pricing changes** — keep voice + native app as parallel channels.
- **Regulatory** — strictly triage/navigation, never diagnosis; clear disclaimers; data localization (DPDP Act 2023). Compliance is a cost line that grows with enterprise.
