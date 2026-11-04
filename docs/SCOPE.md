# What LifeCircle does, and what it doesn't

## What the prototype does
- Calculates the next transfusion date from the patient's cycle.
- Pre-checks donor eligibility using the Government of India NBTC donor selection guidelines (2017) where they can be checked from records: age 18 to 65 (first-time donors not over 60), weight at least 45 kg, 90-day gap for men and 120 for women, plus staff deferrals, blood bank verification and ABO/Rh compatibility.
- Rotates the donor circle fairly and picks a confirmed donor and a backup.
- Promotes the backup when the confirmed donor cancels, and tells the family.
- Hands an uncovered date or an urgent need to the blood bank, alerts the circle first, then nearby eligible donors ranked by straight-line distance, and confirms the first to accept.
- Hides donor phone numbers from families and other donors, shows them only to staff, and logs every view.
- Lets staff record Donated / Deferred / No-show / Excused, which updates eligibility and the donor's record.

## What it does not do
- **Does not diagnose or give medical advice.**
- **Does not make the final eligibility decision.** Our check uses recorded data only; haemoglobin (at least 12.5 g/dL), blood pressure, pulse, temperature, illness, travel and medication screening happen at the blood bank on the day.
- **Does not do cross-matching or replace compatibility testing.** Blood-group matching in the app is a pre-filter.
- **Does not guarantee a donor or a blood supply.**
- **Does not manage blood bank inventory** or component separation (packed red cells, platelets).
- **Does not send real SMS or push notifications.** Messages are stored and shown in the app, marked `[DEMO]`.
- **Does not use real OTP.** The demo code is always `1234`.
- **Does not use road distance or travel time.** Distance is straight-line (haversine) from the blood bank.
- **Does not connect to a real blood bank system** (e-RaktKosh or a hospital system). All data is seeded and fictional.
- **Does not handle payments, incentives, or donor-to-family chat.** Families never contact donors directly.

## Known prototype limits
- SQLite, one server process; the "first to accept wins" rule uses an atomic database update, but there is no real-time push (screens refresh on action).
- The 15-minute escalation runs when a request is read, not on a background timer.
- Donors can delete their account (name and phone erased, past outcomes kept for the blood bank), but there is no "ask staff to fix a record" workflow yet.
- On the live GitHub Pages demo, data lives only in your browser tab and resets when you reload.
