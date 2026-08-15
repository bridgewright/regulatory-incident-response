#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
incident.json의 reporting{} 상태를 갱신(write-back)한다.
각 스킬로 산출물을 만든 뒤 호출해 타임라인 대시보드(스킬4) 정확도를 유지한다.

예:
  python3 set_status.py incident.json --key fss_initial --status 초안
  python3 set_status.py incident.json --key fss_initial --status 제출완료 --submitted 2025-10-09T11:00:00+09:00
"""
import argparse
import json
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
VALID_KEYS = [
    "fss_initial", "fss_interim", "fss_final",
    "kisa_report", "privacy_report",
    "customer_realtime", "customer_recovery",
    "compensation_notice", "exec_brief", "board_report",
]
VALID_STATUS = ["미생성", "초안", "제출완료", "해당없음"]


def main():
    ap = argparse.ArgumentParser(description="reporting 상태 갱신")
    ap.add_argument("incident")
    ap.add_argument("--key", required=True, choices=VALID_KEYS)
    ap.add_argument("--status", required=True, choices=VALID_STATUS)
    ap.add_argument("--generated", default=None, help="초안 생성시각(ISO)")
    ap.add_argument("--submitted", default=None, help="제출완료 시각(ISO)")
    args = ap.parse_args()

    with open(args.incident, encoding="utf-8") as f:
        inc = json.load(f)
    rep = inc.setdefault("reporting", {})
    entry = rep.setdefault(args.key, {})
    entry["status"] = args.status
    if args.status == "초안":
        entry["generated_at"] = args.generated or datetime.now(KST).isoformat(timespec="seconds")
    if args.status == "제출완료":
        entry["submitted_at"] = args.submitted or datetime.now(KST).isoformat(timespec="seconds")

    with open(args.incident, "w", encoding="utf-8") as f:
        json.dump(inc, f, ensure_ascii=False, indent=2)
    print(f"✅ reporting.{args.key}.status = '{args.status}' 갱신됨 → {args.incident}")


if __name__ == "__main__":
    main()
