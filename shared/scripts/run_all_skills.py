#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한 사건(incident.json)에 대해 kakaopaysec-incident-response의 모든 스킬을 순서대로 실행하는 배치 러너.

'최초 대응 시점'을 기준시각(--now)으로 잡아(기본: 인지시각 + 5분) 각 산출물을 생성한다.
산출물은 각 스킬 규칙대로 <incident 폴더>/out/ 에 .md로 자동 저장된다.

사용:
    python3 run_all_skills.py <incident.json> [--now ISO] [--quiet]

동작 스킬:
    1) regulator-incident-report (금감원 최초보고)          — 전 사건
    2) customer-outage-notice (고객 공지, auto)      — 전 사건
    3) exec-board-report (경영진·이사회, auto) — 전 사건
    4) privacy-breach-filing (개인정보 유출)  — 전 사건(내부 자가 판정: 해당없으면 '해당없음'으로 종료)
    5) response-deadline-tracker (대응 타임라인)       — 전 사건
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
SKILLS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "skills"))


def parse_dt(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def run(cmd, quiet):
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = r.returncode == 0
    tag = "✅" if ok else ("➖" if r.returncode == 2 else "⚠️")
    label = os.path.basename(os.path.dirname(os.path.dirname(cmd[1])))  # skill name
    print(f"  {tag} {label} (exit {r.returncode})")
    if not quiet and not ok:
        print("     stderr:", (r.stderr or "").strip().splitlines()[-1:] )
    # 저장 경로는 각 스크립트가 stderr로 '💾 저장: ...' 출력
    for line in (r.stderr or "").splitlines():
        if "💾" in line:
            print("    ", line.strip())
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("incident")
    ap.add_argument("--now", default=None, help="기준 현재시각(ISO). 기본: 인지시각+5분")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    inc_path = os.path.abspath(args.incident)
    with open(inc_path, encoding="utf-8") as f:
        inc = json.load(f)

    if args.now:
        now = args.now
    else:
        det = parse_dt(inc.get("detection", {}).get("detected_at", "")) or datetime.now(KST)
        now = (det + timedelta(minutes=5)).isoformat()

    resolved = inc.get("timeline", {}).get("resolved_at")
    iid = inc.get("incident_id", "?")
    print(f"▶ {iid} — 기준시각(최초대응) {now}  (복구여부: {'복구완료' if resolved else '진행중'})")

    # 사전 검증(pre-flight) — 스키마 enum·필수필드 오류 시 스킬 실행 중단
    validator = os.path.join(os.path.dirname(__file__), "validate_incident.py")
    pre = subprocess.run([sys.executable, validator, inc_path], capture_output=True, text=True)
    if pre.returncode != 0:
        print("  ❌ 사전 검증 실패 — 스킬 실행 중단:")
        for l in pre.stdout.splitlines():
            if "❌" in l:
                print(f"     {l.strip()}")
        return
    print("  ✅ 사전 검증 통과")

    pii = bool(inc.get("security", {}).get("personal_data_affected"))
    py = sys.executable
    # 개인정보 유출 사건이 아니면 신고서 파일은 저장하지 않고(--stdout-only) 판정만 수행 → 아카이브 정리
    privacy_cmd = [py, os.path.join(SKILLS, "privacy-breach-filing", "scripts", "gen_privacy_breach_report.py"), inc_path, "--now", now]
    if not pii:
        privacy_cmd.append("--stdout-only")
    steps = [
        [py, os.path.join(SKILLS, "regulator-incident-report", "scripts", "generate_fss_report.py"), inc_path, "--stage", "initial", "--now", now],
        [py, os.path.join(SKILLS, "regulator-incident-report", "scripts", "generate_fss_pdf.py"), inc_path, "--stage", "initial"],
        [py, os.path.join(SKILLS, "customer-outage-notice", "scripts", "generate_customer_notice.py"), inc_path, "--mode", "auto", "--now", now],
        [py, os.path.join(SKILLS, "exec-board-report", "scripts", "generate_management_report.py"), inc_path, "--tier", "auto", "--now", now],
        privacy_cmd,
        [py, os.path.join(SKILLS, "response-deadline-tracker", "scripts", "incident_tracker.py"), inc_path, "--now", now],
    ]
    results = []
    for cmd in steps:
        # 표준출력은 버리고(파일 저장됨) 성공/저장경로만 요약
        results.append(run(cmd, args.quiet))
    print(f"  → {sum(results)}/{len(results)} 스킬 실행 완료")

    # 가드레일: md ↔ PDF ↔ incident.json 정합성 자동 검증
    verifier = os.path.join(os.path.dirname(__file__), "verify_fss_consistency.py")
    vr = subprocess.run([py, verifier, inc_path, "--stage", "initial"], capture_output=True, text=True)
    tail = [l for l in vr.stdout.splitlines() if "→" in l or "❌" in l]
    print(f"  🛡️ 정합성 검증: {'✅ OK' if vr.returncode == 0 else '❌ 불일치'}")
    for l in tail:
        if "❌" in l:
            print(f"     {l.strip()}")
    print()


if __name__ == "__main__":
    main()
