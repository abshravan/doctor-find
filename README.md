# DoctorFind — AI Healthcare Navigator for India

> An AI healthcare navigator that helps patients discover the right doctors, clinics, and
> healthcare services using conversational AI, voice interfaces, smart triage, and workflow
> automation.
>
> **Think:** Zomato/Swiggy for healthcare discovery + an AI medical concierge — multilingual,
> mobile-first, voice-first, and WhatsApp-friendly.

> [!IMPORTANT]
> **DoctorFind is NOT a diagnostic tool.** It provides informational guidance, doctor/specialist
> discovery, appointment assistance, healthcare workflow automation, and symptom-based
> *navigation* only. Every AI surface ships with safety boundaries, disclaimers, and emergency
> escalation. See [`docs/07-ai-safety-compliance.md`](docs/07-ai-safety-compliance.md).

---

## 📚 Design & Strategy Docs

This repository is both a **strategy blueprint** and a **code scaffold**. The full 12-phase design
lives in [`docs/`](docs/):

| # | Phase | Document |
|---|-------|----------|
| 1 | Product Discovery | [`docs/01-product-discovery.md`](docs/01-product-discovery.md) |
| 2 | MVP Design | [`docs/02-mvp-design.md`](docs/02-mvp-design.md) |
| 3 | System Architecture | [`docs/03-system-architecture.md`](docs/03-system-architecture.md) |
| 4 | AI & Agent Design | [`docs/04-ai-agent-design.md`](docs/04-ai-agent-design.md) |
| 5 | Database Design | [`docs/05-database-design.md`](docs/05-database-design.md) |
| 6 | Voice AI Architecture | [`docs/06-voice-ai-architecture.md`](docs/06-voice-ai-architecture.md) |
| 7 | AI Safety & Compliance | [`docs/07-ai-safety-compliance.md`](docs/07-ai-safety-compliance.md) |
| 8 | UX/UI Design | [`docs/08-ux-ui-design.md`](docs/08-ux-ui-design.md) |
| 9 | Business Model | [`docs/09-business-model.md`](docs/09-business-model.md) |
| 10 | Go-To-Market | [`docs/10-go-to-market.md`](docs/10-go-to-market.md) |
| 11 | Execution Roadmap | [`docs/11-execution-roadmap.md`](docs/11-execution-roadmap.md) |
| 12 | Engineering Outputs | [`docs/12-engineering-outputs.md`](docs/12-engineering-outputs.md) |

---

## 🏗️ Canonical Stack (TL;DR)

| Layer | Choice | Why (1-liner) |
|-------|--------|---------------|
| Backend | **FastAPI** (Python) | Best AI ecosystem + async + speed of MVP |
| Web | **Next.js** | SEO for discovery + SSR + React |
| Mobile | **React Native (Expo)** | One codebase, OTA updates, fast iteration |
| DB | **PostgreSQL + pgvector** | Relational + vector search in one engine |
| Cache/Queue | **Redis** (Streams + Celery) | Cache, rate-limit, light eventing |
| Agent orchestration | **LangGraph** | Stateful, controllable agent graphs |
| Durable workflows | **Temporal** | Reliable bookings/reminders/follow-ups |
| LLM | **Gemini Flash** (+ OpenAI/Claude fallback) | Cost + strong Indian-language support |
| STT | **Deepgram** (realtime) / **Whisper** (batch) | Low-latency streaming + cheap offline |
| TTS | **ElevenLabs** / **Azure TTS** | Quality + Indian-language coverage/cost |
| Telephony | **Exotel** (India PSTN) + **LiveKit** (web/app) | TRAI/DLT-compliant + WebRTC realtime |
| Messaging | **WhatsApp Cloud API / Gupshup** | Where Indian patients already are |
| Auth | **Phone OTP (MSG91) + JWT** | Mobile-first identity |

Full rationale and comparison tables: [`docs/03-system-architecture.md`](docs/03-system-architecture.md).

---

## 🚀 Quick Start (local dev)

```bash
# 1. Copy env
cp .env.example .env

# 2. Boot Postgres + Redis + API
docker compose up --build

# 3. API is up
open http://localhost:8000/docs   # FastAPI Swagger UI
curl http://localhost:8000/health
```

Without Docker (API only):

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

---

## 🗂️ Monorepo Layout

```
doctor-find/
├── apps/
│   ├── api/          # FastAPI backend (modular monolith)
│   ├── web/          # Next.js web app (placeholder scaffold)
│   └── mobile/       # React Native (Expo) app (placeholder scaffold)
├── packages/
│   └── shared/       # Shared TS types / contracts (placeholder)
├── infra/            # Docker, k8s, CI/CD notes
├── docs/             # 12-phase design blueprint
├── docker-compose.yml
└── Makefile
```

See [`docs/12-engineering-outputs.md`](docs/12-engineering-outputs.md) for the full engineering
playbook (API design, CI/CD, Docker, k8s, observability).

---

## 🧭 Status

This is an **MVP scaffold + design blueprint**. The backend boots with a health check, sample
doctor-discovery and triage endpoints (stubbed AI), and the structure to grow into the full
architecture. It is intentionally a *modular monolith* (see Phase 3) — easy to run, easy to split
later.

## ⚖️ License & Disclaimer

Internal/early-stage. Not medical advice. Not for clinical decision-making.
