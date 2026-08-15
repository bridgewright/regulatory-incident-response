---
name: exec-board-report
description: Use this skill for an executive incident brief, board report, chief executive update, or board-materiality assessment. It produces a Tier A executive brief and, when indicated, a Tier B board report.
---

# Executive and Board Reporting

Generate governance drafts from a validated `incident.json`. The materiality result is a recommendation for accountable officers, not a binding legal conclusion.

## Run

```bash
python3 scripts/generate_management_report.py incident.json \
  --tier auto
```

Supported tiers are `auto`, `a`, `b`, and `both`. `--json` returns only the materiality decision for orchestration. Use `--out` or `--stdout-only` to control persistence.

## Materiality logic

- Mandatory factors: a security incident or impact on personal or credit information.
- Weighted factors: affected users, disruption duration, incident amount, and combined third-party and cross-institution impact.
- In the supplied example policy, two weighted factors trigger a board recommendation. Thresholds are configurable and must be reviewed against the institution's actual policy.

Never estimate a value that determines a threshold. If incident category or information exposure is unknown, obtain that fact before stating a conclusion. Present the decision and its reasons before the report, identify unresolved governance fields, and report the saved output path.
