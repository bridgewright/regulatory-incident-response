---
name: incident-response
description: Use this skill first when a user reports an outage, security incident, electronic-finance fraud, suspected data exposure, or asks what to do after an incident. It triages the event, establishes a single incident record, orders work by deadline, and routes the user to the required reporting, communication, privacy, governance, and tracking skills.
---

# Electronic-Finance Incident Response

Use this skill as the entry point. It coordinates review-ready drafts; it does not restore systems, submit filings, send notices, or replace an accountable incident commander.

## Operating rules

- Never invent times, affected users, loss amounts, causes, recovery status, or data-exposure facts.
- Record unavailable facts as `null`, `unknown`, or under investigation.
- Use `shared/incident.schema.json` as the single fact contract and reuse an existing incident record.
- Validate before invoking downstream workflows:

```bash
python3 shared/scripts/validate_incident.py incident.json
```

## Triage

Collect the minimum routing information in structured questions:

1. Incident category: service disruption, security breach, electronic-finance fraud, or under investigation.
2. Recovery state: ongoing or confirmed recovered.
3. Personal or credit information impact: none, personal information, credit information, both, or unknown.
4. Exact duration and affected-user count where available. Never infer a threshold result from a range midpoint.
5. Detection, occurrence, and recovery timestamps; affected system; concise observed impact.

Map the answers to `incident.json`. Ask for an exact value whenever a statutory boundary is material.

## Response order

| Timing | Action | Skill | Condition |
| --- | --- | --- | --- |
| Immediate | Issue an in-progress customer notice | `customer-outage-notice` | Service impact is ongoing |
| Within the applicable reporting window | Prepare the Financial Supervisory Service report | `regulator-incident-report` | After reportability assessment |
| In parallel | Prepare security and privacy notifications | `privacy-breach-filing` | Security incident or information exposure |
| As severity requires | Prepare executive and board reporting | `exec-board-report` | Mandatory factor or configured severity threshold |
| After confirmed recovery | Prepare recovery notice and final report | Customer and regulator skills | `timeline.resolved_at` is confirmed |
| Continuously | Recalculate deadlines and next action | `response-deadline-tracker` | At every material status change |

Generate the coordinated initial set when appropriate:

```bash
python3 shared/scripts/run_all_skills.py incident.json
```

After each output, update the relevant `reporting` status with `shared/scripts/set_status.py`. Explain the recommended sequence and the evidence still required before proceeding.
