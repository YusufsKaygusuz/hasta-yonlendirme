# Privacy and data protection

Face data is a **special category of personal data** under Türkiye's Personal Data
Protection Law (KVKK, Law No. 6698, Art. 6) and the EU GDPR (Art. 9). This page lists what the
software does to protect it and what the operator (the hospital) still has to do.
It is not legal advice.

## What is stored

| Data | Stored? | How |
|---|---|---|
| Camera frames | **No** | Processed in memory and discarded. Nothing is recorded. |
| Enrolment photos | **No** | Only the face encoding computed from them is kept. |
| Face encoding | Yes | 128 numbers per photo, in `face_encodings`. Cannot be turned back into a photo, but is still biometric data. |
| National ID number | **No** (hash only) | HMAC-SHA256 with a secret pepper kept outside the database. |
| First and last name | Yes | Needed to greet the patient; the screen shows only "First L.". |
| Consent time | Yes | `patients.consent_at`, set at enrolment. |
| Appointments | Yes | Clinic, doctor and time. |

Logs contain internal patient numbers, never names or ID numbers.

## What the software enforces

- **Consent.** `enroll` refuses to run without `--consent`.
- **Erasure.** `forget` deletes all of a patient's face encodings. They can still use the
  ID-number path. The running kiosk drops them at the next gallery refresh
  (`gallery_refresh_seconds`, 5 minutes by default); restart it for immediate effect.
- **No disclosure by ID number.** Typing an unknown ID number and typing a registered one
  without an appointment produce the same screen, without a name.
- **Shoulder surfing.** The keypad shows only the last digit typed.
- **Data minimisation.** Only the nearest face in each frame is processed; nothing about
  passers-by is kept.
- **Secrets outside files.** The pepper and database password are read from environment
  variables only.

## What the operator must do

- Obtain **explicit consent** before enrolment and keep the signed record.
- Publish a **privacy notice** (aydınlatma metni) at the kiosk and on the website.
- Offer the ID-number path to everyone; never make face recognition mandatory.
- Define a **retention period** and remove face data when it ends (`forget`).
- Register the processing in VERBİS where required.
- Run a **data protection impact assessment** before going live.
- Test accuracy on your own patient population; recognition does not perform equally well
  for every group ([NIST IR 8280](https://doi.org/10.6028/NIST.IR.8280)).
- Consider adding **liveness detection** against someone holding up a photo of another
  patient (see the roadmap in the changelog).

## Database accounts

Use two MySQL accounts:

```sql
-- the kiosk only reads
CREATE USER 'kiosk'@'10.0.0.%' IDENTIFIED BY '...';
GRANT SELECT ON hasta_yonlendirme.* TO 'kiosk'@'10.0.0.%';

-- enrolment and administration, from a staff workstation
CREATE USER 'kiosk_admin'@'10.0.0.%' IDENTIFIED BY '...';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, REFERENCES ON hasta_yonlendirme.* TO 'kiosk_admin'@'10.0.0.%';
```

Restrict the network range to the kiosks, and enable TLS on the MySQL server.

## The pepper

The ID-number hash uses a secret pepper (`HY_ID_PEPPER`). Without it, a stolen database does
not reveal ID numbers, and the 11-digit space cannot simply be enumerated.

- Generate it once: `openssl rand -hex 32`.
- Store it outside the database, readable only by the kiosk user.
- Back it up securely: losing it means re-enrolling everyone.
