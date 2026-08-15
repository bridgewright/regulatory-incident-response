---
name: customer-outage-notice
description: Use this skill when a user needs an in-progress outage notice, recovery notice, customer banner, mobile-trading-system notice, or short customer message. It produces three channel variants and prevents recovery language before recovery is confirmed.
---

# Customer Outage Notice

Create customer-facing Korean drafts from `incident.json` and the operating assumptions in `shared/company.json`.

## Boundaries

- Draft only; do not publish or send a message.
- Do not add facts that are absent from the incident record.
- If `timeline.resolved_at` is not confirmed, generate only the real-time notice. The recovery path must fail with exit code 2.
- Privacy notices belong to `privacy-breach-filing`, not this skill.

## Run

```bash
python3 scripts/generate_customer_notice.py incident.json \
  --mode realtime
python3 scripts/generate_customer_notice.py incident.json \
  --mode recovery
```

Use `--mode auto` to select recovery only when `resolved_at` exists. Use `--out` to override the output path or `--stdout-only` to avoid writing a file.

The script produces detailed web or mobile copy, a concise message, and a one-line status banner. A recovery notice must include the confirmed cause and compensation process. The agent may improve clarity and compress a long service list, but it must not introduce a new fact or imply recovery that has not been verified.

Report the saved path and ask the responsible operator to confirm facts, timing, customer-service details, and publication authority.
