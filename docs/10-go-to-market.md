# Phase 10 — Go-To-Market (India)

> How DoctorFind wins its first 100 clinics and first 10,000 patients. India-specific, channel-by-channel, week-by-week.

---

## 10.1 GTM thesis

Healthcare discovery is **hyper-local and trust-driven**. You don't win India top-down with a national app; you win **one neighborhood/specialty cluster at a time** until you have enough supply density that consumer demand has somewhere to go. We solve the cold-start by leading **supply-first with a paid product that delivers value with zero patients on day one** — the AI receptionist works for a clinic even if DoctorFind has no consumer traffic. That breaks the chicken-and-egg: clinics pay for labour savings, not for leads we can't yet deliver.

**One-line GTM:** *Sell the AI receptionist to clinics in one dense micro-market, accumulate booking + catalog data, then turn on consumer discovery where supply is already liquid.*

---

## 10.2 First-city & niche wedge

### City choice: **Bengaluru** (or Pune/Hyderabad as alternates)
Rationale: high smartphone + WhatsApp penetration, English+Kannada+Hindi mix (tests multilingual early), dense clinic clusters (Indiranagar, Koramangala, HSR, Jayanagar, Whitefield), tech-comfortable doctors, strong word-of-mouth among clinic owners, and you can do feet-on-street within a 10 km radius.

### Niche wedge: **Pediatrics + high-call-volume specialties first**
Start where the front desk is most overwhelmed and bookings are most repetitive:
1. **Pediatricians** — anxious parents, after-hours calls, vaccination schedules (perfect for AI reminders), high repeat.
2. **Dentists** — appointment-driven, no-show heavy (no-show recovery is an instant ROI demo).
3. **Dermatologists / IVF / physiotherapy** — high-value, appointment-led, marketing-savyy owners.

Avoid GP/family-medicine first (walk-in driven, lower software willingness). Win one specialty cluster, become "the thing every pediatrician in Koramangala uses," then expand specialty-by-specialty.

---

## 10.3 Solving the cold-start (chicken-and-egg)

| Side | The trap | Our break |
|---|---|---|
| **Supply (doctors)** | "Why list if no patients?" | Don't sell listings. Sell the **AI receptionist** — value is labour saving + recovered missed calls from the clinic's *own* existing patients. Zero DoctorFind traffic required. |
| **Demand (patients)** | "Why use the app if no doctors?" | Don't launch consumer discovery until a micro-market has 30–50 clinics live. First patient touchpoint is **through the clinic's own channel** (their WhatsApp/phone now powered by us) — we ride existing patient flow. |

**Sequence:** (1) Sign clinics → (2) their patients experience our AI on the clinic's number → (3) those patients get a DoctorFind health profile + see other clinics → (4) consumer-side discovery flips on once density exists. The clinic's existing patients seed the consumer base for free.

---

## 10.4 Acquiring the first doctors/clinics

### Feet-on-street (primary, month 0–6)
- **Target list:** scrape Google Maps / Practo / JustDial for the chosen specialty + pincodes; build a 300-clinic hit-list with phone, address, owner name, current software (if any), Google rating, review complaints about "couldn't reach / no response."
- **The demo that closes:** call the clinic's *own* number live in front of the owner using our AI, book a fake appointment, show the WhatsApp confirmation. Then show the "missed calls last month" estimate. Visceral, 5-minute close.
- **BD motion:** 1–2 BD reps, 8–10 in-person visits/day, target 20–30% demo→trial. Founder does first 20 closes personally (founder-led sales until the script is repeatable).
- **Pricing entry:** free 14-day trial → ₹1,999 Starter, upsell to Pro after they see voice value. First 20 clinics: heavy discount / design-partner pricing in exchange for testimonials + feedback.
- **Onboarding:** port/forward their number, ingest doctor list + timings + fees into catalog, configure WhatsApp via Gupshup, train AI on their FAQs. Target <48h to live. Have a same-day onboarding checklist; a clinic that isn't live in 2 days churns mentally.

### Self-serve (layer in month 4+)
- Landing page with "Try the AI receptionist on your clinic in 10 minutes" — self signup, WhatsApp QR onboarding, guided catalog import. Reduces CAC for warm/inbound clinics. Keep feet-on-street for cold.

### Trust-building with doctors (critical in India)
- **Local references** — "Dr. X in your area uses us" is the single strongest lever. Cluster-by-cluster so references compound.
- **Doctor association tie-ins** — IMA local chapters, IAP (pediatrics), IDA (dental) — sponsor a CME/meetup, get on the WhatsApp group.
- **Founder credibility** — be present, in person, in the clinic. Indian doctors trust people, not webforms.

---

## 10.5 Acquiring the first patients

Phase 1 (months 0–6): **don't run consumer acquisition.** Patients arrive *through partner clinics* — every clinic patient interacting with our AI gets a DoctorFind identity + health record offer. This is the cheapest, highest-trust acquisition channel (the patient already trusts their doctor).

Phase 2 (month 6+, where density exists):
- **WhatsApp-first entry** — "Find a doctor" WhatsApp number / click-to-chat ads. Conversational discovery in the user's language. No app install friction.
- **Local SEO / Google** — "pediatrician near me Koramangala" etc.
- **Referral loop** — patient gets ₹100 health-wallet credit / family member booking benefit for referring; clinics love it (more bookings).
- **Trust signals** — verified doctors, real reviews collected post-visit via our own WhatsApp follow-up (we own the review collection moment, unlike Practo).

---

## 10.6 Growth loops

1. **Supply density loop:** more clinics in a cluster → richer discovery → more patient engagement → testimonials & referrals → easier to sign next clinic in same cluster.
2. **Content/data loop:** every triage + booking enriches the catalog & symptom→specialty mapping → better triage quality → better outcomes → word of mouth.
3. **Review loop:** we collect post-visit reviews via WhatsApp → clinics get reputation value → clinics promote DoctorFind to patients → more reviews.
4. **No-show recovery loop:** AI fills cancelled slots from a waitlist → clinic revenue up → clinic advocates → referrals.

---

## 10.7 WhatsApp marketing (India-native)

- **Click-to-WhatsApp ads** (Meta) — cheapest high-intent channel in India for health; land directly in the triage bot. Track cost-per-qualified-booking.
- **Utility templates** for confirmations/reminders (cheap, high open rate ~95%+).
- **Service window** for triage (free, user-initiated) — keep conversations user-initiated to avoid marketing message costs.
- **Broadcast discipline** — marketing templates only for reactivation; over-messaging gets numbers blocked by Meta. Maintain quality rating.
- **Regional language templates** — Kannada/Hindi/Tamil from day one; auto-detect and switch.

---

## 10.8 SEO & local SEO

- **Programmatic local pages:** "Best [specialty] in [locality], [city]" — one page per specialty×locality, populated from live verified catalog (only where we have density, to avoid thin/empty pages).
- **Google Business Profile** assistance for partner clinics (we manage it as a value-add → ties them deeper to us + improves their discoverability + our backlinks).
- **Health content hub:** symptom guides, "when to see a [specialist]", vaccination schedules — feeds top-of-funnel + supports triage credibility. Strictly informational, with medical disclaimers.
- **Schema markup** (MedicalClinic, Physician, FAQ) for rich results.

---

## 10.9 Referral systems

- **Clinic→clinic:** refer another clinic → 1 month free / ₹2,000 credit each. Doctors talk to doctors; this is high-yield.
- **Patient→patient:** ₹100 wallet credit on referred friend's first booking.
- **Patient→clinic seeding:** patients can "invite my other doctor to DoctorFind" — turns demand into supply leads.

---

## 10.10 Week-by-week launch motion (first 12 weeks, Bengaluru, pediatrics wedge)

| Week | Focus | Concrete actions | Target metric |
|---|---|---|---|
| **0 (pre)** | Setup | Hit-list of 300 pediatric/dental clinics; Gupshup + Exotel accounts live; demo flow rock-solid; onboarding checklist | Demo works end-to-end on a real number |
| **1** | Founder sales | Founder visits 30 clinics, live demos | 5 design-partner trials signed |
| **2** | Onboard | Get all trials live <48h; daily check-ins; collect FAQs | 5 clinics live, first AI-handled real call |
| **3** | Iterate | Fix triage/voice issues from real calls; first testimonial video | 8 trials, 1 converts to paid |
| **4** | First paid cohort | Convert trials; refine pricing objection script | 10 live, 4 paying |
| **5** | Hire BD #1 | Onboard first BD rep on the proven script; ride-alongs | BD doing solo demos |
| **6** | Cluster density | Concentrate on Koramangala+HSR; use references | 20 live clinics in 2 localities |
| **7** | No-show recovery launch | Turn on waitlist auto-fill; quantify recovered revenue per clinic | ROI dashboard live |
| **8** | Reviews loop | Post-visit WhatsApp review collection | First 100 verified reviews |
| **9** | Second specialty | Add dentists in same localities | 30 clinics, 2 specialties |
| **10** | Self-serve beta | Launch self-signup landing + WhatsApp QR onboarding | First self-serve clinic live |
| **11** | Consumer pilot | In dense localities, flip on patient discovery via clinic channels | First cross-clinic discovery booking |
| **12** | Review & double down | Cohort retention analysis; lock the playbook | 40 paying clinics, <8% monthly churn, NPS baseline |

---

## 10.11 GTM KPIs to watch
- Demo→trial→paid conversion (each step).
- Time-to-live (signup → first real AI-handled call); target <48h.
- Clinics per locality (density is the moat).
- Recovered missed-call value per clinic (the ROI story).
- Monthly clinic churn (target <5%).
- Cross-clinic consumer bookings (signal that demand side is waking up).
- WhatsApp quality rating (must stay High).

---

## 10.12 What NOT to do early
- Don't go multi-city before one cluster is dense and retaining.
- Don't sell premium listings before consumer traffic exists (kills trust).
- Don't promise diagnosis/medical advice — navigation + triage only.
- Don't chase hospitals first (9-month sales cycles will starve the company).
- Don't run consumer ads into an empty marketplace.
