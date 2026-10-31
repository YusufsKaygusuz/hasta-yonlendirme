# Security policy

This software processes biometric and health-related data, so security and privacy reports
are taken seriously.

## Reporting a vulnerability

Please **do not open a public issue**. Report it privately through
[GitHub's private vulnerability reporting](https://github.com/YusufsKaygusuz/hasta-yonlendirme/security/advisories/new).

Include what you found, how to reproduce it and its impact. You will get an answer within
seven days, and credit in the release notes if you wish.

## In scope

- Ways to obtain names, ID numbers or face encodings without authorisation
- Ways to make the kiosk route a patient as someone else
- Injection, unsafe deserialisation or secrets exposure in the code

Spoofing the camera with a printed photo is a known limitation (no liveness detection yet)
and is tracked as a feature, not a vulnerability.

## Supported versions

Security fixes are made on the latest release.
