# Milestone 2 · Network / endpoint requests

All endpoints are live in the prototype. Open `http://127.0.0.1:8000/docs` for interactive Swagger docs.
Every call except sign-in sends `Authorization: Bearer <token>`. Calling another role's endpoint returns **403**.

User stories referenced below are from the Milestone 1 deck: F = family, D = donor, S = staff.

## Auth
| CRUD | Verb | Endpoint | Description | Stories |
|---|---|---|---|---|
| Create | POST | `/auth/login` | phone + OTP sign-in, returns token (demo OTP `1234`) | D1 |
| Read | GET | `/auth/me` | who am I, which role | all |

## Patient family
| CRUD | Verb | Endpoint | Description | Stories |
|---|---|---|---|---|
| Read | GET | `/family/home` | next date, confirmed + backup, circle, circle health, open requests | F2 |
| Read | GET | `/family/plan` | blood group, cycle, last transfusion, next date | F1 |
| Update | PUT | `/family/plan` | save plan, recalculates the date and re-runs rotation | F1 |
| Create | POST | `/family/urgent` | "Request urgent help", goes to the blood bank, not donors | F3 |
| Read | GET | `/family/requests/{id}` | live request status timeline | F4 |
| Read | GET | `/family/notifications` | plan changes, backup promotion, etc. | F4 |

## Donor
| CRUD | Verb | Endpoint | Description | Stories |
|---|---|---|---|---|
| Read | GET | `/donor/home` | upcoming donations, eligibility, rotation turn | D2 |
| Update | POST | `/donor/appointments/{id}/confirm` | "Yes, I'll come" | D2 |
| Update | POST | `/donor/appointments/{id}/cancel` | "I can't make it" (no penalty), promotes backup | D3 |
| Read | GET | `/donor/alerts` | urgent alerts near me ("2.4 km from you") | D3 |
| Update | POST | `/donor/alerts/{id}/accept` | first to accept is confirmed; later ones get 409 | D3 |
| Update | POST | `/donor/alerts/{id}/decline` | "Not today" | D3 |
| Read / Update | GET / PUT | `/donor/privacy` | three sharing toggles | D4 |
| Read | GET | `/donor/record` | "showed up 4 of 5" + history | D3 |
| Read | GET | `/donor/notifications` | reminders and alerts | D2 |

## Blood bank staff
| CRUD | Verb | Endpoint | Description | Stories |
|---|---|---|---|---|
| Read | GET | `/staff/queue` | request queue with one suggested action each | S1 |
| Update | POST | `/staff/requests/{id}/approve` | approve, alerts the patient's circle | S1 |
| Update | POST | `/staff/requests/{id}/escalate` | alert nearby eligible donors now (auto after 15 min) | S3 |
| Read | GET | `/staff/requests/{id}/candidates` | circle first, then nearby, ranked by distance, with phone (logged) | S3 |
| Update | POST | `/staff/requests/{id}/confirm` | confirm a donor after phoning them | S3 |
| Read | GET | `/staff/donors` | all donors with phone, verification, eligibility (logged) | S2 |
| Update | POST | `/staff/donors/{id}/verify` | give the verified badge | S2 |
| Read | GET | `/staff/today` | today's expected donors | S4 |
| Create | POST | `/staff/outcomes` | record Donated / Deferred / No-show / Excused | S4 |
| Read | GET | `/staff/audit/phone-views` | who saw which phone number, when | S2 |

## Demo only
| Verb | Endpoint | Description |
|---|---|---|
| GET | `/demo/accounts` | seeded accounts for the login screen (no phone numbers) |
| POST | `/demo/login/{user_id}` | one-click sign-in |
| POST | `/demo/reset` | wipe and re-seed |
| POST | `/demo/advance` | move the clock (`{"minutes": 15}` to trigger escalation) |
| GET | `/demo/clock` | current demo time |

## Network request outline (by screen)
- **Family home**: GET `/family/home` · POST `/family/urgent`
- **Family plan**: GET `/family/plan` · PUT `/family/plan`
- **Request status**: GET `/family/requests/{id}`
- **Donor home**: GET `/donor/home` · POST `/donor/appointments/{id}/confirm` or `/cancel`
- **Donor urgent alert**: GET `/donor/alerts` · POST `/donor/alerts/{id}/accept` or `/decline`
- **Donor privacy and record**: GET/PUT `/donor/privacy` · GET `/donor/record`
- **Staff request queue**: GET `/staff/queue` · POST `/staff/requests/{id}/approve` or `/escalate`
- **Staff choose a donor**: GET `/staff/requests/{id}/candidates` · POST `/staff/requests/{id}/confirm`
- **Staff today**: GET `/staff/today` · POST `/staff/outcomes`
