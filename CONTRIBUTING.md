# Contributing

Thank you for helping make hospital wayfinding easier. Issues and pull requests in English
or Turkish are both welcome. (Türkçe katkılar da memnuniyetle karşılanır.)

## Getting started

```bash
git clone https://github.com/YusufsKaygusuz/hasta-yonlendirme.git
cd hasta-yonlendirme
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install          # optional: runs the linters on every commit
pytest
```

The test suite needs no camera and no dlib. Install `.[face,camera]` only when you work on
recognition or want to run the kiosk.

## Before opening a pull request

- `pytest` passes, and new behaviour has a test.
- `ruff check .`, `ruff format --check .` and `mypy` are clean.
- User-facing text is added to **both** languages in `src/hasta_yonlendirme/i18n.py`
  (a test checks that the catalogues match).
- `CHANGELOG.md` has a line under *Unreleased*.
- Never commit real patient data, photos of real people, or secrets.

## Design principles

- **Prefer "not recognised" over "wrong person".** Changes to matching must not make a
  false match more likely without a good reason and a test that shows the trade-off.
- **The fallback path must always work**, with or without camera and face library.
- **Keep hardware at the edges.** Logic belongs in the controller, matcher or routing
  service, where it can be tested without devices.
- **Privacy is a feature.** Do not log names or ID numbers; do not store images.

## Reporting bugs and security issues

Use the issue templates for bugs and feature requests. Report security or privacy problems
privately, as described in [SECURITY.md](SECURITY.md).

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE)
and that you follow the [Code of Conduct](CODE_OF_CONDUCT.md).
