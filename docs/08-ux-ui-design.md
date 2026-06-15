# Phase 8 — UX / UI Design

> **DoctorFind** — an AI healthcare *navigator* for India. The UX must work for a **first-time smartphone user in a tier-3 town speaking Bhojpuri-accented Hindi over a 3G connection** *and* for a **clinic front-desk operator managing 80 appointments a day**. This document specifies flows, principles, screen-by-screen wireframes, and a design system that are **implementation-ready** against the canonical stack (Next.js web, React Native/Expo mobile).

**Audience:** Product Design, Frontend Eng (web + mobile), Content/Localization, Accessibility.
**Status:** Implementation-ready (v1).

---

## 0. Table of Contents

1. Design principles (mobile-first, voice-first, India-first)
2. Accessibility & low-literacy strategy
3. Multilingual / vernacular UX strategy
4. Trust-building UI system
5. Core flows (onboarding, symptom, discovery, booking, voice, clinic)
6. Screen-by-screen wireframes
7. Design system (color, type, tokens, components — web & mobile)
8. Content / microcopy guidelines
9. Handoff checklist

---

## 1. Design Principles

1. **Mobile-first, thumb-first.** Design for one-handed use on a 360–412 dp screen on a budget Android. Primary actions sit in the bottom 1/3 (thumb zone). Min tap target **48×48 dp**.
2. **Voice-first as a peer, not a fallback.** Every key flow (symptom, discovery, booking) is completable by voice. A persistent **mic** affordance is always one tap away.
3. **Conversation as the home base.** The AI navigator chat/voice is the spine; lists, profiles, and booking are *surfaces the conversation opens into*, not separate apps.
4. **Reduce, don't decorate.** Low cognitive load: one primary action per screen, progressive disclosure, plain language. Avoid jargon ("triage", "specialty taxonomy" → "What kind of doctor").
5. **Trust before transaction.** Verification, credentials, and disclaimers are visible at decision points, not buried.
6. **Safety is UI, not just backend.** Emergency override is a first-class screen state (red, full-bleed, unmissable).
7. **Tolerant & forgiving.** Works with messy input, code-mixed language, typos, and intermittent connectivity (optimistic UI, retry, offline state).
8. **Fast & light.** Performance budget: usable on 3G; lazy media; small bundles; skeleton states; cache last results.

---

## 2. Accessibility & Low-Literacy Strategy

- **Low-literacy / first-time users:**
  - **Icons + text always paired** (never icon-only for primary actions); consistent, literal icons.
  - **Voice in & voice out** on every screen (read-aloud toggle).
  - Short sentences, **active voice**, numerals over words ("2", not "two").
  - **Visual progress** (stepper dots) so users know where they are.
  - Symptom input via **tappable body map + symptom chips**, not only free text.
- **Touch & motor:** large targets (≥48 dp), generous spacing (≥8 dp between targets), no tiny close buttons, swipe + tap alternatives.
- **Vision / contrast:** WCAG **AA** minimum (4.5:1 text, 3:1 large text/UI), AAA for critical safety text. **Dynamic type** support (respect OS font scaling up to 200%). No color-only meaning (pair color with icon/label — esp. urgency).
- **Screen readers:** semantic roles, labels, focus order; `accessibilityLabel`/`accessibilityHint` (RN) and ARIA (web); live regions for AI streaming responses and for the **emergency banner** (`role="alert"`).
- **Motion:** respect reduce-motion; no essential info in animation alone.
- **Connectivity accessibility:** SMS/WhatsApp fallback so users on poor data still complete booking; IVR fully usable feature-phone-style (DTMF + voice).
- **Hit-area & forms:** numeric keypad for phone/OTP, autofill OTP, inline validation, error messages in plain language + the user's chosen language.

---

## 3. Multilingual / Vernacular UX Strategy

- **Language switching:**
  - Asked **first thing** at onboarding (big tappable list showing each language **in its own script**: हिन्दी, বাংলা, తెలుగు, தமிழ், English…).
  - Persistent **language pill** in the top bar to switch any time; switching is instant and non-destructive.
  - Auto-suggest from device locale but never force it.
- **Vernacular content:** UI strings, disclaimers, AI responses, doctor specialties, and notifications all localized (i18n keys; see Safety doc §2). Voice TTS uses the matching language/voice (ElevenLabs/Azure).
- **Code-mixing tolerance:** the navigator accepts **Hinglish / code-mixed** input ("doctor chahiye for bachcha ka fever") — no need to type in one language.
- **Transliteration & input:** support **Romanized → native script** input (type "bukhar" → understood). Offer transliteration keyboard hint; never block on script.
- **Display fallback:** if a doctor's name/specialty lacks a translation, show original + transliteration; never show empty.
- **Numerals & formats:** localized date/time, 12-hr clock with AM/PM in words where helpful, Indian numbering for fees (₹), local calendar awareness for holidays/clinic closures.
- **Right-sizing layouts:** text expansion (Hindi/Tamil can be longer) — flexible containers, no fixed-width buttons, test at longest-string.

---

## 4. Trust-Building UI System

Trust elements appear at **decision points** (discovery, profile, booking):

| Element | What it shows | Where |
|---|---|---|
| **Verified badge** ✔️ | NMC/State-council verification (with "Verified on <date>" on tap) | List card, profile header |
| **Credentials block** | Degrees, registration no., specialty, years of experience, languages spoken | Profile |
| **Ratings & reviews** | Aggregate star + count, recent verified-patient reviews, "verified visit" tag | Card + profile |
| **Photo & clinic photo** | Real doctor/clinic photo (or neutral placeholder, never fake stock implying a person) | Card + profile |
| **Transparency on fees & wait** | Consultation fee (₹), avg wait, slot availability "as of <time>" | Card + booking |
| **Safety disclaimer (L1/L2)** | "AI navigator, not medical advice" footer + inline | Every chat surface |
| **"Why this doctor?"** | Plain-language reason for the recommendation (specialty match, distance, availability) | Recommendation chips |
| **Secure/consent cues** | "Your details are encrypted", consent prompts before sharing with clinic | Booking |
| **Human help** | "Talk to a person" always available | Header/menu |

Anti-pattern guardrails: no fake urgency ("only 1 slot!" unless true), no dark patterns on consent, no hiding fees.

---

## 5. Core Flows

### 5.1 Onboarding
```
Splash → Language select → Value + safety (L0 disclaimer, accept)
   → Phone number → OTP verify → (optional) Name/age/gender, location permission
   → Home (navigator ready)
```
- Minimal: phone + OTP is the only hard requirement. Profile is **optional & deferrable**.
- L0 disclaimer accept is mandatory and logged (Safety §2).
- Skippable, voice-guided ("Tap the mic and tell me what's wrong").

### 5.2 Symptom input → triage (navigator)
```
Home → (type / speak / pick chip / body-map)
   → [Red-flag check runs first]
        ├─ RED  → Emergency override screen (112/108)
        └─ else → Clarifying Qs (1–3, plain) → Urgency + "What kind of doctor"
   → "Find {specialty} near you?" → Doctor list
```
- AI streams response; L2 disclaimer prefixed; recommendation explained ("Why this doctor").
- Never diagnoses; refusal-and-redirect for medical-advice asks (Safety §11).

### 5.3 Doctor discovery
```
Doctor list (sorted: relevance + distance + availability)
   → Filters (specialty, distance, fee, language, gender, availability today, video/in-person, verified-only)
   → Card tap → Doctor profile
```

### 5.4 Booking
```
Profile → "Book appointment" → Mode (in-person / video)
   → Date strip → Slot picker → Patient (self/other) → Reason (prefilled from chat)
   → Consent to share with clinic → Confirm → Payment (if any) → Confirmation
   → Add to calendar / reminders (SMS/WhatsApp) / directions
```

### 5.5 Voice interaction (app + IVR/WhatsApp-voice)
```
Tap mic / call number → Spoken disclaimer (first time) → "How can I help?"
   → User speaks → live transcript + barge-in → [red-flag check]
   → AI replies (voice + on-screen) → confirms specialty → reads top doctors
   → "Shall I book Dr X tomorrow 5 PM?" → user confirms → booking + SMS/WhatsApp confirmation
```
- Always-visible transcript, waveform, "tap to stop", and a **switch-to-typing** escape hatch.

### 5.6 Clinic dashboard (web, operator + doctor)
```
Login → Today view (queue) → Appointment detail / actions (confirm, reschedule, cancel, mark seen)
   → Calendar (week) → Patients → Availability/slot management → Profile & verification → Analytics
```

---

## 6. Screen-by-Screen Wireframes

> ASCII wireframes are **layout intent**, not pixel specs. `[ ]` = button, `( )` = input, `▣` = image, `★` = rating, `✔️` = verified, `▾` = dropdown. Mobile frames ~360 dp wide.

### 6.1 Home / Navigator (mobile)
```
┌──────────────────────────────┐
│ DoctorFind        हिन्दी ▾  ☰ │  ← language pill + menu (Talk to a person in menu)
├──────────────────────────────┤
│                              │
│   नमस्ते 👋                   │
│   मैं आपको सही डॉक्टर         │
│   ढूँढने में मदद करूँगा।       │
│                              │
│   What's bothering you?      │
│                              │
│   Common:                    │
│   [ Fever ] [ Cough ]        │  ← symptom chips (icon+text)
│   [ Stomach pain ] [ Skin ]  │
│   [ Child health ] [ More ▾] │
│                              │
│            ▣ body map         │  ← tap a body area
│           (tap where it hurts)│
│                              │
├──────────────────────────────┤
│ ( Type your symptom…       ) │  ← text input
│ [ 🎤  Speak ]   [ Send ➤ ]   │  ← BIG mic (thumb zone)
├──────────────────────────────┤
│ AI assistant — not medical   │  ← L1 footer (persistent)
│ advice. Emergency? 112 / 108 │
└──────────────────────────────┘
```

### 6.2 Symptom navigator — chat (mobile)
```
┌──────────────────────────────┐
│ ‹ Back        Navigator   🎤 │
├──────────────────────────────┤
│  ┌────────────────────────┐  │
│  │ You: 2 din se bukhar    │  │  ← user (code-mixed ok)
│  │ aur sir dard            │  │
│  └────────────────────────┘  │
│  ┌────────────────────────┐  │
│  │ AI: I can help you find │  │
│  │ the right doctor — I    │  │  ← L2 inline disclaimer
│  │ can't diagnose. A few   │  │
│  │ quick questions:        │  │
│  │ Since when the fever?   │  │
│  │ [ 1 day ][ 2-3 ][ 4+ ]  │  │  ← quick-reply chips
│  └────────────────────────┘  │
│  ┌────────────────────────┐  │
│  │ AI: A General Physician │  │
│  │ can assess this best.   │  │
│  │ Why: fever + headache,  │  │  ← "why this" transparency
│  │ no emergency signs.     │  │
│  │ [ Find doctors near me ]│  │  ← primary CTA
│  └────────────────────────┘  │
│         …streaming…           │
├──────────────────────────────┤
│ ( Type… )      [🎤]  [ ➤ ]    │
│ Not medical advice · 112/108 │
└──────────────────────────────┘
```

### 6.3 Voice mode (mobile, active call)
```
┌──────────────────────────────┐
│ ‹ End                 हिन्दी ▾│
├──────────────────────────────┤
│                              │
│         ◉ listening…         │
│      ∿∿∿∿  ∿∿∿∿  ∿∿∿        │  ← live waveform
│                              │
│  "do din se bukhar hai…"     │  ← live transcript (large)
│                              │
│  AI: "Samajh gaya. Kya saans │
│   lene me dikkat hai?"       │  ← AI reply (shown + spoken)
│                              │
│   [ ⏸ Tap to stop ]          │  ← big targets
│   [ ⌨ Type instead ]         │  ← escape hatch
│                              │
├──────────────────────────────┤
│   🔴 Emergency? Call 112/108  │
└──────────────────────────────┘
```

### 6.4 EMERGENCY OVERRIDE (red-flag) — full-bleed
```
┌══════════════════════════════┐   (RED background, role="alert")
║                              ║
║          ⚠  ⚠  ⚠            ║
║                              ║
║   यह एक मेडिकल इमरजेंसी       ║
║        हो सकती है            ║
║   This may be an emergency   ║
║                              ║
║   Call now:                  ║
║   ┌────────────────────────┐ ║
║   │   📞  CALL 112          │ ║  ← huge tel: buttons
║   └────────────────────────┘ ║
║   ┌────────────────────────┐ ║
║   │   📞  CALL 108 (Amb.)   │ ║
║   └────────────────────────┘ ║
║                              ║
║   [ Show nearest hospitals ] ║
║   Ask someone near you to    ║
║   call if you can't.         ║
║                              ║
└══════════════════════════════┘
```

### 6.5 Doctor list + filters (mobile)
```
┌──────────────────────────────┐
│ ‹  General Physicians   🗺 ▾ │  ← list/map toggle
├──────────────────────────────┤
│ [ Today ][ Video ][ ≤₹500 ]  │  ← quick filter chips (scrollable)
│ [ Filters ▾ ]   Sort: Best ▾ │
├──────────────────────────────┤
│ ┌──────────────────────────┐ │
│ │ ▣  Dr. Asha Rao  ✔️Verified│ │
│ │    General Physician      │ │
│ │    ★ 4.6 (320) · 12 yrs   │ │
│ │    🗣 Hindi, English       │ │
│ │    1.2 km · ₹400          │ │
│ │    🟢 Available today 5 PM │ │  ← color + text (not color-only)
│ │    [ View ]   [ Book ]    │ │
│ └──────────────────────────┘ │
│ ┌──────────────────────────┐ │
│ │ ▣  Dr. Imran Khan  ✔️     │ │
│ │    General Physician      │ │
│ │    ★ 4.4 (110) · 8 yrs    │ │
│ │    2.0 km · ₹300          │ │
│ │    🟡 Next: Tomorrow 11 AM │ │
│ │    [ View ]   [ Book ]    │ │
│ └──────────────────────────┘ │
│ Availability as of 4:32 PM   │  ← freshness
├──────────────────────────────┤
│ Not medical advice · 112/108 │
└──────────────────────────────┘
```
Filter sheet (bottom sheet): Specialty ▾ · Distance (slider) · Fee range · Language (multi) · Gender · Available today (toggle) · Mode (In-person/Video) · Verified only (toggle) · **[ Apply ] [ Reset ]**.

### 6.6 Doctor profile (mobile)
```
┌──────────────────────────────┐
│ ‹ Back                  ♡  ⇪ │
├──────────────────────────────┤
│   ▣ photo   Dr. Asha Rao ✔️  │
│             General Physician │
│             ★ 4.6 (320 reviews)│
│   MBBS, MD · Reg: KMC/12345   │  ← credentials + reg no.
│   ✔️ Verified (NMC) 2026-01    │  ← tap → verification detail
│   12 yrs exp · 🗣 Hindi, Eng   │
├──────────────────────────────┤
│  About                       │
│  Treats fever, infections,   │
│  diabetes, BP… (plain text)  │
├──────────────────────────────┤
│  Clinic   ▣ photo            │
│  Sunrise Clinic, Andheri     │
│  1.2 km · [ Directions 🗺 ]   │
│  Mon–Sat 10AM–8PM            │
├──────────────────────────────┤
│  Fees                        │
│  In-person ₹400 · Video ₹350 │
├──────────────────────────────┤
│  Reviews (verified visits)   │
│  ★★★★★ "Listened patiently…" │
│  ★★★★☆ "Short wait…"          │
├──────────────────────────────┤
│ [   Book appointment   ]     │  ← sticky primary (thumb zone)
└──────────────────────────────┘
```

### 6.7 Booking — slot picker (mobile)
```
┌──────────────────────────────┐
│ ‹  Book — Dr. Asha Rao       │
├──────────────────────────────┤
│  Mode:  [ In-person ] ( Video)│  ← segmented
│                              │
│  Mon  Tue  Wed  Thu  Fri     │  ← date strip (swipe)
│   15   16   17   18   19     │
│  [16]                        │  ← selected
│                              │
│  Morning                     │
│  ( 10:00 )(10:30)(11:00)     │  ← slot pills; disabled = greyed
│  Afternoon                   │
│  ( 2:00 )( 2:30 )( 3:00 )    │
│  Evening                     │
│  [ 5:00 ]( 5:30 )( 6:00 )    │  ← [ ] = selected
│                              │
│  Who is this for?            │
│  ( Myself ▾ )                │  ← self / add family member
│  Reason (optional)           │
│  ( Fever & headache 2 days ) │  ← prefilled from chat
│                              │
│ ☐ I agree to share these     │  ← consent (Safety §7)
│   details with the clinic    │
├──────────────────────────────┤
│ [   Confirm — ₹400   ]       │
└──────────────────────────────┘
```

### 6.8 Confirmation (mobile)
```
┌──────────────────────────────┐
│            ✅                  │
│   Appointment confirmed!     │
│                              │
│  Dr. Asha Rao ✔️             │
│  Tue, 16 Jun · 5:00 PM       │
│  In-person · Sunrise Clinic  │
│  Token/Ref: DF-48217         │
│  Paid ₹400                   │
│                              │
│  [ 🗺 Directions ]            │
│  [ 📅 Add to calendar ]      │
│  [ 🔔 Reminders: SMS+WhatsApp]│
│  [ ✖ Cancel / Reschedule ]   │
│                              │
│  We'll send a reminder 2 hrs │
│  before. Reply STOP to opt   │  ← DLT/WhatsApp opt-out cue
│  out of messages.            │
├──────────────────────────────┤
│ Not medical advice · 112/108 │
└──────────────────────────────┘
```

### 6.9 Clinic dashboard — Today view (web, desktop)
```
┌───────────────────────────────────────────────────────────────────┐
│ DoctorFind Clinic   Sunrise Clinic ▾      🔔   Dr. Asha Rao ▾  EN ▾ │
├───────────┬───────────────────────────────────────────────────────┤
│ ▦ Today   │  Today — Tue, 16 Jun        [+ New appointment] [⟳]    │
│ 📅 Calendar│  ┌───────────────────────────────────────────────────┐│
│ 👤 Patients│  │ Time   Patient        Reason       Mode   Status  ││
│ ⏱ Slots   │  ├───────────────────────────────────────────────────┤│
│ 📊 Reports │  │ 10:00  Ravi Kumar     Fever        In    🟢 Done  ││
│ ⚙ Profile │  │ 10:30  Sita Devi      Follow-up    Video ⚪ Waiting││
│ ✔️ Verify  │  │ 11:00  — (open)       —            —     ＋ Add   ││
│           │  │ 5:00   N. Sharma      Fever,h-ache  In    🟡 Conf. ││
│           │  │        [ Check-in ][ Reschedule ][ Cancel ][ ⋯ ]   ││
│           │  └───────────────────────────────────────────────────┘│
│           │  Queue: 6 waiting · Avg wait 18 min · No-shows today 1 ││
└───────────┴───────────────────────────────────────────────────────┘
```
Appointment detail (right drawer): patient name/phone (masked until check-in per consent), reason from chat, history of visits, actions (confirm/reschedule/cancel/mark seen, send message via approved template), notes. Doctor/PHI access is role-gated and audit-logged.

### 6.10 Clinic — Slot / availability management (web)
```
┌───────────────────────────────────────────────────────────────────┐
│ Availability — Dr. Asha Rao                         [ Save ]        │
├───────────────────────────────────────────────────────────────────┤
│ Weekly template:  Mon ▣  Tue ▣  Wed ▣  Thu ▣  Fri ▣  Sat ▣  Sun ☐ │
│ Hours: ( 10:00 )–( 13:00 ) , ( 17:00 )–( 20:00 )   Slot: (15 min)▾ │
│ Modes: ☑ In-person  ☑ Video    Per-slot capacity: (1)              │
│ Blackouts / leave: [ + Add date ]   16 Jun (half-day) ✕           │
│ Buffer between patients: (5 min)▾                                   │
└───────────────────────────────────────────────────────────────────┘
```

---

## 7. Design System

### 7.1 Brand & color (trust + accessibility)
Healthcare palette: calm, clean, trustworthy (medical teal/blue), warm accent for friendliness, strict semantic colors. **All pairs meet WCAG AA on their backgrounds.**

```
Primary    Teal/Blue  #0E7C86  (trust, calm, "medical")   on white = AA
Primary-dk            #0A5B63  (pressed / headers)
Accent     Warm       #F2994A  (friendly highlight, CTAs sparingly)
Success    Green      #1B873F  🟢 available / done
Warning    Amber      #B25E00  🟡 urgent / limited
Danger     Red        #C62828  🔴 EMERGENCY (reserved — only for safety)
Neutral    Ink        #1A2330  (primary text, ~15:1 on white)
Neutral    Slate      #5B6675  (secondary text, AA)
Surface    #FFFFFF / #F6F8FA (bg) / Border #E2E8F0
Dark mode  tokens mirrored with adjusted contrast
```
- **Red is reserved for emergencies** — never used for normal CTAs, to keep the emergency signal unambiguous.
- Never encode meaning in color alone (pair with icon/label).

### 7.2 Typography
- **Web:** `Inter` (Latin) + **`Noto Sans`** family for Indic scripts (Devanagari, Bengali, Telugu, Tamil, etc.) — Noto guarantees consistent multi-script rendering. System fallback stack.
- **Mobile:** Inter / system + Noto Sans Indic bundled (Expo font assets).
- **Scale (mobile, 1.25 ratio, respects OS scaling):** Display 28 / H1 24 / H2 20 / Body-L 17 / Body 15 / Caption 13. Min body **15 sp**; never below 12.
- **Weights:** 400/500/600/700. Generous line-height (1.4–1.6) for Indic legibility. Avoid all-caps for Indic text.

### 7.3 Spacing, radius, elevation (tokens)
```
space: 4 / 8 / 12 / 16 / 24 / 32 (8-pt base)
radius: sm 8 · md 12 · lg 16 · pill 999
elevation: card (subtle), sheet, modal; respect reduce-motion
tap target: min 48×48; spacing between targets ≥ 8
```

### 7.4 Design tokens (shared source of truth)
Tokens live in a platform-agnostic JSON (`/design/tokens.json`) consumed by Tailwind (web) and a JS theme (mobile). Example:
```json
{
  "color": {
    "primary":   { "value": "#0E7C86" },
    "danger":    { "value": "#C62828" },
    "success":   { "value": "#1B873F" },
    "warning":   { "value": "#B25E00" },
    "ink":       { "value": "#1A2330" },
    "surface":   { "value": "#FFFFFF" }
  },
  "radius": { "md": 12, "pill": 999 },
  "space":  { "sm": 8, "md": 16, "lg": 24 },
  "font":   { "body": 15, "h1": 24, "lineHeight": 1.5 },
  "target": { "min": 48 }
}
```

### 7.5 Component libraries
- **Web (Next.js):** **shadcn/ui + Tailwind CSS** + Radix primitives (accessible by default). Map design tokens → Tailwind theme. Use Radix Dialog for emergency modal (with `role="alert"` override), Combobox for filters, Tabs for clinic nav.
- **Mobile (React Native / Expo):** **NativeWind** (Tailwind for RN) for token parity with web, optionally **React Native Paper** for Material-grade accessible components (large targets, dynamic type, screen-reader support out of the box). Choose one as primary (recommend **NativeWind + a small custom component kit** for token parity; Paper where you want batteries-included a11y).
- **Shared:** Lucide icons (consistent across web/mobile), one icon set only.

### 7.6 Key shared components (spec)
- `DisclaimerBanner` (L1 footer), `DisclaimerInline` (L2), `EmergencyOverlay` (L3, role=alert, focus-trap, tel: deep links).
- `MicButton` (states: idle/listening/processing; large; haptic feedback).
- `SymptomChip`, `BodyMap`, `QuickReplyChips`.
- `DoctorCard` (image, name, ✔️ badge, specialty, ★rating, distance, fee, availability tag, View/Book).
- `VerifiedBadge` (tap → verification provenance).
- `SlotPicker` (date strip + slot pills, disabled/selected states).
- `LanguagePill` (script-native labels).
- `ConsentCheckbox` (links to policy, logs consent).
- Clinic: `AppointmentRow`, `QueueSummary`, `AvailabilityEditor`.

### 7.7 States to design for every screen
Loading (skeleton) · Empty ("No doctors match — widen filters?") · Error + retry · Offline (cached + "you're offline") · No-permission (location/mic) · Slow network (progressive) · RTL-safe layouts for future Urdu.

---

## 8. Content / Microcopy Guidelines

- **Plain, warm, non-alarming** (except emergency, which is direct). Reading level ~grade 5.
- Never imply diagnosis ("you might have…" is banned in UI copy; use "a doctor can check this").
- Always offer the next safe action ("Find a doctor", "Talk to a person").
- Localize *meaning*, not literal strings; review by native speakers; test longest strings.
- Buttons are verbs ("Book", "Find doctors", "Call 112"), not nouns.
- Error copy: say what happened + what to do, in the user's language.

---

## 9. Handoff Checklist

- [ ] Tokens (`tokens.json`) wired into Tailwind (web) + RN theme (mobile); single source of truth.
- [ ] All primary CTAs in thumb zone, ≥48 dp, icon+text.
- [ ] Voice path completable for symptom → discovery → booking; mic always reachable; type escape hatch.
- [ ] Emergency overlay implemented as `role="alert"`, focus-trapped, tel:112/108, full-bleed red (red reserved).
- [ ] L1 footer + L2 inline disclaimers on every chat surface; L0 at onboarding.
- [ ] Language pill (script-native) + full localization incl. AI responses, TTS voices, notifications.
- [ ] Transliteration / Hinglish input accepted; longest-string layouts verified.
- [ ] Trust elements (✔️ verified + date, credentials, reg no., reviews, fees, freshness) at decision points.
- [ ] WCAG AA contrast; dynamic type to 200%; screen-reader labels; reduce-motion; color never sole signal.
- [ ] All screen states (loading/empty/error/offline/no-permission) designed.
- [ ] Consent checkbox before clinic data share; opt-out cue on messages.
- [ ] Clinic dashboard: queue, appointment actions, availability editor, role-gated/masked PHI.
- [ ] Performance budget validated on 3G / budget Android; skeletons + caching.
