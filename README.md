# Regulatory Incident Response

**A deterministic workflow for producing consistent response documents after an electronic-finance incident in Korea.**

The plugin accepts one structured incident record and produces review-ready drafts for the Financial Supervisory Service, customers, executives and the board, privacy regulators, and the internal response team. Language models may help draft narrative sections; code owns reportability thresholds, deadlines, status transitions, and cross-document consistency.

This is an independent portfolio project based on public statutes, official forms, and public incident reports. It is not affiliated with or endorsed by Kakao Pay Securities or any regulator.

## Problem Definition

The narrowest defensible automation opportunity begins after an incident has occurred. Infrastructure prevention and service restoration require internal systems and operating authority that a public-data prototype does not have. The post-incident reporting workflow, however, has explicit inputs, official forms, statutory thresholds, and time-bound outputs.

The product therefore does not claim to prevent, detect, remediate, submit, or send anything. It turns a validated incident record into a coordinated set of drafts and decision flags for accountable professionals to review.

## Outputs

| Workflow | Output | Control |
| --- | --- | --- |
| Regulatory reporting | Initial, interim, and final incident-report drafts, including an official-form PDF | Rule-based reportability and field mapping |
| Customer communication | Real-time outage notice, recovery notice, and compensation guidance | Stage and service-impact validation |
| Executive governance | Executive brief and board report | Configurable severity assessment |
| Privacy response | Notification and filing drafts | Threshold and sensitive-data checks |
| Deadline management | Response dashboard and next-action summary | Deterministic date and status calculation |

Korean statutory terms and filing language remain in Korean because they are operational artifacts, not documentation-localization omissions.

## Architecture

```text
incident.json
    │
    ├── schema and preflight validation
    ├── statutory and policy decisions
    ├── cross-document consistency checks
    │
    └── review-ready drafts
        ├── regulator report and PDF
        ├── customer notices
        ├── executive and board reports
        ├── privacy notification
        └── deadline dashboard
```

`shared/incident.schema.json` is the data contract. `shared/company.json` contains configurable operating assumptions rather than claims about any institution's internal policy. Missing values remain `null` and are surfaced for review; they are never converted silently to zero.

## Installation

Python 3.11 or later is recommended.

```bash
git clone https://github.com/bridgewright/regulatory-incident-response.git
cd regulatory-incident-response
```

For Codex:

```bash
codex plugin marketplace add bridgewright/regulatory-incident-response
codex plugin add regulatory-incident-response@regulatory-incident-response
```

For Claude Code:

```bash
claude plugin marketplace add bridgewright/regulatory-incident-response
claude plugin install regulatory-incident-response@regulatory-incident-response
```

## Usage

Start from the example record, validate it, and run the coordinated workflow:

```bash
python3 shared/scripts/new_incident.py --from-example --output incident.json
python3 shared/scripts/validate_incident.py incident.json
python3 shared/scripts/run_all_skills.py incident.json --output-dir output
```

The generated files are drafts. A responsible employee must verify the facts, legal interpretation, recipients, timing, and submission channel.

## Evaluation

```bash
python3 tests/test_plugin.py
```

The suite contains 25 tests covering statutory trigger boundaries, board-severity logic, business-day calculations, schema failures, unknown values, recovery locks, and status write-back. The design was also evaluated against 14 legal scenarios and eight incidents reconstructed from public information. Tests exposed an early defect in which an unknown affected-user count could collapse to zero; the schema and validation path were changed as a result.

## Limitations

- Public reporting rarely contains complete affected-user and loss data. A real decision requires internal records.
- Legal applicability can depend on facts and institutional classifications that this project cannot establish.
- Configurable board thresholds are operating assumptions, not verified internal policy.
- The plugin does not connect to regulatory, customer-messaging, or case-management systems.
- Generated documents do not have legal effect and require qualified review.

## Licensing and Third-Party Material

Original software is licensed under the MIT License. Korean statutes, official forms, regulatory names, company names, and trademarks are not covered by that license. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
