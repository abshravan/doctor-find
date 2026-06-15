# DoctorFind Mobile (React Native / Expo) — Scaffold Placeholder

Mobile is the **primary** surface for patients (mobile-first, voice-first). Built with
**React Native + Expo** for one codebase, OTA updates, and fast iteration.

## Planned structure
```
mobile/
├── app/                      # expo-router (file-based)
│   ├── (tabs)/               # home, search, bookings, profile
│   ├── triage/               # voice-first AI Symptom Navigator
│   └── doctor/[id].tsx
├── components/               # NativeWind + RN Paper design system
├── lib/voice/                # mic capture -> STT stream, TTS playback
├── lib/api.ts                # typed API client
└── i18n/                     # multilingual
```

## Bootstrap
```bash
npx create-expo-app@latest mobile -t
```

Offline support: cache discovery results + draft bookings (MMKV/SQLite), sync on
reconnect. See `docs/08-ux-ui-design.md` and `docs/12-engineering-outputs.md`.
