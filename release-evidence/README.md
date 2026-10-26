# Reviewed release evidence

Store only completed, reviewed `NAME.json` records here. Start from the candidate
workflow's `validation.json`; see [the release procedure](../docs/releases.md).

All checks must actually pass for the exact payload digest, source revision and
tested ISO checksum. Evidence URLs must point to durable, reviewed logs. Redact
credentials, usernames, serial numbers and other sensitive diagnostics first.
Do not commit keys, passwords, VM disks, or untested records marked as passing.

No completed record is supplied: this implementation does not prove Secure Boot,
GDM, registry-backed bootc updates, backup restoration or hardware readiness.
