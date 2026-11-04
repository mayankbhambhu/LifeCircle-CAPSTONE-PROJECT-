# Milestone 2 · Data models

LifeCircle has 11 objects. The code is in [`app/models.py`](../app/models.py) (SQLAlchemy, SQLite for the prototype; the same schema runs on PostgreSQL).

```
User ──1:1── Donor ──< CircleMember >── Patient ──> BloodBank
                │                          │
                ├──< Appointment >─────────┤        (planned mode)
                ├──< RequestAlert >── DonationRequest   (urgent mode)
                ├──< DonationRecord                  (staff outcomes)
                └──< PhoneViewLog  (staff audit)
User ──< Notification, AuthSession
```

### User
| Property | Type | Description |
|---|---|---|
| id | int | primary key |
| name | string | full name (only staff and the person themselves see the full name) |
| phone | string, unique | sign-in identity; **visible to staff only** |
| role | enum `family` / `donor` / `staff` | decides which screens and endpoints the user can reach |
| blood_bank_id | FK → BloodBank | staff only: which bank they work for |

### AuthSession
| Property | Type | Description |
|---|---|---|
| token | string | bearer token issued after phone + OTP sign-in |
| user_id | FK → User | |
| created_at | datetime | |

### BloodBank
| Property | Type | Description |
|---|---|---|
| id, name | | e.g. "District Blood Bank" |
| lat, lng | float | used as the centre point for urgent-mode distance ranking |

### Patient
| Property | Type | Description |
|---|---|---|
| id, name | | e.g. Aarav |
| blood_group | string | A+ … AB- |
| cycle_days | int | transfusion every N days (e.g. 21) |
| last_transfusion_date | date | next date = last + cycle |
| family_user_id | FK → User | the family account that manages this patient |
| blood_bank_id | FK → BloodBank | where transfusions happen |

### Donor
| Property | Type | Description |
|---|---|---|
| id, user_id | FK → User | |
| blood_group, sex | | sex sets the minimum donation gap (90 / 120 days) |
| lat, lng | float | home location, used only if the donor allows it |
| last_donation_date | date | drives eligibility |
| deferred_until | date | set when staff record "Deferred" |
| verified | bool | blood bank verified badge; only verified donors are matched |
| show_next_eligible_to_staff | bool | privacy toggle |
| share_location_for_urgent | bool | privacy toggle |
| urgent_alerts_enabled | bool | privacy toggle |

### CircleMember
| Property | Type | Description |
|---|---|---|
| patient_id, donor_id | FK | a donor in a patient's fixed donor circle (a donor can be in several circles) |
| joined_on | date | |

### Appointment (planned mode)
| Property | Type | Description |
|---|---|---|
| patient_id, donor_id | FK | |
| transfusion_date | date | |
| slot | enum `confirmed` / `backup` | |
| status | enum `scheduled` / `confirmed` / `cancelled` / `completed` | `confirmed` = donor tapped "Yes, I'll come" |

### DonationRequest (request queue)
| Property | Type | Description |
|---|---|---|
| patient_id, blood_bank_id | FK | |
| type | enum `planned` / `urgent` | planned = circle could not cover a date; urgent = family pressed the button |
| status | enum `sent_to_bank` → `circle_alerted` → `nearby_alerted` → `filled` → `closed` | |
| needed_by | datetime | |
| circle_alerted_at, nearby_alerted_at | datetime | drives the 15-minute escalation |
| approved_by_user_id | FK → User | staff who approved |
| filled_by_donor_id | FK → Donor | first donor to accept |

### RequestAlert
| Property | Type | Description |
|---|---|---|
| request_id, donor_id | FK | |
| tier | enum `circle` / `nearby` | |
| distance_km, rank | | |
| status | enum `sent` / `accepted` / `declined` / `expired` | `expired` when someone else accepted first |

### DonationRecord (staff daily log)
| Property | Type | Description |
|---|---|---|
| donor_id, patient_id, appointment_id / request_id | FK | |
| outcome | enum `donated` / `deferred` / `no_show` / `excused` | only `no_show` counts against reliability |
| reason, on_date, recorded_by_user_id | | |

### Notification
Simulated SMS / in-app message (`user_id`, `text`, `created_at`). Nothing is actually sent.

### PhoneViewLog
One row every time a donor's phone number is shown to staff (`staff_user_id`, `donor_id`, `context`, `viewed_at`).
