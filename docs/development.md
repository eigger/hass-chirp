# Development and tests

[English](development.md) | [한국어](ko/development.md) | [README](../README.md)

The current test environment uses HA 2026.10.4 and plugin 0.13.375. The minimum supported HA is 2026.10.0, tested separately with its compatible plugin 0.13.371. Both environments require Python 3.14.2 or newer. The support floor was raised to remove known Home Assistant and aiohttp vulnerabilities from the historical HA 2025.3.0 test environment.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements_test.txt -r requirements_lint.txt
.venv/bin/python -m pip check
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m pytest tests/components/chirp/ -v
```

Install `requirements_test_min.txt` in a separate environment to test minimum HA with the same pytest command. Tests check each environment against its exact HA/plugin requirements and ensure the minimum environment matches the support floor in `hacs.json`. Dependabot updates the current test environment and groups pip security updates separately. The exact minimum HA/plugin pair in `requirements_test_min.txt` is excluded from automated updates because it defines the supported version floor. Change it only in an explicit support-floor PR that also updates `hacs.json`, the CI expected version and the support documentation; the environment test catches mismatches. Review security alerts for the minimum environment when deciding whether to raise that floor. Updating only the current test environment does not raise component support requirements. Test dependencies are separate from the runtime manifest; review HA and its compatible plugin together. See [adopted standards](../STANDARDS.md) and the [checklist](../ADOPTION_CHECKLIST.md) for exact environments and verification limits.

## Domain and API contract

The integration domain is `chirp` (path `custom_components/chirp/`, tests in `tests/components/chirp/`). The API contract is the zod schema in the Chirp repository (`packages/shared/src/schema.ts`); `tests/components/chirp/fixtures/status.json` is an unmodified copy of its sample (`status.sample.json`); `status_container_scope.json`, `status_null_sections.json` and `status_legacy.json` are unmodified copies of `status.container-scope.json`, `status.null-sections.json` and `status.legacy.json` (container-scope host metrics, every metric section `null`, an older server without host metrics). The other `status_*.json` fixtures are variations of the sample (failing NVMe, new SATA SSD, standby, removed disk). Host metric `scope` values other than `host` and `container` (a value a future server might add) are passed through unchanged in each entity's `scope` attribute, while the **Metrics scope** summary sensor becomes *unknown* rather than guessing; see `_data_scope` in `sensor.py`. Fan, voltage and power source names drop the "speed"/"voltage"/"power" suffix when the chip label already contains an English word for it (`label_words` in `sensor.py`); chip labels are English, so the Korean name then shows the bare label too (`power1`, not `power1 전력`). Brand images are regenerated with `python scripts/generate_brand.py` (see `custom_components/chirp/brand/README.md`).
