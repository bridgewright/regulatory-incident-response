---
name: privacy-breach-filing
description: Use this skill when personal or credit information may have been exposed and the user needs a data-subject notice, regulator filing draft, or deadline assessment. It keeps privacy and credit-information reporting separate from the electronic-finance incident report.
---

# Privacy and Credit-Information Notification

Activate this workflow when `security.personal_data_affected` is true. Otherwise return not applicable.

## Run

```bash
python3 scripts/gen_privacy_breach_report.py incident.json
```

The output contains a Korean data-subject notification, a regulator filing draft, deadline calculations, and separate flags for personal-information, credit-information, and security-incident reporting tracks.

Before drafting, verify the information type, exact exposed fields, exact number of affected data subjects, detection time, cause, containment, and prevention measures. Do not substitute a range for an exact count where the count affects reporting or response.

Current statutory thresholds and deadlines must be checked against an authoritative current source. If the configured Korean-law service is unavailable, disclose that current-law verification was not completed. Generated documents require legal and privacy review before use.
