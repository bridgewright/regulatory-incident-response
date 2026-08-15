#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""incident.json 사전 검증(pre-flight) — 모든 스킬 실행 전 공통 가드레일.

스키마의 핵심 enum·필수필드·타입을 검증해, 잘못된 데이터가 어느 스킬에든
들어가 '조용히 잘못된 산출물'을 만드는 것을 앞단에서 차단한다.
사고유형·세부유형 정규목록은 form_mapping(단일 원천)을 재사용한다.

미상 표현(null)은 오류가 아니라 정상: affected_users_count·incident_amount_krw·
resolved_at 은 null(미상/미복구)을 허용한다.

사용: python3 validate_incident.py <incident.json>
반환: 오류가 있으면 exit 1.
표준 라이브러리만 사용.
"""
import argparse
import importlib.util
import json
import os
import sys

_FM = os.path.join(os.path.dirname(__file__), "form_mapping.py")
_spec = importlib.util.spec_from_file_location("form_mapping", _FM)
fm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm)

INFO_TYPES = ["개인정보", "신용정보", "둘 다", "해당없음"]
RECOGNIZERS = ["금융회사", "고객(민원인)", "기타"]
STATUSES = ["미생성", "초안", "제출완료", "해당없음"]

# (경로, 라벨) — 반드시 값이 있어야 하는 필수 필드
REQUIRED = [
    ("incident_id", "장애 식별자"),
    ("detection.first_recognizer", "최초 인지 주체"),
    ("detection.detected_at", "사고인지일시"),
    ("timeline.occurred_at", "사고발생일시"),
    ("classification.incident_category", "사고유형"),
    ("system_name", "사고발생 시스템명"),
    ("description", "사고내용"),
]


def get(d, path, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def validate(inc):
    errs, warns = [], []

    # 1) 필수 필드
    for path, label in REQUIRED:
        v = get(inc, path)
        if v in (None, ""):
            errs.append(f"[필수] {label}({path}) 누락")

    # 2) enum — 사고유형(단일 원천), 세부유형, 최초인지, 정보종류, 보고상태
    cat = get(inc, "classification.incident_category")
    if cat is not None and cat not in fm.INCIDENT_CATEGORIES:
        errs.append(f"[enum] classification.incident_category '{cat}' ∉ {fm.INCIDENT_CATEGORIES}")
    if cat == "전산장애사고":
        sub = get(inc, "classification.failure_subtype")
        if sub not in (None, "") and sub not in fm.FAILURE_SUBTYPES:
            errs.append(f"[enum] classification.failure_subtype '{sub}' ∉ {fm.FAILURE_SUBTYPES}")
    fr = get(inc, "detection.first_recognizer")
    if fr not in (None, "") and fr not in RECOGNIZERS:
        errs.append(f"[enum] detection.first_recognizer '{fr}' ∉ {RECOGNIZERS}")
    it = get(inc, "security.info_type")
    if it not in (None, "") and it not in INFO_TYPES:
        errs.append(f"[enum] security.info_type '{it}' ∉ {INFO_TYPES}")
    rep = get(inc, "reporting") or {}
    if isinstance(rep, dict):
        for k, v in rep.items():
            st = v.get("status") if isinstance(v, dict) else None
            if st is not None and st not in STATUSES:
                errs.append(f"[enum] reporting.{k}.status '{st}' ∉ {STATUSES}")

    # 3) 타입 — 숫자 필드(미상=null 허용)
    dis = get(inc, "impact.disruption_minutes")
    if dis is not None and not isinstance(dis, (int, float)):
        errs.append(f"[타입] impact.disruption_minutes 는 숫자 또는 null(미상)여야 함: {dis!r}")
    users = get(inc, "impact.affected_users_count")
    if users is not None and not isinstance(users, int):
        errs.append(f"[타입] impact.affected_users_count 는 정수 또는 null(미상)여야 함: {users!r}")
    amt = get(inc, "impact.incident_amount_krw")
    if amt is not None and not isinstance(amt, (int, float)):
        errs.append(f"[타입] impact.incident_amount_krw 는 숫자 또는 null(미상)여야 함: {amt!r}")

    # 4) 논리 경고 — 침해/개인정보 정합
    if cat == "침해사고" and get(inc, "security.personal_data_affected") is None:
        warns.append("[경고] 침해사고인데 security.personal_data_affected 미설정 — 개인정보 유출 여부 확인 권장")
    if get(inc, "security.personal_data_affected") and not get(inc, "security.info_type"):
        warns.append("[경고] 개인정보 영향(true)인데 info_type 미설정 — 개인정보/신용정보/둘 다 확인 권장")
    if dis is None:
        warns.append("[미상] impact.disruption_minutes 미상 — 보고대상 시간기준 판정 보류(확정 필요)")
    if users is None:
        warns.append("[미상] impact.affected_users_count 미상 — '10분+1만명' 요건 재판정 필요")

    return errs, warns


def preflight_or_exit(inc, skip=False):
    """각 스킬 main()에서 호출하는 사전 검증. 경고는 stderr로 알리고,
    하드 오류(enum·필수필드·타입)면 stderr에 출력 후 exit(1)로 산출물 생성을 막는다.
    skip=True(예: --no-validate)면 생략."""
    if skip:
        return
    errs, warns = validate(inc)
    for w in warns:
        print(f"🟡 사전검증 {w}", file=sys.stderr)
    if errs:
        print("❌ 사전검증 실패 — incident.json 오류로 산출물 생성 중단:", file=sys.stderr)
        for e in errs:
            print(f"   {e}", file=sys.stderr)
        print("   상세: validate_incident.py <파일> / 우회: --no-validate", file=sys.stderr)
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="incident.json 사전 검증")
    ap.add_argument("incident")
    ap.add_argument("--quiet", action="store_true", help="오류 없으면 출력 생략")
    args = ap.parse_args()
    with open(args.incident, encoding="utf-8") as f:
        inc = json.load(f)
    errs, warns = validate(inc)
    iid = inc.get("incident_id", "?")
    if errs or not args.quiet:
        print(f"■ {iid} 사전 검증")
        for e in errs:
            print(f"  ❌ {e}")
        for w in warns:
            print(f"  🟡 {w}")
        print(f"  → {'✅ 통과' if not errs else '❌ 오류 ' + str(len(errs)) + '건 — 스킬 실행 전 수정 필요'}")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
