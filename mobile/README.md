# EHS Mall mobile

Expo SDK 57 read-only catalogue client for Android, tablets, and web. The visual theme and
`com.example.ehsmall` Android identifier are provisional; final branding, logo, icon, splash,
package name, and store metadata require approval before release.

## Local development

1. Copy `.env.example` to `.env` without committing it.
2. Set `EXPO_PUBLIC_API_BASE_URL` to `http://10.0.2.2:8000` for the Android emulator, or
   `http://YOUR_COMPUTER_LAN_IP:8000` for a physical phone on the same Wi-Fi.
3. Run `npm install` and then `npx expo start` from `mobile`.
4. Open the project in Expo Go. Do not use a production API for local development.

Deployed builds require an HTTPS API base URL. The client calls only the five public GET
catalogue endpoints. Saved listings contain public UUIDs only; listing details are always
refetched. Contact values are intentionally unavailable pending policy and consent review.

Useful checks: `npm run typecheck`, `npm run lint`, `npm test`, `npx expo-doctor`, and
`npm run export:web`. EAS, signing, cloud projects, publishing, and store builds are not
configured in this phase.
