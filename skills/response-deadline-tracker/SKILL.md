---
name: response-deadline-tracker
description: Use this skill when a user asks what is urgent, what remains incomplete, when a filing is due, or how the incident response is progressing. It recalculates deadlines and identifies the next required action from incident.json.
---

# Response Deadline Tracker

This is a read-only status dashboard. It does not submit, publish, or approve any item.

## Run

```bash
python3 scripts/incident_tracker.py incident.json
```

Use `--now` for a controlled evaluation timestamp, `--out` to override the output path, or `--stdout-only` to avoid persistence.

The tracker reads timestamps and the `reporting` object from `incident.json`, recalculates time remaining, highlights imminent deadlines, and identifies the most urgent incomplete item. It adds parallel security and privacy tracks when the incident data requires them; a Financial Supervisory Service report does not automatically satisfy those obligations.

Dashboard accuracy depends on status maintenance. After a draft is created or a human completes a submission, update the relevant status and `submitted_at` value. Report the generated dashboard path and any missing timestamp that prevents a reliable deadline calculation.
