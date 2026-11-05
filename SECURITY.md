# Security

Report problems privately to the project maintainer (contact address not set up yet: placeholder).

Design rules (enforced by tests where noted): GUIs never run as root (Store refuses); privileged steps use `pkexec` or a terminal the user watches;
subprocesses are argv lists, never shells; profile files are validated data, never executed (tested); package names are validated and
separated with `--` (tested); no telemetry; package signature checks are never disabled (validator rejects `SigLevel Never` and extra remote repos).
Live medium only: user `chud` has passwordless sudo and autologin. Installed systems must not have these (validator enforces separation of files).
Known gaps: see docs/RELEASE-CANDIDATE.md (generic polkit prompt, unsigned local build repo, Secure Boot not supported).
