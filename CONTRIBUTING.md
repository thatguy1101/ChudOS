# Contributing

- Run before every commit: `python3 tools/validation/validate.py && python3 -m pytest -q tests` and `shellcheck` on shell scripts.
- A setting, feature or button must have a real implementation and a test. No placeholder UI.
- Say what was tested and what was not (see docs/TESTING.md). Never write "works" for something only unit-tested with fakes.
- Keep Qt out of logic modules; keep privileged actions out of the GUI processes (pkexec / visible terminal only).
- Do not add repositories, telemetry, or network calls without a documented reason (docs/DECISIONS.md).
