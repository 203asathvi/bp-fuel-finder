// BP Fuel Finder — Firebase Config
// ─────────────────────────────────────────────────────────────────────────
// This file is listed in .gitignore — NEVER committed to GitHub.
// Place this file in the same folder as index.html on each device.
//
// SETUP:
// 1. Go to Firebase Console → your existing project
// 2. Add a Realtime Database (if not already):
//    Build → Realtime Database → Create Database → Start in test mode
// 3. Copy your database URL (e.g. https://your-app-default-rtdb.firebaseio.com)
// 4. Paste it below, save this file, upload to GitHub repo
//
// SECURITY: Set Realtime Database rules to allow read/write only from
// your GitHub Pages domain (optional but recommended):
// {
//   "rules": {
//     "geocache": { ".read": true, ".write": true }
//   }
// }
// ─────────────────────────────────────────────────────────────────────────

window.BPFF_CONFIG = {
  FIREBASE_DB_URL: 'https://bp-fuel-tracker-default-rtdb.firebaseio.com',
  SERVO_SAVER_KEY: 'f6a1f76f7e6ef46bd3ef4a5bcc23902b',
};
