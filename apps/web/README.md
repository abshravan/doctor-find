# DoctorFind Web (Next.js) — Scaffold Placeholder

The web app is a **Next.js (App Router)** project — chosen for SEO on doctor/specialty
discovery pages (organic acquisition is a core GTM loop, see `docs/10-go-to-market.md`).

## Planned structure
```
web/
├── app/
│   ├── (marketing)/          # SEO landing + specialty/city pages (SSG/ISR)
│   ├── search/               # doctor discovery + filters
│   ├── doctor/[slug]/        # verified profile + booking
│   ├── triage/               # AI Symptom Navigator (chat + voice)
│   └── dashboard/            # clinic dashboard (RBAC-gated)
├── components/ui/            # shadcn/ui + Tailwind design system
├── lib/api.ts                # typed API client (shared contracts)
└── i18n/                     # multilingual (en, hi, + regional)
```

## Bootstrap
```bash
npx create-next-app@latest web --ts --tailwind --app
```

State: TanStack Query (server state) + Zustand (UI state). See `docs/08-ux-ui-design.md`
for screens/wireframes and `docs/12-engineering-outputs.md` for frontend architecture.
