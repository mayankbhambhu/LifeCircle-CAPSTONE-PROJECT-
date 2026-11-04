# What LifeCircle does, and what it doesn't

## What the prototype does
- Calculates the next transfusion date from the patient's cycle.
- Pre-checks donor eligibility from recorded dates (90-day gap for men, 120 for women, deferrals, verification, ABO/Rh compatibility).
- Rotates the donor circle fairly and picks a confirmed donor and a backup.
- Promotes the backup when the confirmed donor cancels, and tells the family.
- Hands an uncovered date or an urgent need to the blood bank, alerts the circle first, then nearby eligible donors ranked by straight-line distance, and confirms the first to accept.
- Hides donor phone numbers from families and other donors, shows them only to staff, and logs every view.
- Lets staff record Donated / Deferred / No-show / Excused, which updates eligibility and the donor's record.

## What it does not do
- **Does not diagnose or give medical advice.**
- **Does not make the final eligibility decision.** Our check uses recorded dates only; haemoglobin, weight, illness, travel and medication screening happen at the blood bank.
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
- No account deletion or record-correction workflow yet (shown on the wireframe, not built).
