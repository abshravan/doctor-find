# Phase 5 — Database Design (DoctorFind)

> AI-first healthcare discovery & booking platform for India.
> Engine: **PostgreSQL 16** + **pgvector 0.7+** (HNSW) + **Redis 7** (cache / rate-limit / ephemeral session state).
> Conventions: `snake_case`, UUIDv7 PKs (time-sortable), `TIMESTAMPTZ` everywhere (store UTC, render IST), soft deletes via `deleted_at`, append-only `audit_logs`.

---

## 0. Design Principles

| Principle | Decision |
|---|---|
| Primary keys | `UUID` generated with `uuidv7()` (time-ordered → better index locality than v4). Fallback: `gen_random_uuid()` if extension unavailable. |
| Timestamps | All `TIMESTAMPTZ`; app sets UTC. Display layer localizes to `Asia/Kolkata`. |
| Money | `NUMERIC(12,2)` in INR (paise stored as whole rupees with 2 decimals); never `float`. |
| Phone | E.164 `VARCHAR(16)` (`+919876543210`) — India-first but international-safe. |
| Soft delete | `deleted_at TIMESTAMPTZ NULL`; all reads filter `deleted_at IS NULL` (enforced via views / app repo layer). Hard delete only for GDPR/DPDP erasure jobs. |
| Multi-tenant | Single-DB, shared-schema, **`clinic_id` tenant key** + Row Level Security (RLS). Large enterprise chains can be promoted to dedicated schema later. |
| Embeddings | `vector(768)` (Gemini `text-embedding-004`) for doctor/specialty semantic search and conversation memory. |
| Enums | Native PG `ENUM` types for closed sets; lookup tables for open/extensible sets (specialties, languages). |
| PII | Encrypted-at-rest column option via `pgcrypto` for Aadhaar-like identifiers; we **avoid storing Aadhaar**. |

```sql
-- Extensions (run once, superuser)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";       -- gen_random_uuid, crypt
CREATE EXTENSION IF NOT EXISTS "pg_trgm";        -- fuzzy text search
CREATE EXTENSION IF NOT EXISTS "vector";         -- pgvector
CREATE EXTENSION IF NOT EXISTS "btree_gin";      -- composite GIN incl scalar cols
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";      -- fallback uuid funcs
-- uuidv7(): use pg_uuidv7 ext if present, else a SQL/plpgsql shim (omitted here).
```

---

## 1. ER Diagram (ASCII)

```
                                    ┌──────────────┐
                                    │  languages   │
                                    └──────┬───────┘
                       ┌───────────────────┼────────────────────┐
                       │                    │                    │
              ┌────────▼────────┐  ┌────────▼────────┐  ┌────────▼────────┐
              │ doctor_languages │  │ user (lang_pref) │  │ clinic (lang)   │
              └────────┬────────┘  └─────────────────┘  └─────────────────┘
                       │
   ┌──────────┐  ┌─────▼──────┐   ┌───────────────────┐  ┌──────────────┐
   │ specialties│◄─┤  doctors   ├──►│ doctor_specialties │  │  addresses   │
   └──────────┘  └─────┬──────┘   └───────────────────┘  └──────┬───────┘
                       │                                          │
        ┌──────────────┼───────────────┐                         │
        │              │               │                         │
 ┌──────▼──────┐ ┌─────▼──────┐ ┌──────▼───────┐          ┌──────▼──────┐
 │ availability │ │  reviews   │ │ appointments │◄─────────┤   clinics   │
 │ (slots+rules)│ └────────────┘ └──────┬───────┘          └──────┬──────┘
 └─────────────┘                        │                         │
                                        │  ┌──────────────────────┘
              ┌─────────────────────────┤  │
              │                         ▼  ▼
 ┌────────────▼─────┐          ┌──────────────┐      ┌───────────────┐
 │      users       │◄─────────┤   payments   │      │ subscriptions │
 └────┬────────┬────┘          └──────────────┘      └───────────────┘
      │        │
      │        │      ┌──────────────────┐    ┌──────────────────┐
      │        └─────►│ ai_conversations  ├───►│   ai_messages    │
      │               └────────┬─────────┘    └──────────────────┘
      │                        │
      │               ┌────────▼─────────┐
      │               │ voice_transcripts │
      │               └──────────────────┘
      │
      ├──────►┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
      │       │  reminders   │   │ notifications │   │ otp_verifications│
      │       └──────────────┘   └──────────────┘   └──────────────────┘
      │
      ├──────►┌──────────────┐   ┌──────────────┐
      └──────►│  consents    │   │  audit_logs  │ (refs any actor/entity)
              └──────────────┘   └──────────────┘

Legend:  ──►  FK (many→one points to the "one")
         ◄──  reverse for readability
```

Cardinalities (key relationships):

- `users 1—N appointments`, `doctors 1—N appointments`, `clinics 1—N appointments`.
- `doctors N—M specialties` via `doctor_specialties`.
- `doctors N—M languages` via `doctor_languages`.
- `users 1—N ai_conversations 1—N ai_messages`.
- `ai_conversations 1—N voice_transcripts` (one transcript chunk per turn/utterance).
- `appointments 1—1 payments` (and `payments N—1 users`).
- `clinics 1—N doctors` (a doctor may also be independent → nullable clinic FK or `doctor_clinics` join; we model primary `clinic_id` nullable on doctor + many-to-many later if needed).

---

## 2. Enum Types

```sql
CREATE TYPE user_role            AS ENUM ('patient','doctor','clinic_admin','ops','superadmin');
CREATE TYPE gender_t             AS ENUM ('male','female','other','undisclosed');
CREATE TYPE appointment_status   AS ENUM ('pending','confirmed','rescheduled','cancelled','no_show','completed','in_progress');
CREATE TYPE appointment_mode     AS ENUM ('in_person','video','audio','home_visit');
CREATE TYPE consult_channel      AS ENUM ('app','web','whatsapp','voice_call','ivr');
CREATE TYPE payment_status       AS ENUM ('created','authorized','captured','failed','refunded','partially_refunded');
CREATE TYPE payment_method       AS ENUM ('upi','card','netbanking','wallet','cash','insurance');
CREATE TYPE reminder_channel     AS ENUM ('sms','whatsapp','push','voice_call','email');
CREATE TYPE reminder_status      AS ENUM ('scheduled','sent','delivered','failed','cancelled');
CREATE TYPE notification_type    AS ENUM ('booking','reminder','payment','review_request','marketing','system','triage_alert');
CREATE TYPE conversation_channel AS ENUM ('app','web','whatsapp','voice_call','ivr','sms');
CREATE TYPE message_role         AS ENUM ('user','assistant','system','tool','human_agent');
CREATE TYPE consent_type         AS ENUM ('tnc','privacy','data_processing','marketing','teleconsult','recording','dpdp_2023');
CREATE TYPE subscription_tier    AS ENUM ('free','plus','clinic_basic','clinic_pro','enterprise');
CREATE TYPE subscription_status  AS ENUM ('trialing','active','past_due','cancelled','expired');
CREATE TYPE availability_kind    AS ENUM ('recurring_rule','one_off_slot','blackout');
CREATE TYPE triage_urgency       AS ENUM ('emergency','urgent','soon','routine','self_care','unknown');
```

---

## 3. Core Tables — DDL

### 3.1 languages / addresses (supporting, referenced early)

```sql
CREATE TABLE languages (
    id          SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    iso_code    VARCHAR(8)  NOT NULL UNIQUE,         -- 'hi','en','ta','te','bn','mr','kn','ml','gu','pa'
    name        VARCHAR(64) NOT NULL,                -- 'Hindi'
    native_name VARCHAR(64) NOT NULL,                -- 'हिन्दी'
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE
);

CREATE TABLE addresses (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    line1         VARCHAR(255) NOT NULL,
    line2         VARCHAR(255),
    locality      VARCHAR(128),                       -- area / sub-locality
    city          VARCHAR(128) NOT NULL,
    district      VARCHAR(128),
    state         VARCHAR(128) NOT NULL,
    pincode       VARCHAR(10)  NOT NULL CHECK (pincode ~ '^[1-9][0-9]{5}$'),
    country       VARCHAR(2)   NOT NULL DEFAULT 'IN',
    geo_lat       NUMERIC(9,6),                       -- -90..90
    geo_lng       NUMERIC(9,6),                       -- -180..180
    geog          GEOGRAPHY(POINT,4326),              -- if PostGIS enabled; else use lat/lng
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_lat CHECK (geo_lat  BETWEEN -90  AND 90),
    CONSTRAINT chk_lng CHECK (geo_lng  BETWEEN -180 AND 180)
);
```

### 3.2 users

```sql
CREATE TABLE users (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role               user_role    NOT NULL DEFAULT 'patient',
    phone              VARCHAR(16)  NOT NULL,            -- E.164, primary login in India
    phone_verified     BOOLEAN      NOT NULL DEFAULT FALSE,
    email              VARCHAR(255),
    email_verified     BOOLEAN      NOT NULL DEFAULT FALSE,
    full_name          VARCHAR(160),
    display_name       VARCHAR(80),
    gender             gender_t,
    date_of_birth      DATE,
    preferred_lang_id  SMALLINT     REFERENCES languages(id),
    primary_address_id UUID         REFERENCES addresses(id),
    avatar_url         TEXT,
    -- DPDP / consent quick flags (source of truth = consents table)
    marketing_opt_in   BOOLEAN      NOT NULL DEFAULT FALSE,
    -- auth
    password_hash      TEXT,                            -- nullable: OTP-first users may never set one
    last_login_at      TIMESTAMPTZ,
    -- metadata
    metadata           JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at         TIMESTAMPTZ,
    CONSTRAINT uq_users_phone        UNIQUE (phone),
    CONSTRAINT chk_phone_e164        CHECK (phone ~ '^\+[1-9][0-9]{7,14}$'),
    CONSTRAINT chk_email_fmt         CHECK (email IS NULL OR email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
    CONSTRAINT chk_dob_past          CHECK (date_of_birth IS NULL OR date_of_birth < CURRENT_DATE)
);
```

### 3.3 clinics (tenant root)

```sql
CREATE TABLE clinics (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name               VARCHAR(200) NOT NULL,
    slug               VARCHAR(120) NOT NULL UNIQUE,    -- url + tenant routing
    legal_name         VARCHAR(255),
    gstin              VARCHAR(15)  CHECK (gstin IS NULL OR gstin ~ '^[0-9A-Z]{15}$'),
    address_id         UUID REFERENCES addresses(id),
    phone              VARCHAR(16),
    email              VARCHAR(255),
    timezone           VARCHAR(64)  NOT NULL DEFAULT 'Asia/Kolkata',
    default_lang_id    SMALLINT REFERENCES languages(id),
    logo_url           TEXT,
    -- voice receptionist config (per-tenant)
    voice_config       JSONB        NOT NULL DEFAULT '{}'::jsonb, -- {tts_voice, greeting, business_hours...}
    is_verified        BOOLEAN      NOT NULL DEFAULT FALSE,
    is_active          BOOLEAN      NOT NULL DEFAULT TRUE,
    metadata           JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at         TIMESTAMPTZ
);

-- Clinic staff mapping (who can act on behalf of a tenant)
CREATE TABLE clinic_members (
    clinic_id   UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id)   ON DELETE CASCADE,
    role        user_role NOT NULL DEFAULT 'clinic_admin',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (clinic_id, user_id)
);
```

### 3.4 specialties / doctors / join tables

```sql
CREATE TABLE specialties (
    id           SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code         VARCHAR(48) NOT NULL UNIQUE,          -- 'cardiology'
    name         VARCHAR(96) NOT NULL,                 -- 'Cardiology'
    synonyms     TEXT[]      NOT NULL DEFAULT '{}',     -- ['heart specialist','हृदय रोग']
    description  TEXT,
    embedding    VECTOR(768),                           -- semantic match for "chest pain doctor"
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE
);

CREATE TABLE doctors (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID UNIQUE REFERENCES users(id) ON DELETE SET NULL, -- login identity (optional)
    clinic_id          UUID REFERENCES clinics(id),       -- primary clinic; NULL = independent
    full_name          VARCHAR(160) NOT NULL,
    gender             gender_t,
    reg_number         VARCHAR(64),                        -- state medical council reg no.
    reg_council        VARCHAR(96),                        -- 'Karnataka Medical Council'
    qualifications     VARCHAR(255),                       -- 'MBBS, MD (Medicine)'
    experience_years   SMALLINT CHECK (experience_years BETWEEN 0 AND 80),
    consultation_fee   NUMERIC(10,2) CHECK (consultation_fee >= 0),
    bio                TEXT,
    photo_url          TEXT,
    rating_avg         NUMERIC(3,2) NOT NULL DEFAULT 0 CHECK (rating_avg BETWEEN 0 AND 5),
    rating_count       INTEGER      NOT NULL DEFAULT 0,
    is_verified        BOOLEAN      NOT NULL DEFAULT FALSE,  -- KYC + reg verified
    is_accepting       BOOLEAN      NOT NULL DEFAULT TRUE,
    search_doc         TSVECTOR,                            -- maintained by trigger
    embedding          VECTOR(768),                         -- bio+specialty embedding for semantic search
    metadata           JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at         TIMESTAMPTZ
);

CREATE TABLE doctor_specialties (
    doctor_id    UUID     NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    specialty_id SMALLINT NOT NULL REFERENCES specialties(id),
    is_primary   BOOLEAN  NOT NULL DEFAULT FALSE,
    PRIMARY KEY (doctor_id, specialty_id)
);

CREATE TABLE doctor_languages (
    doctor_id    UUID     NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    language_id  SMALLINT NOT NULL REFERENCES languages(id),
    proficiency  SMALLINT NOT NULL DEFAULT 3 CHECK (proficiency BETWEEN 1 AND 5),
    PRIMARY KEY (doctor_id, language_id)
);

-- Enforce: at most one primary specialty per doctor
CREATE UNIQUE INDEX uq_doctor_primary_specialty
    ON doctor_specialties (doctor_id) WHERE is_primary;
```

### 3.5 availability (recurring rules + one-off slots + blackouts)

```sql
CREATE TABLE availability (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id     UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    clinic_id     UUID REFERENCES clinics(id),         -- where this availability applies
    kind          availability_kind NOT NULL,
    mode          appointment_mode  NOT NULL DEFAULT 'in_person',
    -- RECURRING: day-of-week 0=Sun..6=Sat + local time window + slot length
    weekday       SMALLINT CHECK (weekday BETWEEN 0 AND 6),
    start_time    TIME,                                 -- clinic-local
    end_time      TIME,
    slot_minutes  SMALLINT CHECK (slot_minutes BETWEEN 5 AND 240),
    -- ONE-OFF / BLACKOUT: explicit window (UTC stored)
    starts_at     TIMESTAMPTZ,
    ends_at       TIMESTAMPTZ,
    valid_from    DATE,                                 -- recurring rule effective range
    valid_until   DATE,
    capacity      SMALLINT NOT NULL DEFAULT 1,          -- parallel patients per slot
    is_active     BOOLEAN  NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_recurring CHECK (
        kind <> 'recurring_rule' OR
        (weekday IS NOT NULL AND start_time IS NOT NULL AND end_time IS NOT NULL
         AND slot_minutes IS NOT NULL AND end_time > start_time)
    ),
    CONSTRAINT chk_oneoff CHECK (
        kind = 'recurring_rule' OR
        (starts_at IS NOT NULL AND ends_at IS NOT NULL AND ends_at > starts_at)
    )
);
```
> Materialized bookable slots are **generated on read** (next 30 days) from rules minus blackouts minus booked appointments, cached in Redis (`slots:{doctor_id}:{date}` TTL 60s). We do not store every concrete slot row — avoids slot-table bloat.

### 3.6 appointments (PARTITIONED by month)

```sql
CREATE TABLE appointments (
    id                UUID         NOT NULL DEFAULT gen_random_uuid(),
    patient_id        UUID         NOT NULL REFERENCES users(id),
    doctor_id         UUID         NOT NULL REFERENCES doctors(id),
    clinic_id         UUID         REFERENCES clinics(id),     -- tenant key
    booked_by         UUID         REFERENCES users(id),       -- self / family / ops / AI(NULL)
    channel           consult_channel NOT NULL DEFAULT 'app',
    mode              appointment_mode NOT NULL DEFAULT 'in_person',
    status            appointment_status NOT NULL DEFAULT 'pending',
    scheduled_start   TIMESTAMPTZ  NOT NULL,
    scheduled_end     TIMESTAMPTZ  NOT NULL,
    fee_amount        NUMERIC(10,2) CHECK (fee_amount >= 0),
    -- triage context captured at booking (NOT a diagnosis)
    triage_urgency    triage_urgency,
    reason_text       TEXT,
    triage_summary    JSONB,                                    -- {symptoms[], duration, red_flags[]}
    conversation_id   UUID,                                     -- FK added after ai_conversations exists
    cancel_reason     TEXT,
    cancelled_by      UUID REFERENCES users(id),
    metadata          JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at        TIMESTAMPTZ,
    PRIMARY KEY (id, scheduled_start),                          -- partition key must be in PK
    CONSTRAINT chk_time_order CHECK (scheduled_end > scheduled_start)
) PARTITION BY RANGE (scheduled_start);

-- Monthly partitions (create rolling via pg_partman or a cron job)
CREATE TABLE appointments_2026_06 PARTITION OF appointments
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE appointments_2026_07 PARTITION OF appointments
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
-- DEFAULT catch-all (so inserts never fail if a partition is missing)
CREATE TABLE appointments_default PARTITION OF appointments DEFAULT;

-- Prevent double-booking the same doctor for overlapping confirmed slots.
-- (btree_gist needed for exclusion w/ equality on doctor_id + range overlap)
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE appointments
  ADD CONSTRAINT excl_doctor_overlap
  EXCLUDE USING gist (
      doctor_id WITH =,
      tstzrange(scheduled_start, scheduled_end) WITH &&
  ) WHERE (status IN ('confirmed','in_progress') AND deleted_at IS NULL);
```
> Note: exclusion constraints on partitioned parents are not supported directly pre-PG17 — apply the `EXCLUDE` per-partition (template via pg_partman), or enforce via advisory lock + check in the booking service. Documented as **per-partition constraint** in the migration template.

### 3.7 reviews

```sql
CREATE TABLE reviews (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appointment_id  UUID UNIQUE REFERENCES appointments_root_fk(id), -- see note: FK to logical appt
    patient_id      UUID NOT NULL REFERENCES users(id),
    doctor_id       UUID NOT NULL REFERENCES doctors(id),
    clinic_id       UUID REFERENCES clinics(id),
    rating          SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    title           VARCHAR(160),
    body            TEXT,
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,    -- tied to a completed appt
    is_published    BOOLEAN NOT NULL DEFAULT TRUE,     -- moderation flag
    helpful_count   INTEGER NOT NULL DEFAULT 0,
    reply_text      TEXT,                              -- doctor/clinic response
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,
    CONSTRAINT uq_review_per_appt UNIQUE (appointment_id)
);
```
> FK to a partitioned table by `id` alone is not allowed (PK is composite). Practical options: (a) drop the FK and validate in app, (b) keep an `appointments_index(id PK, scheduled_start)` lightweight non-partitioned mirror for FK targets. We use option (b): a thin `appointment_keys(id UUID PK, scheduled_start TIMESTAMPTZ)` table written in the same txn, and FKs point there. (Above `appointments_root_fk` denotes that target.)

### 3.8 AI conversations / messages / voice transcripts

```sql
CREATE TABLE ai_conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),         -- NULL for anon/pre-auth IVR
    clinic_id       UUID REFERENCES clinics(id),        -- tenant if clinic-scoped
    channel         conversation_channel NOT NULL,
    external_ref    VARCHAR(128),                        -- Exotel CallSid / LiveKit room / WA msg thread
    lang_id         SMALLINT REFERENCES languages(id),
    state           VARCHAR(48) NOT NULL DEFAULT 'open', -- langgraph node / FSM state
    triage_urgency  triage_urgency,
    summary         TEXT,                                -- rolling LLM summary (memory compaction)
    summary_embedding VECTOR(768),                       -- semantic recall of past chats
    handoff_to_human BOOLEAN NOT NULL DEFAULT FALSE,
    temporal_workflow_id VARCHAR(128),                   -- Temporal correlation
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

CREATE TABLE ai_messages (
    id              UUID NOT NULL DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    seq             INTEGER NOT NULL,                    -- ordinal within conversation
    role            message_role NOT NULL,
    content         TEXT,                                -- final text (post-STT for user voice)
    content_redacted TEXT,                               -- PII-masked copy for analytics
    tool_name       VARCHAR(96),                         -- when role='tool'
    tool_payload    JSONB,
    model           VARCHAR(64),                         -- 'gemini-2.0-flash','claude-...','gpt-...'
    prompt_tokens   INTEGER,
    completion_tokens INTEGER,
    latency_ms      INTEGER,
    embedding       VECTOR(768),                         -- per-message vector for RAG over history
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at),
    CONSTRAINT uq_conv_seq UNIQUE (conversation_id, seq)
) PARTITION BY RANGE (created_at);

CREATE TABLE ai_messages_2026_06 PARTITION OF ai_messages
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE ai_messages_default PARTITION OF ai_messages DEFAULT;

CREATE TABLE voice_transcripts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    message_id      UUID,                                -- links to ai_messages.id (logical)
    speaker         message_role NOT NULL,               -- user | assistant
    stt_provider    VARCHAR(32),                         -- 'deepgram','whisper'
    tts_provider    VARCHAR(32),                         -- 'elevenlabs','azure'
    lang_detected   VARCHAR(8),                          -- detected code, may differ from conv lang
    text_raw        TEXT,                                -- verbatim STT (may include disfluency)
    text_clean      TEXT,                                -- normalized
    confidence      NUMERIC(4,3) CHECK (confidence BETWEEN 0 AND 1),
    audio_url       TEXT,                                -- object-store URI (S3/GCS), short retention
    audio_ms        INTEGER,
    is_interrupted  BOOLEAN NOT NULL DEFAULT FALSE,      -- barge-in occurred
    word_timings    JSONB,                               -- [{w,start,end,conf}] for alignment
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ                           -- audio purged on retention policy
);

-- Add deferred FK now that ai_conversations exists
ALTER TABLE appointments
  ADD CONSTRAINT fk_appt_conversation
  FOREIGN KEY (conversation_id) REFERENCES ai_conversations(id);
```

### 3.9 reminders / notifications (notifications PARTITIONED)

```sql
CREATE TABLE reminders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appointment_id  UUID REFERENCES appointment_keys(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    channel         reminder_channel NOT NULL,
    status          reminder_status NOT NULL DEFAULT 'scheduled',
    scheduled_for   TIMESTAMPTZ NOT NULL,
    sent_at         TIMESTAMPTZ,
    attempts        SMALLINT NOT NULL DEFAULT 0,
    max_attempts    SMALLINT NOT NULL DEFAULT 3,
    temporal_workflow_id VARCHAR(128),                   -- Temporal schedules the fire
    template_key    VARCHAR(96),
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    provider_msg_id VARCHAR(128),
    last_error      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE notifications (
    id              UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    type            notification_type NOT NULL,
    channel         reminder_channel NOT NULL,
    title           VARCHAR(200),
    body            TEXT,
    status          reminder_status NOT NULL DEFAULT 'scheduled',
    read_at         TIMESTAMPTZ,
    provider_msg_id VARCHAR(128),
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE notifications_2026_06 PARTITION OF notifications
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE notifications_default PARTITION OF notifications DEFAULT;
```

### 3.10 payments / subscriptions

```sql
CREATE TABLE payments (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appointment_id     UUID REFERENCES appointment_keys(id),
    user_id            UUID NOT NULL REFERENCES users(id),
    clinic_id          UUID REFERENCES clinics(id),
    amount             NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    currency           VARCHAR(3) NOT NULL DEFAULT 'INR',
    method             payment_method,
    status             payment_status NOT NULL DEFAULT 'created',
    gateway            VARCHAR(32) NOT NULL DEFAULT 'razorpay',
    gateway_order_id   VARCHAR(128),
    gateway_payment_id VARCHAR(128),
    gateway_signature  VARCHAR(256),
    refund_amount      NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (refund_amount >= 0),
    idempotency_key    VARCHAR(128) UNIQUE,              -- prevents duplicate charges
    raw_response       JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_refund_le_amount CHECK (refund_amount <= amount)
);

CREATE TABLE subscriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id   UUID REFERENCES users(id),           -- B2C
    clinic_id       UUID REFERENCES clinics(id),          -- B2B tenant
    tier            subscription_tier NOT NULL DEFAULT 'free',
    status          subscription_status NOT NULL DEFAULT 'active',
    seats           SMALLINT NOT NULL DEFAULT 1,
    price_amount    NUMERIC(12,2) NOT NULL DEFAULT 0,
    billing_cycle   VARCHAR(16) NOT NULL DEFAULT 'monthly', -- monthly|annual
    current_period_start TIMESTAMPTZ,
    current_period_end   TIMESTAMPTZ,
    trial_ends_at   TIMESTAMPTZ,
    gateway_sub_id  VARCHAR(128),
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_owner_or_clinic CHECK (owner_user_id IS NOT NULL OR clinic_id IS NOT NULL)
);
```

### 3.11 otp_verifications / consents / audit_logs

```sql
CREATE TABLE otp_verifications (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone         VARCHAR(16),
    email         VARCHAR(255),
    purpose       VARCHAR(32) NOT NULL DEFAULT 'login',  -- login|booking|consent
    code_hash     TEXT NOT NULL,                          -- bcrypt/argon hash, never plaintext
    attempts      SMALLINT NOT NULL DEFAULT 0,
    max_attempts  SMALLINT NOT NULL DEFAULT 5,
    expires_at    TIMESTAMPTZ NOT NULL,
    consumed_at   TIMESTAMPTZ,
    ip            INET,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_target CHECK (phone IS NOT NULL OR email IS NOT NULL)
);
-- Operationally short-lived; consider TTL cleanup or move to Redis. Kept in PG for audit.

CREATE TABLE consents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type          consent_type NOT NULL,
    version       VARCHAR(24) NOT NULL,                  -- policy doc version e.g. 'privacy-v3'
    granted       BOOLEAN NOT NULL,
    channel       conversation_channel,                  -- where consent captured
    ip            INET,
    user_agent    TEXT,
    granted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at    TIMESTAMPTZ,
    evidence      JSONB,                                 -- recording id / signed token
    CONSTRAINT uq_consent UNIQUE (user_id, type, version)
);

CREATE TABLE audit_logs (
    id            UUID NOT NULL DEFAULT gen_random_uuid(),
    actor_user_id UUID,                                  -- nullable (system/AI actor)
    actor_type    VARCHAR(24) NOT NULL DEFAULT 'user',   -- user|system|ai|ops
    clinic_id     UUID,                                  -- tenant scope
    action        VARCHAR(64) NOT NULL,                  -- 'appointment.cancel'
    entity_type   VARCHAR(48) NOT NULL,                  -- 'appointment'
    entity_id     UUID,
    before        JSONB,                                 -- prev state (PII-redacted)
    after         JSONB,                                 -- new state
    ip            INET,
    request_id    VARCHAR(64),                           -- trace correlation
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE audit_logs_2026_06 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE audit_logs_default PARTITION OF audit_logs DEFAULT;
```

### 3.12 appointment_keys (FK target for partitioned appointments)

```sql
CREATE TABLE appointment_keys (
    id              UUID PRIMARY KEY,
    scheduled_start TIMESTAMPTZ NOT NULL
);
-- Written in the same transaction as the partitioned appointments row.
-- All FKs that "point to an appointment" reference this thin table.
```

---

## 4. Indexing Strategy

### 4.1 B-tree (lookups, joins, sort, range)

```sql
-- Hot foreign keys & status filters
CREATE INDEX idx_appt_doctor_time   ON appointments (doctor_id, scheduled_start);
CREATE INDEX idx_appt_patient_time  ON appointments (patient_id, scheduled_start DESC);
CREATE INDEX idx_appt_clinic_status ON appointments (clinic_id, status, scheduled_start);
CREATE INDEX idx_msg_conv_seq       ON ai_messages (conversation_id, seq);
CREATE INDEX idx_conv_user          ON ai_conversations (user_id, started_at DESC);
CREATE INDEX idx_pay_user           ON payments (user_id, created_at DESC);
CREATE INDEX idx_reviews_doctor     ON reviews (doctor_id, created_at DESC);

-- Partial: only schedulable reminders the worker scans
CREATE INDEX idx_reminders_due
    ON reminders (scheduled_for)
    WHERE status = 'scheduled';

-- Partial: active, accepting, verified doctors only (search default set)
CREATE INDEX idx_doctors_live
    ON doctors (clinic_id)
    WHERE deleted_at IS NULL AND is_verified AND is_accepting;

-- Composite for "doctor's upcoming confirmed schedule"
CREATE INDEX idx_appt_doctor_upcoming
    ON appointments (doctor_id, scheduled_start)
    WHERE status IN ('confirmed','in_progress') AND deleted_at IS NULL;

-- Unique active phone (soft-delete aware): allow re-use of phone after deletion
DROP INDEX IF EXISTS uq_users_phone;  -- replace the table-level UNIQUE
CREATE UNIQUE INDEX uq_users_phone_active
    ON users (phone) WHERE deleted_at IS NULL;
```

### 4.2 GIN (full-text, trigram fuzzy, JSONB, arrays)

```sql
-- Full-text doctor search (name + bio + qualifications), maintained tsvector column
CREATE INDEX idx_doctors_fts ON doctors USING gin (search_doc);

-- Fuzzy / typo-tolerant name match (e.g. "kumr" -> "Kumar")
CREATE INDEX idx_doctors_name_trgm ON doctors USING gin (full_name gin_trgm_ops);
CREATE INDEX idx_specialty_syn_trgm ON specialties USING gin (synonyms);  -- array containment

-- JSONB queries on triage summary / metadata
CREATE INDEX idx_appt_triage_gin ON appointments USING gin (triage_summary jsonb_path_ops);
CREATE INDEX idx_users_meta_gin  ON users USING gin (metadata jsonb_path_ops);

-- Composite GIN (btree_gin) for "search within clinic"
CREATE INDEX idx_doctors_clinic_fts ON doctors USING gin (clinic_id, search_doc);
```

`search_doc` maintenance trigger:

```sql
CREATE OR REPLACE FUNCTION doctors_tsv_update() RETURNS trigger AS $$
BEGIN
  NEW.search_doc :=
      setweight(to_tsvector('simple', coalesce(NEW.full_name,'')), 'A') ||
      setweight(to_tsvector('english', coalesce(NEW.qualifications,'')), 'B') ||
      setweight(to_tsvector('english', coalesce(NEW.bio,'')), 'C');
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_doctors_tsv
  BEFORE INSERT OR UPDATE OF full_name, qualifications, bio ON doctors
  FOR EACH ROW EXECUTE FUNCTION doctors_tsv_update();
```

### 4.3 pgvector (semantic search & memory)

```sql
-- HNSW preferred (better recall/latency, no training step). cosine distance.
CREATE INDEX idx_doctors_embed_hnsw
    ON doctors USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_specialty_embed_hnsw
    ON specialties USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Conversation memory recall (RAG over past summaries)
CREATE INDEX idx_conv_summary_embed_hnsw
    ON ai_conversations USING hnsw (summary_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Alternative IVFFlat (lower build cost, needs ANALYZE + lists tuning) for very large sets:
-- CREATE INDEX idx_doctors_embed_ivf ON doctors
--   USING ivfflat (embedding vector_cosine_ops) WITH (lists = 200);
-- Rule of thumb: lists ≈ rows/1000 (≤1M rows) ; set ef_search / probes at query time.
```

Query-time tuning:

```sql
SET hnsw.ef_search = 80;     -- recall vs latency knob (per-session)
-- SET ivfflat.probes = 10;  -- if IVFFlat used
```

### 4.4 Index decision matrix

| Need | Index type | Example column |
|---|---|---|
| Equality / range / sort | B-tree | `appointments(doctor_id, scheduled_start)` |
| Filtered subset hot path | Partial B-tree | `reminders WHERE status='scheduled'` |
| Keyword full-text | GIN(tsvector) | `doctors.search_doc` |
| Typo-tolerant name | GIN(trgm) | `doctors.full_name` |
| JSONB containment | GIN(jsonb_path_ops) | `appointments.triage_summary` |
| Array membership | GIN | `specialties.synonyms` |
| Semantic / "find similar" | HNSW (pgvector) | `doctors.embedding` |
| No-double-book | GiST EXCLUDE | `appointments` tstzrange |

---

## 5. Query Optimization

### 5.1 Doctor discovery — slow vs optimized

**Naive (slow):** ILIKE scan + correlated subquery for rating + no index usage.

```sql
-- BEFORE: seq scan, ILIKE not indexable, subquery per row
SELECT d.*,
       (SELECT avg(rating) FROM reviews r WHERE r.doctor_id = d.id) AS rating
FROM doctors d
JOIN doctor_specialties ds ON ds.doctor_id = d.id
JOIN specialties s ON s.id = ds.specialty_id
WHERE d.bio ILIKE '%diabetes%'
  AND s.name ILIKE '%endocrin%'
ORDER BY rating DESC NULLS LAST
LIMIT 20;
-- EXPLAIN: Seq Scan on doctors (cost ~ rows*N), Subplan per row. ~800ms @ 50k docs.
```

**Optimized:** denormalized `rating_avg` (kept by trigger), FTS + trigram, partial-index-friendly filters, hybrid with vector pre-filter.

```sql
-- AFTER: GIN FTS, denormalized rating, covered ordering
SELECT d.id, d.full_name, d.qualifications, d.rating_avg, d.consultation_fee
FROM doctors d
JOIN doctor_specialties ds ON ds.doctor_id = d.id
JOIN specialties s ON s.id = ds.specialty_id AND s.code = 'endocrinology'
WHERE d.deleted_at IS NULL AND d.is_verified AND d.is_accepting
  AND d.search_doc @@ plainto_tsquery('english','diabetes')
ORDER BY d.rating_avg DESC, d.rating_count DESC
LIMIT 20;
-- Uses idx_doctors_fts + idx_doctors_live ; ~6-15ms @ 50k docs.
```

**Hybrid semantic + keyword (AI-routed search):** vector candidate set, re-rank by rating + distance.

```sql
WITH semantic AS (
  SELECT id, embedding <=> $1 AS dist          -- $1 = query embedding (768)
  FROM doctors
  WHERE deleted_at IS NULL AND is_verified AND is_accepting
  ORDER BY embedding <=> $1
  LIMIT 100
)
SELECT d.id, d.full_name, d.rating_avg, sm.dist
FROM semantic sm
JOIN doctors d ON d.id = sm.id
WHERE d.search_doc @@ plainto_tsquery('english', $2)   -- optional keyword tighten
ORDER BY (0.7 * (1 - sm.dist)) + (0.3 * d.rating_avg/5.0) DESC
LIMIT 20;
```

### 5.2 Slot availability check (avoid scanning all appointments)

```sql
-- Uses idx_appt_doctor_upcoming (partial) + partition pruning by scheduled_start range
SELECT 1
FROM appointments
WHERE doctor_id = $1
  AND status IN ('confirmed','in_progress')
  AND tstzrange(scheduled_start, scheduled_end) && tstzrange($2, $3)
LIMIT 1;
```

### 5.3 General tactics

- **Partition pruning:** always include a `scheduled_start`/`created_at` predicate so the planner touches one partition.
- **Covering indexes / `INCLUDE`:** add `INCLUDE (rating_avg)` to avoid heap fetches on hot lists.
- **Denormalize aggregates:** `doctors.rating_avg/rating_count` updated by trigger on `reviews` — eliminates per-request AVG.
- **Keyset pagination** (`WHERE (scheduled_start, id) < ($cursor)`) instead of `OFFSET` for deep lists.
- **`EXPLAIN (ANALYZE, BUFFERS)`** in CI on representative data; alert on seq scans of hot tables.
- **Statistics:** raise `default_statistics_target` to 500 on `appointments.scheduled_start`, `doctors.clinic_id`.

---

## 6. Partitioning Strategy

| Table | Strategy | Key | Granularity | Retention |
|---|---|---|---|---|
| `appointments` | RANGE | `scheduled_start` | monthly | hot 13 months, archive older to cold storage |
| `ai_messages` | RANGE | `created_at` | monthly | 6 months hot, summarize+drop detail after |
| `notifications` | RANGE | `created_at` | monthly | 3 months, then drop |
| `audit_logs` | RANGE | `created_at` | monthly | 7 years (compliance) — move old to compressed/cold |

Automation (pg_partman):

```sql
SELECT partman.create_parent(
  p_parent_table := 'public.appointments',
  p_control      := 'scheduled_start',
  p_type         := 'range',
  p_interval     := '1 month',
  p_premake      := 3                     -- pre-create 3 future months
);
-- Schedule maintenance to create future + drop/detach expired partitions
SELECT cron.schedule('partman-maint','0 3 * * *',$$CALL partman.run_maintenance_proc()$$);
```

Benefits: cheap drop of old data (DETACH/DROP partition vs `DELETE`), partition pruning, smaller indexes per partition, parallel vacuum.

---

## 7. Audit Logging Design

- **Append-only**, partitioned monthly, never `UPDATE`d.
- Written via a single helper `audit(action, entity, before, after)` invoked in the service layer (preferred over DB triggers for rich context like `request_id`, AI actor). Optional DB-trigger fallback for tables changed outside the app.
- `before`/`after` store **PII-redacted** JSONB (phone/email/name masked) — analytics-safe.
- Correlated with distributed traces via `request_id`.

```sql
-- Trigger fallback example (generic row diff)
CREATE OR REPLACE FUNCTION fn_audit_row() RETURNS trigger AS $$
BEGIN
  INSERT INTO audit_logs(actor_type, action, entity_type, entity_id, before, after)
  VALUES (
    'system',
    TG_OP,
    TG_TABLE_NAME,
    COALESCE(NEW.id, OLD.id),
    CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END,
    CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END
  );
  RETURN COALESCE(NEW, OLD);
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_appointments
  AFTER INSERT OR UPDATE OR DELETE ON appointments
  FOR EACH ROW EXECUTE FUNCTION fn_audit_row();
```

---

## 8. Soft Deletes

- Convention: `deleted_at TIMESTAMPTZ NULL` on user-facing entities (`users, doctors, clinics, appointments, reviews, ai_conversations, voice_transcripts`).
- **All app reads go through repository methods** that auto-append `deleted_at IS NULL`, or through filtered views:

```sql
CREATE VIEW v_active_doctors AS
  SELECT * FROM doctors WHERE deleted_at IS NULL;
```

- Unique constraints must be **partial** to allow value reuse after deletion (see `uq_users_phone_active`).
- Hard-delete pipeline (DPDP "right to erasure"): a Temporal workflow anonymizes (`full_name='[redacted]'`, null phone/email), purges `voice_transcripts.audio_url`, then crypto-shreds. `audit_logs` retains a tamper-evident, PII-free record of the erasure event itself.

---

## 9. Multi-Tenant (Clinics) Considerations

**Model:** shared-DB, shared-schema, `clinic_id` tenant key + **Row-Level Security**.

```sql
-- Enable RLS and scope by session-set tenant
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_appt ON appointments
  USING (
    clinic_id = current_setting('app.current_clinic_id', true)::uuid
    OR current_setting('app.role', true) IN ('ops','superadmin')
  );

-- App sets per-request (inside transaction):
--   SET LOCAL app.current_clinic_id = '...';
--   SET LOCAL app.role = 'clinic_admin';
```

Guidelines:

- Every tenant-owned table carries `clinic_id` (appointments, reviews, payments, doctors, ai_conversations, subscriptions).
- B2C/patient-owned data (a patient who books across many clinics) is **not** tenant-scoped to one clinic; patient identity (`users`) is global. RLS policies differ: patient sees own rows; clinic sees rows where `clinic_id` matches.
- Indexes lead with `clinic_id` for tenant-local queries (`idx_appt_clinic_status`).
- Noisy-neighbor / large enterprise: promote a chain to a **dedicated schema** (or DB) via the same migration set; routing by `clinics.slug`.
- Connection pooling (PgBouncer) — use `SET LOCAL` (txn-scoped) so tenant context never leaks across pooled sessions.

---

## 10. Operational Notes

- **Redis usage:** OTP store (TTL), slot cache (`slots:{doctor}:{date}`), rate limits (`rl:{phone}`), realtime voice session FSM scratch, idempotency keys for booking. Source-of-truth stays in PG.
- **Migrations:** Alembic; one head; partitions created by pg_partman not Alembic.
- **Backups:** PITR (WAL archiving) + nightly base backup; audit_logs & payments excluded from any destructive test refresh.
- **`updated_at`:** trigger `BEFORE UPDATE` sets `now()` on all mutable tables.
```
