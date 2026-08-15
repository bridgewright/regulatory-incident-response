---
name: regulator-incident-report
description: Use this skill when a user needs a Korean Financial Supervisory Service electronic-finance incident report, an EFARS field block, an official-form PDF draft, a reportability assessment, or a reporting-deadline calculation.
---

# Financial Supervisory Service Incident Report

Create a review-ready Korean report from `incident.json`. The skill does not submit to the Electronic Financial Accident Reporting System because no public submission interface is assumed.

## Current-law guardrail

Before relying on configured thresholds, check the current version of Article 7-4 of the Detailed Enforcement Rules of the Electronic Financial Supervision Regulations through an authoritative source or the configured Korean-law service. Compare the result with `reference/efars-rules.md`. If verification is unavailable, disclose that limitation and do not present the configured rule as newly verified law.

## Required facts

Collect incident category, report stage, first recognizer, exposure of personal or credit information, exact disruption duration, exact affected-user count, affected services, occurrence and detection times, system, observed impact, and any applicable exclusion. For security incidents and electronic-finance fraud, collect the corresponding classification and impact fields. Preserve unknown values as `null`; never infer which side of a statutory threshold they fall on.

## Run

```bash
python3 scripts/generate_fss_report.py incident.json \
  --stage initial
```

Stages are `initial`, `interim`, and `final`. Use `--now` only for controlled evaluation, `--out` to override persistence, or `--stdout-only` to print without saving.

For the official-form draft:

```bash
python3 scripts/generate_fss_pdf.py incident.json --stage initial
```

The PDF path uses a local headless browser. If no supported browser is available, retain the generated HTML and instruct the user to print it to PDF. Never invent the representative's name, document number, or recipient details.

Validate consistency across the incident record, Markdown report, and PDF mapping:

```bash
python3 shared/scripts/verify_fss_consistency.py incident.json
```

Present reportability, reasoning, deadline, missing facts, and the saved path before offering narrative refinement. Refinement may improve clarity but must not add facts. Initial reports may state that a cause is under investigation; final reports require confirmed recovery and prevention measures.
