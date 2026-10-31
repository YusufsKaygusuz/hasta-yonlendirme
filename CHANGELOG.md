# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Planned

- Liveness detection against printed photos and screens
- HL7 FHIR repository for hospital information systems
- More natural offline voice (neural text-to-speech)
- Accessibility mode with larger text and slower speech

## [1.0.0] - 2026-10-31

First public release, based on the TÜBİTAK 2209-A research project.

### Added

- Face recognition kiosk for Raspberry Pi 4 and any computer with a webcam
- Matching with tolerance, ambiguity margin and multi-frame confirmation
- National ID fallback with checksum validation, on touchscreen or keyboard
- Keyed hashing of national ID numbers; photos are never stored
- Appointment routing with early and late arrival windows
- Tkinter touch interface that scales from 800×480 to full HD, and a text interface
- Spoken directions in Turkish and English through espeak-ng (Linux) or the built-in voices (macOS), with titles and floors read naturally
- SQLite and MySQL storage behind a `Repository` interface
- Command-line tools: `run`, `enroll`, `forget`, `demo`, `init-db`, `check-camera` and data management
- Raspberry Pi setup guide, systemd service, architecture and privacy documentation
- Test suite and continuous integration on Python 3.10 to 3.12, with MySQL

[Unreleased]: https://github.com/YusufsKaygusuz/hasta-yonlendirme/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/YusufsKaygusuz/hasta-yonlendirme/releases/tag/v1.0.0
