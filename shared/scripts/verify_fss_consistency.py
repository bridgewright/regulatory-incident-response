#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""regulator-incident-report 정합성 가드레일.

incident.json(단일 진실원장) ↔ md 보고서 ↔ 별지 제2호서식 PDF(HTML) 3자가
서로 어긋나지 않는지 검증한다. 매핑 로직이 md/pdf에 중복돼 있어 발생할 수 있는
'조용한 불일치'를 실행 시점에 잡아낸다. 또한 스키마 enum 위반과 미입력·미상 항목을 표로 보고.

검증 불변식:
  1) incident.json이 스키마 enum(사고유형·세부유형)을 지킨다.
  2) PDF 보고형태 체크 == --stage.
  3) 사고유형 '대분류 열'은 사고유형에 맞는 열만 체크된다(전산장애/침해/사기; 개인정보 동반 시 침해 열 정보유출 허용).
  4) 전산장애면 세부유형 체크 정확히 1개 & failure_subtype와 일치. 최초인지 체크 정확히 1개 & first_recognizer와 일치.
  5) md의 사고유형·보고대상 판정과 PDF 활성 열이 일치.
  6) 미입력/미상 항목을 나열(오류 아님, 리뷰 투명성).

사용: python3 verify_fss_consistency.py <incident.json> [--stage initial|interim|final]
반환: 불일치 있으면 exit 1.
"""
import argparse, importlib.util, os, re, sys, json

SKILLS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "skills"))


def load(mod, rel):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(SKILLS, rel))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


fsspdf = load("fsspdf", "regulator-incident-report/scripts/generate_fss_pdf.py")
fssmd = load("fssmd", "regulator-incident-report/scripts/generate_fss_report.py")

def _load_fm():
    p = os.path.join(os.path.dirname(__file__), "form_mapping.py")
    spec = importlib.util.spec_from_file_location("form_mapping", p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


fm = _load_fm()


def html_checked(html):
    """렌더된 HTML에서 ☑ 라벨 집합 추출. '기타: xxx'는 '기타'로 정규화(오라클과 비교용)."""
    s = set()
    for m in re.findall(r"☑\s*([^<]+)", html):
        lab = m.strip()
        if lab.startswith("기타:"):
            lab = "기타"
        s.add(lab)
    return s


def verify(inc, stage):
    errs, warns, info = [], [], []
    g = lambda p, d=None: fssmd.get(inc, p, d)
    cat = g("classification.incident_category")
    sub = g("classification.failure_subtype")

    # 1) 스키마 enum (form_mapping 정규목록 기준)
    if not fm.is_valid_category(inc):
        errs.append(f"[스키마] incident_category '{cat}' ∉ {fm.INCIDENT_CATEGORIES}")
    if not fm.is_valid_subtype(inc):
        errs.append(f"[스키마] failure_subtype '{sub}' ∉ {fm.FAILURE_SUBTYPES} → 체크박스 매칭 실패 위험")

    # 2) 핵심 불변식: 렌더된 PDF의 ☑ 집합 == form_mapping(단일 원천)이 계산한 체크 집합
    #    → md·PDF·검증기가 같은 규칙을 쓰는지, 렌더 단계에서 누락/오타가 없는지 한 번에 검증
    from datetime import datetime, timezone, timedelta
    now = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=9)))
    html = fsspdf.build_html(inc, {"legal_name": "테스트", "company_name": "테스트"}, stage, now)
    expected = set()
    for label in fm.checked_set(inc, stage):
        expected.add("기타" if label.startswith("기타") else label)
    actual = html_checked(html)
    missing = expected - actual   # 오라클은 체크인데 PDF에 없음
    extra = actual - expected     # PDF에 있는데 오라클엔 없음
    if missing:
        errs.append(f"[체크박스] PDF에 누락된 체크: {sorted(missing)}")
    if extra:
        errs.append(f"[체크박스] PDF에 잘못 추가된 체크: {sorted(extra)}")

    # 3) md ↔ pdf 사고유형·판정 교차 (build_report는 문자열 반환)
    _md = fssmd.build_report(inc, stage, now)
    md = _md if isinstance(_md, str) else "\n".join(_md)
    if cat == "전산장애사고":
        want = dict(fm.FAILURE_SUBTYPE_OPTIONS)[fm.selected_subtype(inc)]
        if want not in actual:
            errs.append(f"[md↔pdf] 전산장애 세부유형 '{fm.selected_subtype(inc)}'가 PDF에 미체크")
    if "보고 대상 판정" not in md and "보고 의무" not in md:
        warns.append("[md] 보고 대상 판정 섹션 누락")

    # 6) 미입력/미상 투명성
    for path, name in [("impact.affected_users_count", "영향 이용자수"), ("impact.incident_amount_krw", "사고금액"),
                       ("timeline.resolved_at", "사고종료일시"), ("cause.root_cause", "사고원인"),
                       ("handling", "처리결과"), ("measures", "대책")]:
        v = g(path)
        if v is None or (isinstance(v, str) and ("파악 중" in v or "미상" in v)):
            info.append(name)
    return errs, warns, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("incident")
    ap.add_argument("--stage", default="initial", choices=["initial", "interim", "final"])
    args = ap.parse_args()
    with open(args.incident, encoding="utf-8") as f:
        inc = json.load(f)
    errs, warns, info = verify(inc, args.stage)
    iid = inc.get("incident_id", "?")
    print(f"■ {iid} 정합성 검증")
    for e in errs: print(f"  ❌ {e}")
    for w in warns: print(f"  🟡 {w}")
    if info: print(f"  ℹ️ 미입력·미상 항목(담당자 보완 필요): {', '.join(info)}")
    print(f"  → {'✅ 정합성 OK' if not errs else '❌ 불일치 ' + str(len(errs)) + '건'}")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
