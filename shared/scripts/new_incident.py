#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
빈 incident.json 스켈레톤을 생성한다. 담당자가 사실을 채워 넣는 출발점.
대화형이 아니라 빈 골격을 만들어 주는 방식(에이전트/사람이 값을 채움).

예:
  python3 new_incident.py --id INC-20260701-01 --out incident.json
  python3 new_incident.py --id INC-20260701-01        # stdout으로 출력
"""
import argparse
import json
import sys

SKELETON = {
    "incident_id": "",
    "title": "",
    "detection": {"first_recognizer": "금융회사", "detection_channel": "", "detected_at": ""},
    "timeline": {"occurred_at": "", "resolved_at": None, "events": []},
    "classification": {"incident_category": "전산장애사고", "failure_subtype": "미정(파악 중)", "failure_detail": ""},
    "impact": {
        "affected_services": [], "affected_markets": [],
        "single_branch_only": False, "public_webserver_only": False,
        "disruption_minutes": 0, "affected_users_count": 0, "incident_amount_krw": None
    },
    "cause": {"root_cause": "파악 중", "external_factor": False, "responsible_company": None, "affected_other_firms": None},
    "security": {"personal_data_affected": False},
    "system_name": "",
    "description": "",
    "handling": "",
    "measures": "",
    "victims": [],
    "compensation": {},
    "orders": [],
    "reporting": {
        "fss_initial": {"status": "미생성"},
        "fss_interim": {"status": "미생성"},
        "fss_final": {"status": "미생성"},
        "customer_realtime": {"status": "미생성"},
        "customer_recovery": {"status": "미생성"},
        "compensation_notice": {"status": "미생성"},
        "exec_brief": {"status": "미생성"},
        "board_report": {"status": "미생성"}
    }
}

# 인테이크 질문 순서(담당자가 빠르게 채우도록)
INTAKE_GUIDE = """\
# incident.json 인테이크 체크리스트 (이 순서로 채우세요)
1. detection.detected_at  : 언제 장애를 인지했나? (ISO, 예 2026-07-01T22:40:00+09:00)
2. timeline.occurred_at   : 실제 발생 시각은?
3. impact.disruption_minutes / affected_users_count : 중단 몇 분 / 영향 이용자 몇 명? (보고 트리거 판정 핵심)
4. impact.affected_services / affected_markets       : 어떤 서비스·시장이 영향?
5. classification.failure_subtype                    : 내부 오류 / 시스템 / 외부요인 중?
6. cause.external_factor / responsible_company        : 외부 연계 장애면 업체명(예 DriveWealth)
7. cause.root_cause                                  : 원인(미확정이면 '파악 중')
8. system_name / description                          : 사고 시스템명 / 현상·결과
9. (복구 후) timeline.resolved_at / handling / measures
10. (보상) orders[]에 미체결 주문 추가
"""


def main():
    ap = argparse.ArgumentParser(description="빈 incident.json 스켈레톤 생성")
    ap.add_argument("--id", default="", help="incident_id")
    ap.add_argument("--out", default=None, help="저장 경로(미지정 시 stdout)")
    ap.add_argument("--guide", action="store_true", help="인테이크 질문 가이드 출력")
    args = ap.parse_args()

    if args.guide:
        print(INTAKE_GUIDE)
        return

    skel = json.loads(json.dumps(SKELETON))
    skel["incident_id"] = args.id
    text = json.dumps(skel, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"✅ 스켈레톤 생성: {args.out}\n", file=sys.stderr)
        print(INTAKE_GUIDE, file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
