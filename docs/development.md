# Development and tests

[English](development.md) | [한국어](ko/development.md) | [README](../README.md)

The current test environment uses HA 2026.10.2, plugin 0.13.373 and Python 3.14.2 or newer. The minimum supported HA remains 2025.3.0, tested separately with Python 3.13 and its compatible plugin 0.13.221.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements_test.txt -r requirements_lint.txt
.venv/bin/python -m pip check
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m pytest tests/components/chirp/ -v
```

Install `requirements_test_min.txt` in a separate environment to test minimum HA with the same pytest command. Tests check each environment against its exact HA/plugin requirements and ensure the minimum environment matches the support floor in `hacs.json`. Updating the current test environment does not raise component support requirements. Test dependencies are separate from the runtime manifest; review HA and its compatible plugin together. See [adopted standards](../STANDARDS.md) and the [checklist](../ADOPTION_CHECKLIST.md) for exact environments and verification limits.

## Domain and API contract

The integration domain is `chirp` (path `custom_components/chirp/`, tests in `tests/components/chirp/`). The API contract is the zod schema in the Chirp repository (`packages/shared/src/schema.ts`); `tests/components/chirp/fixtures/status.json` is an unmodified copy of its sample (`status.sample.json`) and the other `status_*.json` fixtures are variations of it (failing NVMe, new SATA SSD, standby, removed disk). Brand images are regenerated with `python scripts/generate_brand.py` (see `custom_components/chirp/brand/README.md`).
