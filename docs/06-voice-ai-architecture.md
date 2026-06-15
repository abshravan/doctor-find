# Phase 6 — Voice AI Architecture (DoctorFind)

> Real-time, multilingual, conversational voice for an AI healthcare **navigator** (triage + discovery + booking; **never diagnosis**).
> Channels: **PSTN phone calls** (Exotel, India), **web/app realtime** (LiveKit WebRTC), **WhatsApp voice notes** (Gupshup/Meta + Twilio intl), **IVR fallback**.
> Orchestration: **LangGraph** (turn-level agent graph) + **Temporal** (durable call/outbound workflows). LLM: **Gemini 2.0 Flash** primary, **Claude / GPT** fallback.
> Hard rule: every voice session opens and closes with a **safety disclaimer**; emergencies → immediate escalation to 112 / human.

---

## 1. System Overview (media + control planes)

```
                          ┌─────────────────────────── CONTROL PLANE ───────────────────────────┐
                          │   Temporal Workflows (durable): outbound calls, reminders, retries   │
                          │   LangGraph Agent Graph (per-turn): triage → search → book → confirm │
                          └─────────────────────────────────────────────────────────────────────┘
                                                    ▲           │ tool calls (FastAPI)
                                                    │           ▼
  PSTN caller ──dial──►  ┌──────────┐  RTP/SIP   ┌──────────────────────────────────────────────┐
                         │  Exotel  │◄──────────►│            Media Gateway / Orchestrator         │
  Web/App   ──WebRTC──►  │ LiveKit  │◄──────────►│  (FastAPI + websockets, per-call session FSM)   │
                         │ Twilio*  │            │                                                 │
  WhatsApp  ──audio────► │ Gupshup  │            │   ┌────────┐   ┌─────────┐   ┌──────────────┐  │
                         └──────────┘            │   │  VAD/  │──►│   STT   │──►│ LLM (LangGraph│  │
                                                 │   │ barge-in│   │ stream  │   │  + RAG/tools)│  │
                                                 │   └────▲───┘   └─────────┘   └──────┬───────┘  │
                                                 │        │ interrupt                  │ tokens    │
                                                 │   ┌────┴───────────────────────────▼───────┐   │
                                                 │   │            TTS (streaming)              │   │
                                                 │   └─────────────────────┬───────────────────┘   │
                                                 └─────────────────────────┼─────────────────────┘
                                                          audio frames out  ▼
                                                       back to telephony → caller's ear

  * Twilio = international PSTN + WhatsApp; Exotel = India PSTN; LiveKit = web/app.
  Persistence: Postgres (ai_conversations / ai_messages / voice_transcripts), Redis (live FSM, partials), Object store (audio).
```

**Streaming, frame-by-frame.** Audio flows in ~20 ms PCM frames. STT emits **interim + final** transcripts; the LLM streams tokens; TTS streams audio chunks back. Nothing waits for "end of everything" — we pipeline aggressively to hit sub-second perceived latency.

---

## 2. STT Pipeline

```
Mic/PSTN audio (8k μ-law PSTN / 16-48k WebRTC)
   │
   ├─► Jitter buffer + resample to 16 kHz PCM
   │
   ├─► VAD (WebRTC VAD / Silero) ── detects speech start/end + endpointing
   │
   ├─► Stream to STT (Deepgram WS / Whisper) with:
   │        • interim_results = true   (drives barge-in + early intent)
   │        • endpointing = 300 ms     (utterance finalize)
   │        • language = auto/hi-en    (code-switch aware)
   │        • keywords/boost: doctor names, specialties, drug names, pincodes
   │
   ├─► Interim transcript ──► UI captions + early LLM speculative prefetch
   │
   └─► Final transcript ──► normalize (numbers, dates "kal" → tomorrow, Hinglish)
                          ──► ai_messages(role=user) + voice_transcripts(text_raw/clean,conf)
```

Key choices:
- **Endpointing 250–350 ms** balances responsiveness vs cutting people off; longer (600 ms) for elderly/rural callers (configurable per `clinic.voice_config`).
- **Domain boosting / keyword hints** dramatically reduce errors on Indian names, specialties ("orthopaedic"), and medicine names.
- **Confidence gating:** if `confidence < 0.55`, agent reflects back ("I heard 'Dr. Mehta', is that right?") instead of acting.
- **PII redaction** before storing analytics copy (`voice_transcripts.text_clean` clean, redacted variant for `ai_messages.content_redacted`).

---

## 3. TTS Pipeline

```
LLM token stream ──► sentence/clause chunker (split on punctuation + length)
   │
   ├─► first clause sent to TTS as soon as ready  (don't wait for full reply)
   │
   ├─► TTS streaming synth (ElevenLabs Flash / Azure Neural) → audio chunks
   │
   ├─► resample to telephony codec (8 kHz μ-law for PSTN; Opus for WebRTC)
   │
   ├─► playback buffer ──► telephony out
   │
   └─► barge-in monitor: if VAD detects caller speech → STOP playback, flush buffer
```

- **Chunked / incremental synthesis:** synthesize the first sentence while the LLM is still generating the rest → cuts perceived latency by 300–600 ms.
- **SSML / prosody:** insert pauses around disclaimers, slow rate for instructions, spell out phone numbers and OTPs digit-by-digit.
- **Voice cloning per clinic** (optional, with consent): clinic-branded receptionist voice via `clinic.voice_config.tts_voice`.
- **Caching:** static prompts (greeting, disclaimer, hold music prompts) pre-rendered and cached by `(text, voice, lang)` hash — zero TTS latency for boilerplate.

---

## 4. Interruption / Barge-in Handling

```
        ┌──────────────┐  caller starts speaking while bot talks
        │  BOT_SPEAKING │──────────────────────────────┐
        └──────┬────────┘                              ▼
               │ playback chunks            ┌────────────────────────┐
               │                            │ VAD: energy > thresh    │
               │                            │ for > 200 ms (debounce) │
               │                            └───────────┬────────────┘
               │                                        │ barge-in confirmed
               ▼                                        ▼
        ┌──────────────┐   stop+flush TTS     ┌────────────────────┐
        │ FLUSH_OUTPUT │◄────────────────────│   USER_SPEAKING     │
        └──────┬───────┘                     └─────────┬───────────┘
               │ mark assistant msg as interrupted     │ STT resumes
               └───────────────────────────────────────┘
```

- **Debounced VAD** (200 ms continuous speech) prevents false barge-in from coughs/background TV (common in Indian home environments).
- **Echo cancellation:** AEC on the gateway so the bot's own TTS isn't detected as caller speech (critical on speakerphone).
- On barge-in: stop TTS, flush playback buffer, mark the partially-spoken `ai_message` with `is_interrupted=true`, and **truncate context** to what the caller actually heard (so the LLM doesn't assume it finished a sentence).
- **Half-duplex fallback** for very noisy PSTN lines: disable barge-in, use explicit turn-taking ("...over to you").

---

## 5. Latency Optimization & End-to-End Budget

**Target: < 1.2 s perceived turnaround** (caller stops speaking → hears bot start). Achieve via streaming overlap, not by making each stage faster in isolation.

### 5.1 Latency budget table (typical India deployment)

| Stage | Component | Budget (ms) | Notes / how |
|---|---|---|---|
| Network in | PSTN/RTP + jitter buffer | 60–120 | Exotel POP in India keeps this low |
| Endpointing | VAD finalize | 250–350 | configurable; counts after caller stops |
| STT final | Deepgram streaming | 100–200 | interim already arrived; final is fast |
| LLM TTFT | Gemini Flash time-to-first-token | 250–400 | streaming; prompt-cache system+tools |
| LLM → clause | first speakable clause ready | +50–100 | clause chunker |
| TTS TTFB | ElevenLabs Flash / Azure | 120–250 | streaming, first audio chunk |
| Network out | RTP back to caller | 60–120 | |
| **Perceived total** | (overlap-adjusted) | **~700–1100** | endpointing + TTFT + TTS-TTFB dominate |

> Overlap: STT-final, LLM-TTFT, and TTS overlap with the caller's own trailing audio and the playback buffer. The serial sum (≈1.4 s) is **not** what the caller perceives.

### 5.2 Optimization levers

- **Prompt caching** the system prompt + tool schemas + clinic context (Gemini/Claude) → lower TTFT and cost.
- **Speculative prefetch:** on interim transcript, pre-warm likely tool calls (e.g., start a doctor search while the caller finishes the sentence).
- **Co-locate** STT/LLM/TTS egress in the same region (Mumbai) as the telephony POP.
- **Persistent WS connections** to STT/TTS (avoid TLS handshake per turn).
- **First-clause TTS** + **filler audio** ("Let me check that for you...") to mask any tool-call latency > 800 ms.
- **Model tiering:** Flash for routine turns; escalate to Claude/GPT only for ambiguous triage or complaint handling.

---

## 6. Multilingual & Code-Switching (Hindi + regional)

- **Languages (launch):** Hindi, English, Hinglish (mixed), then Tamil, Telugu, Bengali, Marathi, Kannada.
- **Code-switching is the norm** in India ("Mujhe kal subah ek skin doctor chahiye, koi appointment available hai?"). We use STT with multilingual + Hinglish models (Deepgram nova multilingual / Whisper large-v3) rather than single-language models.
- **Language detection per utterance** (`voice_transcripts.lang_detected`) — the caller can switch mid-call; TTS voice + LLM response language follow the dominant detected language, with a sticky preference.
- **Number/date normalization** is locale-aware ("kal" = tomorrow, "parso", "do baje", lakh/crore for fees).
- **Transliteration:** Roman → Devanagari handled so search matches doctor names regardless of script.
- **TTS voice selection** per language from `clinic.voice_config` / user `preferred_lang_id`; fallback to Azure Neural which has the broadest Indic coverage.

---

## 7. Emotional Tone Handling

- **Prosody/acoustic cues** from STT (pitch, rate, pauses) + lexical sentiment → a lightweight `tone` signal (calm / anxious / distressed / angry).
- **Response adaptation:**
  - *Anxious/distressed* → slower TTS rate, reassuring phrasing, shorter sentences, faster path to a human or to triage red-flag check.
  - *Angry (complaint)* → empathy script + escalation offer; switch to Claude for nuanced de-escalation.
  - *Confused/elderly* → slower rate, repeat key info, confirm each step.
- **Red-flag/emergency tone + content** (chest pain, breathing difficulty, suicidal ideation) → immediately surface the **emergency disclaimer**, advise calling 112, and offer human handoff. This overrides the normal flow (see escalation FSM).
- Tone never used to diagnose; only to modulate delivery and routing.

---

## 8. Provider Comparisons + Recommendations

### 8.1 Telephony / Realtime Transport

| Provider | Coverage | Strengths | Weaknesses | Cost (approx) |
|---|---|---|---|---|
| **Exotel** | India PSTN/IVR | India-native, TRAI-compliant DLT/caller-ID, virtual numbers, missed-call APIs, local POP (low latency) | India-only, less modern media-streaming DX | ~₹0.40–0.80 / min |
| **Twilio** | Global + WhatsApp | Best DX/docs, Media Streams, global numbers, WhatsApp BSP | Costlier in India, India PSTN regulatory friction, intl latency | ~₹3–6 / min India |
| **Plivo** | Global incl. India | Cheaper than Twilio, India presence, decent streaming | Smaller ecosystem, fewer features | ~₹0.50–1.5 / min |
| **LiveKit** | Web/app WebRTC | Open-source, ultra-low-latency WebRTC, built-in Agents framework for voice AI, SIP bridge | Not a PSTN carrier itself (needs SIP trunk), self-host ops | infra cost only (self-host) |

**Recommendation:** **Exotel for India PSTN + IVR + missed-call** (compliance, latency, cost), **LiveKit for in-app/web realtime voice** (lowest latency, agent tooling, self-hostable), **Twilio strictly for international PSTN and WhatsApp**. This tri-stack is exactly the canonical choice: route by channel, not one-size-fits-all. *Why:* no single vendor is best at India-regulated PSTN **and** modern WebRTC **and** WhatsApp; splitting by strength minimizes both cost and latency while staying TRAI/DLT-compliant.

### 8.2 STT

| Provider | Streaming | Indic / Hinglish | Latency | Strengths | Weaknesses | Cost (approx) |
|---|---|---|---|---|---|---|
| **Deepgram** | Excellent (WS) | Good multilingual, keyword boost | Lowest (~100–200 ms final) | Real-time first, diarization, cheap, endpointing controls | Indic accuracy slightly below Whisper-large on hard accents | ~$0.0043/min (~₹0.36) |
| **Whisper (large-v3, self-host / OpenAI)** | Batch-native; streaming needs work | Best raw accuracy incl. code-switch | Higher unless self-hosted+chunked | Top accuracy, open weights, offline option | Not natively streaming; GPU cost; higher latency | self-host GPU / ~$0.006/min API |
| **AssemblyAI** | Good (WS) | Decent, fewer Indic specifics | Low-medium | Strong features (sentiment, entities) | Indic coverage weaker, US-centric | ~$0.015/min (~₹1.25) |

**Recommendation:** **Deepgram for real-time calls** (latency + streaming + cost win), with **Whisper large-v3 (self-hosted, batched) for WhatsApp voice notes and offline re-transcription/QA** where latency doesn't matter and accuracy does. *Why:* live voice is latency-bound (Deepgram), async voice notes are accuracy-bound (Whisper) — use each where it dominates.

### 8.3 TTS

| Provider | Latency | Indic voices | Naturalness | Strengths | Weaknesses | Cost (approx) |
|---|---|---|---|---|---|---|
| **ElevenLabs (Flash v2.5)** | Very low (~120–250 ms TTFB) | Multilingual incl. Hindi | Best naturalness, cloning | Streaming, emotion, voice clone | Pricier at scale, fewer pure-Indic regional voices | ~$0.06–0.10 / 1k chars |
| **Azure Neural TTS** | Low | Broadest Indic (hi, ta, te, mr, bn, kn, ml, gu, pa) | Very good | Best regional coverage, SSML, reliable, cheap | Slightly less "human" than ElevenLabs | ~$16 / 1M chars (~₹0.001/char) |
| **OpenAI TTS** | Low-medium | Multilingual, limited Indic tuning | Good | Simple API, decent quality | No streaming maturity for telephony, fewer Indic voices | ~$15 / 1M chars |

**Recommendation:** **ElevenLabs Flash for the premium conversational voice (Hindi/English) where naturalness matters**, **Azure Neural TTS as primary for regional Indic languages and as cost-effective fallback**. *Why:* ElevenLabs wins on naturalness/latency for the flagship experience; Azure wins on breadth of Indic regional voices and price — together they cover all 8 launch languages without a quality cliff.

---

## 9. Voice Receptionist Flow (inbound)

```
                         ┌──────────────────────┐
  Inbound call ─────────►│  GREETING + DISCLAIMER │  "Namaste, DoctorFind. This is an AI
                         │  (cached TTS)          │   assistant, not a doctor. For
                         └──────────┬─────────────┘   emergencies call 112."
                                    ▼
                         ┌──────────────────────┐
                         │   LANG + INTENT       │  detect language; "How can I help?"
                         └──────────┬─────────────┘
              ┌────────────┬────────┼─────────┬───────────────┐
              ▼            ▼        ▼          ▼               ▼
        ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐ ┌─────────────┐
        │  TRIAGE  │ │ DISCOVER │ │ BOOK   │ │ RESCHED/  │ │  SPEAK TO   │
        │ (symptom │ │ doctor   │ │ appt   │ │ CANCEL    │ │  HUMAN      │
        │  → need) │ │ search   │ │        │ │           │ │ (escalate)  │
        └────┬─────┘ └────┬─────┘ └───┬────┘ └────┬──────┘ └──────┬──────┘
             │ red flag?  │ results    │ slot      │               │
             ▼            ▼            ▼           ▼               ▼
        ┌──────────┐  confirm doctor → pick slot → confirm → SMS/WA confirmation
        │EMERGENCY │
        │ → 112 +  │  All paths end with: recap + disclaimer + "anything else?"
        │ human    │
        └──────────┘
```

LangGraph nodes map 1:1 to these states; each node has tools (search_doctors, get_slots, create_appointment, send_confirmation). `ai_conversations.state` persists the active node for resumability (Temporal-backed).

---

## 10. Appointment Reminder Call (outbound, Temporal-driven)

```
Temporal schedule fires (T-24h / T-2h)
   │
   ├─► place outbound call via Exotel
   │
   ├─► on answer: disclaimer + "This is a reminder for your appointment with
   │              Dr. X tomorrow at 4 PM. Press/say 1 to confirm, 2 to reschedule."
   │
   ├─► CONFIRM ──► update appointment.status=confirmed ──► WA confirmation
   ├─► RESCHEDULE ──► enter reschedule sub-flow ──► offer next slots
   ├─► NO ANSWER / VOICEMAIL ──► leave TTS message ──► retry policy (Temporal)
   └─► fallback to WhatsApp/SMS reminder if call fails after N attempts
```

State machine:

```
SCHEDULED ─fire─► DIALING ─answered─► PROMPTING ─input─► (CONFIRMED | RESCHEDULING)
                     │ no-answer/busy        │ timeout
                     ▼                        ▼
                  RETRY(≤3, backoff) ───► FALLBACK_WHATSAPP ───► DONE
```

Temporal guarantees: durable retries with backoff, exactly-once side effects (no double-calling), and audit via `reminders` rows.

---

## 11. Missed-Call Workflow (zero-cost lead capture, India pattern)

```
Patient gives a missed call to DoctorFind number
   │  (Exotel missed-call API webhook: caller number, timestamp)
   ▼
Temporal workflow:
   ├─► auto-disconnect (caller pays nothing)
   ├─► within ~5s: outbound call-back  OR  WhatsApp template message
   ├─► if call-back answered → enter VOICE RECEPTIONIST flow
   └─► if no answer → WhatsApp "Hi! You missed-called DoctorFind. Reply to book."
```

*Why:* missed-call is a deeply ingrained, free, low-friction entry point for price-sensitive and feature-phone users in India.

---

## 12. Escalation to Human

```
        ┌───────────────┐
        │  AI HANDLING   │
        └───────┬────────┘
   triggers:    │  • caller says "talk to a person"
   ───────────  │  • emergency/red-flag detected (triage_urgency=emergency)
                │  • 2x low-confidence / repeated misunderstanding
                │  • angry sentiment + complaint
                │  • out-of-scope (medical advice request → refuse + handoff)
                ▼
        ┌───────────────┐  warm transfer: pass summary + transcript context
        │  HUMAN QUEUE   │  (ai_conversations.handoff_to_human=true)
        └───────┬────────┘
        agent available?
          ┌─────┴─────┐
       yes▼           ▼ no (off-hours / queue full)
   ┌────────────┐  ┌──────────────────────────────┐
   │ LIVE AGENT │  │ CALLBACK PROMISE + ticket      │
   │ (SIP xfer) │  │ WA/SMS: "We'll call you back"  │
   └────────────┘  └──────────────────────────────┘
```

- **Warm handoff:** the human agent receives the rolling `summary`, structured `triage_summary`, and full transcript — no "please repeat everything."
- **Emergency override:** any emergency red flag short-circuits to disclaimer + 112 advice + immediate human, regardless of current node.
- **Scope guardrail:** if the caller asks for a diagnosis/prescription, the AI refuses ("I can't diagnose, but I can connect you to a doctor"), logs it, and offers booking/handoff.

---

## 13. End-to-End Cost-per-Minute Analysis (INR, indicative)

Assume a typical 1-minute conversational turn-dense call: ~30 s caller speech (STT), ~30 s bot speech (TTS ≈ ~750 chars), ~6 LLM turns (~1.2k in + 0.4k out tokens total).

| Component | Unit cost | Per-minute estimate (INR) |
|---|---|---|
| Telephony (Exotel PSTN, in/out) | ~₹0.60/min | **₹0.60** |
| STT (Deepgram streaming, ~0.5 min audio) | ~₹0.36/min audio | **₹0.18** |
| TTS (ElevenLabs Flash, ~750 chars) | ~₹6–8 / 1k chars | **₹0.70** (Azure: ~₹0.10) |
| LLM (Gemini Flash, ~1.6k tokens, cached prompt) | ~₹0.01–0.03 / 1k tok | **₹0.04** |
| Infra/orchestration (LiveKit/Temporal amortized) | — | **₹0.05** |
| **Total (ElevenLabs voice)** | | **≈ ₹1.55 / min** |
| **Total (Azure voice, cost-optimized)** | | **≈ ₹0.95 / min** |

Observations:
- **TTS is the swing cost** — use Azure for regional/high-volume and ElevenLabs only for premium flagship voice; cache all boilerplate (greeting/disclaimer) to drop effective TTS chars ~30%.
- **Telephony dominates** the floor in India; missed-call + WhatsApp routing pushes many interactions to near-zero telephony cost.
- **LLM cost is negligible** with Gemini Flash + prompt caching — model choice is driven by latency/quality, not price.
- WhatsApp voice-note path (async): no telephony cost, Whisper self-host STT amortized → **< ₹0.30 / interaction**, the cheapest channel.

---

## 14. Safety & Compliance (always-on)

- **Disclaimer** at call start, before any triage output, and at close: "I'm an AI assistant, not a medical professional. This is not a diagnosis. For emergencies, call 112."
- **No diagnosis / no prescription** — hard guardrail in the system prompt and a post-LLM validator that blocks diagnostic/prescriptive language.
- **Recording consent:** captured per `consents(type='recording')`; calls announce recording where required.
- **Data retention:** `voice_transcripts.audio_url` purged on a short retention policy (e.g., 30 days) unless consented for QA; transcripts redacted for analytics.
- **DPDP 2023 alignment:** consent capture, purpose limitation, erasure pipeline (see DB design §8).
- **Emergency detection** has highest priority in the agent graph and bypasses all other intents.
```
