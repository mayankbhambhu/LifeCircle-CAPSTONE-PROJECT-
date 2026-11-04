# Demo script (about 4 minutes)

Start: `uvicorn app.main:app` and open http://127.0.0.1:8000. Press **Reset demo** first.
For numbers that match the wireframes exactly, start with `LIFECIRCLE_TODAY=2026-11-03`.

1. **Family home** (sign in as *Rohan Mehta*). "Next transfusion 12 Nov, in 9 days. Confirmed Amit, backup Priya." Point out the faded circle members: they gave recently, so fair rotation skips them.
2. **Donor cancels** (sign in as *Amit Tiwari*). Tap *I can't make it*. The toast shows "Priya promoted from backup to confirmed".
3. **Family sees the change** (*Rohan Mehta*). Confirmed is now Priya; the Updates tab has the message. No phone numbers anywhere.
4. **Urgent request.** Tap *Request urgent help*. It goes to the blood bank, not to donors.
5. **Staff approves** (*R. Kumar*). Queue shows the suggested action. Approve: the two eligible circle donors are alerted.
6. **Nobody answers.** Press **+15 min** in the demo bar. The request escalates to nearby donors. Open *Choose a donor*: circle first, then nearby ranked by distance, phone numbers marked staff-only. The *Log* tab shows each phone view was recorded.
7. **Donor accepts** (*Ishaan Gupta*). "2.4 km from you", patient name hidden. Tap *Accept*. Anyone accepting after him gets "already filled".
8. **Staff records outcome** (*R. Kumar*, *Today* tab). Mark *Donated*. Ishaan's eligibility clock restarts.
9. Close on the "what this doesn't do" slide ([SCOPE.md](SCOPE.md)).
