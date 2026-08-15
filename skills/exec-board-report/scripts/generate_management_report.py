#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
경영진·이사회 상황보고서 생성기 (+ 이사회 보고대상 자동 판정).

근거:
- 전자금융감독규정: CISO는 정보보호위원회 심의·의결사항을 최고경영자(CEO)에 보고.
- 전자금융거래의 안전성·신뢰성에 '중대한 영향'을 미치는 사항(침해사고·개인정보유출 대응,
  클라우드·제3자 리스크 포함)은 이사회에 보고. (2025.8.5 시행)
- 금융회사 지배구조법: 내부통제 '주요사항' 이사회 보고.

출력:
- 이사회 보고대상 판정 — 전 조건을 평가하고 각 조건의 충족 여부·기준·현재값·결론을 상세 기재.
- Tier A 경영진 속보(1보): 항상 생성.
- Tier B 이사회 보고서: '중대' 판정 시 생성(또는 강제 옵션).
- 판정은 '권고'다. 최종 판단은 CISO/이사회 몫.

표준 라이브러리만 사용. 보고 행위 자체는 하지 않는다.
"""
import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone

# 사고유형 정규목록·판정의 단일 원천(fss와 공용)
_FM = os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "scripts", "form_mapping.py")
_spec = importlib.util.spec_from_file_location("form_mapping", _FM)
fm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm)

# 공통 사전 검증(단독 호출 시에도 자동 검증)
_VD = os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "scripts", "validate_incident.py")
_vspec = importlib.util.spec_from_file_location("validate_incident", _VD)
_validate = importlib.util.module_from_spec(_vspec)
_vspec.loader.exec_module(_validate)

KST = timezone(timedelta(hours=9))

# 중대성 판정 임계치 기본값 — company.json의 board_severity_thresholds로 보정 가능
DEFAULT_TH = {
    "affected_users": 100000,
    "disruption_minutes": 60,
    "incident_amount_krw": 100000000,
    "factors_required_for_board": 2,
}


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def fmt(dt):
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M") if dt else "(미입력)"


def fmt_sec(dt):
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S (KST)") if dt else "(미입력)"


def save_and_print(text, incident_path, incident_id, suffix, out, stdout_only):
    print(text)
    if not stdout_only:
        path = out or os.path.join(os.path.dirname(os.path.abspath(incident_path)), "out", f"{incident_id}_{suffix}.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"💾 저장: {path}", file=sys.stderr)


def get(d, path, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur not in (None, "") else default


def yn(b):
    return "✅ 충족" if b else "❌ 미충족"


def assess_board(inc, th):
    """이사회 보고대상 여부(권고) + 전 조건별 상세 평가."""
    cat = fm.selected_category(inc)  # 사고유형 정규목록은 form_mapping 단일 원천
    pii = get(inc, "security.personal_data_affected", False)
    users = get(inc, "impact.affected_users_count", 0) or 0
    mins = get(inc, "impact.disruption_minutes", 0) or 0
    raw_amount = get(inc, "impact.incident_amount_krw")
    amount = raw_amount or 0
    ext = get(inc, "cause.external_factor", False)
    other = get(inc, "cause.affected_other_firms")
    req_n = th["factors_required_for_board"]

    # 필수사유 (하나라도 충족 시 즉시 대상)
    mandatory = [
        {"label": "침해사고 (전자적 침해행위로 인한 사고)",
         "met": cat == "침해사고",
         "status": f"사고유형 = {cat or '(미입력)'}"},
        {"label": "개인정보·신용정보 영향",
         "met": bool(pii),
         "status": "유출·영향 있음 (별도 신고 의무 검토)" if pii else "영향 없음"},
    ]
    # 가중요인 (factors_required_for_board 개 이상 충족 시 대상)
    weighted = [
        {"label": "영향 이용자수", "criterion": f"≥ {th['affected_users']:,}명",
         "actual": f"{users:,}명", "met": users >= th["affected_users"]},
        {"label": "지연·중단 시간", "criterion": f"≥ {th['disruption_minutes']}분",
         "actual": f"{mins}분", "met": mins >= th["disruption_minutes"]},
        {"label": "사고금액", "criterion": f"≥ {th['incident_amount_krw']:,}원",
         "actual": (f"{raw_amount:,}원" if isinstance(raw_amount, (int, float)) else "미상(미입력)"),
         "met": amount >= th["incident_amount_krw"]},
        {"label": "외부 제3자 연계 + 타사 동시영향", "criterion": "외부요인 장애 & 타사 동시영향 모두 해당",
         "actual": f"외부요인={'예' if ext else '아니오'}, 타사 동시영향={'있음' if other else '없음/미확인'}",
         "met": bool(ext and other)},
    ]
    m_met = sum(1 for m in mandatory if m["met"])
    w_met = sum(1 for w in weighted if w["met"])
    required = m_met > 0 or w_met >= req_n

    # 결론 문장
    if m_met > 0:
        names = ", ".join(m["label"].split(" (")[0] for m in mandatory if m["met"])
        conclusion = f"필수사유 {m_met}개 충족({names}) → **이사회 보고대상**. (필수사유는 하나만 있어도 즉시 대상)"
    elif w_met >= req_n:
        names = ", ".join(w["label"] for w in weighted if w["met"])
        conclusion = f"필수사유 0개, 가중요인 **{w_met}개** 충족({names}) → 기준({req_n}개) 이상이므로 **이사회 보고대상**."
    else:
        conclusion = (f"필수사유 0개, 가중요인 **{w_met}개** 충족 → 기준({req_n}개) 미만이고 필수사유도 없으므로 "
                      f"**이사회 보고대상 아님 (경영진 보고로 갈음 가능)**.")

    return {"required": required, "mandatory": mandatory, "weighted": weighted,
            "m_met": m_met, "w_met": w_met, "req_n": req_n, "conclusion": conclusion, "th": th}


def render_rationale(board):
    """전 조건 평가표 + 규칙 + 결론 (상세 근거)."""
    L = []
    L.append(f"- **결과: {'⭕ 이사회 보고대상' if board['required'] else '➖ 경영진 보고로 갈음 가능(이사회 비대상)'}** (권고 — 최종 판단 CISO/이사회)")
    L.append(f"- **판정 규칙**: **필수사유 1개 이상** 충족, 또는 **가중요인 {board['req_n']}개 이상** 충족 시 이사회 보고대상")
    L.append("  - 근거: 전자금융감독규정(안전성·신뢰성 '중대한 영향' 사항 이사회 보고, 2025.8.5 시행) + 금융회사 지배구조법 내부통제")
    L.append("")
    L.append("**① 필수사유** — 하나라도 충족 시 즉시 이사회 보고대상")
    L.append("| 조건 | 충족 | 현황 |")
    L.append("|---|---|---|")
    for m in board["mandatory"]:
        L.append(f"| {m['label']} | {yn(m['met'])} | {m['status']} |")
    L.append("")
    L.append(f"**② 가중요인** — {board['req_n']}개 이상 충족 시 이사회 보고대상")
    L.append("| 조건 | 기준 | 현재값 | 충족 |")
    L.append("|---|---|---|---|")
    for w in board["weighted"]:
        L.append(f"| {w['label']} | {w['criterion']} | {w['actual']} | {yn(w['met'])} |")
    L.append("")
    L.append(f"**→ 결론**: {board['conclusion']}")
    return "\n".join(L)


def parallel_filings(inc, d):
    """금감원 보고로 '갈음되지 않는' 병행 신고 시한 목록. (fss 「1-1 병행 신고 점검」과 동일 근거)"""
    cat = fm.selected_category(inc)
    pii = get(inc, "security.personal_data_affected", False)
    items = []
    if cat == "침해사고":
        items.append(f"정보통신망법 §48조의3 KISA/과기정통부 신고 — 인지+24h({fmt(d + timedelta(hours=24)) if d else '-'})")
    if pii:
        items.append(f"개인정보보호법 유출신고(보호위·KISA) — 인지+72h({fmt(d + timedelta(hours=72)) if d else '-'})")
        if get(inc, "security.info_type") in ("신용정보", "둘 다"):
            items.append("신용정보법 §39조의4 금융위·금감원 신고 — 병행(privacy-breach 참조)")
    return items


def scope_note(inc):
    """플러그인 범위밖이지만 놓치면 안 되는 후속 트랙 각주."""
    cat = fm.selected_category(inc)
    if cat == "전자금융사기사고":
        return "전자금융사기 피해자 지급정지·통지·환급은 통신사기피해환급법 별도 트랙(본 플러그인 범위밖)"
    # 침해사고로 이용자 금전피해(무권한 전자금융거래) 정황이면 전자금융거래법 §9 배상·통지 트랙
    dmg = (get(inc, "security.attack_damage") or "")
    if cat == "침해사고" and ("금전" in dmg or "손실" in dmg or (get(inc, "victims") or [])):
        return "해킹發 무권한 전자금융거래 손해는 전자금융거래법 §9 배상책임·이용자 통지 별도 검토(본 플러그인 범위밖)"
    return ""


def parallel_block(inc, d, head="", sub="  - "):
    """병행 신고를 여러 줄(헤더 + 하위 불릿)로 렌더 — 다건 가독성. 없으면 '해당 없음' 한 줄. + 범위밖 각주."""
    par = parallel_filings(inc, d)
    out = []
    if par:
        out.append(f"{head}병행 신고(금감원 보고로 갈음 안 됨):")
        out += [f"{sub}{p}" for p in par]
    else:
        out.append(f"{head}병행 신고(금감원 보고로 갈음 안 됨): 해당 없음")
    note = scope_note(inc)
    if note:
        out.append(f"{sub}※ {note}")
    return out


def tier_a(inc, board):
    o = parse_dt(get(inc, "timeline.occurred_at"))
    d = parse_dt(get(inc, "detection.detected_at"))
    r = parse_dt(get(inc, "timeline.resolved_at"))
    status = "복구 완료" if r else "대응 중"
    cat = fm.selected_category(inc) or "전산장애사고"  # 제목에 실제 사고유형 반영
    lines = [
        "## [Tier A] 경영진 속보 (1보)",
        "```text",
        f"[경영진 보고 — {cat} 1보] {get(inc,'incident_id','')}",
        f"제목: {get(inc,'title','(제목 미입력)')}",
        f"발생/인지: {fmt(o)} / {fmt(d)}    현재상태: {status}" + (f" (종료 {fmt(r)})" if r else ""),
        f"영향: {', '.join(get(inc,'impact.affected_services',[]) or get(inc,'impact.affected_markets',[]) or ['(미입력)'])}"
        f" / 이용자 {get(inc,'impact.affected_users_count','-')}명 / 중단 {get(inc,'impact.disruption_minutes','-')}분",
        f"원인: {get(inc,'cause.root_cause','(파악 중)')}",
        f"대응현황: {get(inc,'handling','(진행 중)')}",
        f"규제보고: 금감원 최초보고 24시간 이내 대상 여부 확인 필요(regulator-incident-report 참조)",
        *parallel_block(inc, d, head="", sub="  - "),
        f"이사회 보고대상(권고): {'예' if board['required'] else '아니오'}",
        f"다음 보고: 상황 변동/복구 시",
        "```",
    ]
    return "\n".join(lines)


def tier_b(inc, board):
    o = parse_dt(get(inc, "timeline.occurred_at"))
    r = parse_dt(get(inc, "timeline.resolved_at"))
    lines = [
        "## [Tier B] 이사회 보고서",
        "",
        f"- 사안: {get(inc,'title','')} ({get(inc,'incident_id','')})",
        "",
        "### 1. 중대성 판단 (이사회 보고 근거)",
        render_rationale(board),
        "",
        "### 2. 사고 개요",
        f"- 발생/종료: {fmt(o)} / {fmt(r)} / 중단 {get(inc,'impact.disruption_minutes','-')}분",
        f"- 영향: 이용자 {get(inc,'impact.affected_users_count','-')}명 / {', '.join(get(inc,'impact.affected_services',[]) or ['-'])}",
        f"- 원인: {get(inc,'cause.root_cause','(파악 중)')}",
        "",
        "### 3. 침해사고·개인정보 영향",
        f"- 사고유형: {get(inc,'classification.incident_category','-')}",
        f"- 개인정보·신용정보 영향: {'있음 (별도 신고 의무 검토)' if get(inc,'security.personal_data_affected') else '없음'}",
        *parallel_block(inc, parse_dt(get(inc, "detection.detected_at")), head="- ", sub="  - "),
        "",
        "### 4. 외부·제3자 리스크",
        f"- 외부요인 장애: {'예' if get(inc,'cause.external_factor') else '아니오'}"
        + (f" / 원인회사: {get(inc,'cause.responsible_company','-')}" if get(inc,'cause.external_factor') else ""),
        f"- 타사 동시영향: {get(inc,'cause.affected_other_firms','-')}",
        "",
        "### 5. 재무·평판 영향",
        f"- 사고금액: {get(inc,'impact.incident_amount_krw','(미상)')} / 배상(예상): {get(inc,'compensation.total_amount_krw','(산정 중)')}",
        "- 평판: 반복 장애 시 고객 신뢰·MAU 영향(정성) — 필요 시 보강",
        "",
        "### 6. 재발방지·거버넌스 조치",
        f"- 대책: {get(inc,'measures','(수립 중)')}",
        "- 책무구조도상 책임 임원: (지정 임원 기재 필요)",
        "- 정보보호위원회 심의 결과 및 이사회 보고 일자: (기재 필요)",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="경영진·이사회 상황보고서 생성기")
    ap.add_argument("incident")
    ap.add_argument("--tier", choices=["a", "b", "both", "auto"], default="auto",
                    help="auto=경영진 속보 + (중대 시)이사회 보고서")
    ap.add_argument("--company", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--now", default=None, help="문서 생성시각(ISO). 미지정 시 실제 현재시각(KST)")
    ap.add_argument("--out", default=None, help="저장 경로(미지정 시 <incident 폴더>/out/<id>_경영진이사회보고.md)")
    ap.add_argument("--stdout-only", action="store_true", help="파일 저장 없이 화면 출력만")
    ap.add_argument("--no-validate", action="store_true", help="사전 검증 생략")
    args = ap.parse_args()

    with open(args.incident, encoding="utf-8") as f:
        inc = json.load(f)
    _validate.preflight_or_exit(inc, skip=args.no_validate)
    now = parse_dt(args.now) or datetime.now(KST)
    comp_path = args.company or os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "company.json")
    th = dict(DEFAULT_TH)
    comp = {}
    try:
        with open(comp_path, encoding="utf-8") as f:
            comp = json.load(f)
            th.update(comp.get("board_severity_thresholds", {}))
    except FileNotFoundError:
        pass
    board = assess_board(inc, th)

    if args.json:
        print(json.dumps({k: board[k] for k in ("required", "m_met", "w_met", "req_n", "conclusion")},
                         ensure_ascii=False, indent=2))
        return

    iid = get(inc, "incident_id", "incident")
    title = get(inc, "title", "")
    lines = []
    A = lines.append
    A(f"# [경영진·이사회 보고] {iid}" + (f" — {title}" if title else ""))
    A("")
    A(f"> 문서 생성시각: {fmt_sec(now)}  ·  상태: 초안  ·  대상: {comp.get('company_name', '금융회사')}")
    A("> ⚠️ 자동 생성 초안입니다. 실제 보고·이사회 심의는 담당자가 수행합니다. 이사회 보고대상 판정은 권고이며 최종 판단은 CISO/이사회.")
    A("")
    A("## 이사회 보고대상 판정 (권고) — 조건별 상세 근거")
    A(render_rationale(board))
    A("")

    show_b = args.tier in ("b", "both") or (args.tier == "auto" and board["required"])
    show_a = args.tier in ("a", "both", "auto")
    if show_a:
        A(tier_a(inc, board))
        A("")
    if show_b:
        A(tier_b(inc, board))
    elif args.tier == "auto":
        A("> 이사회 보고서(Tier B)는 '비대상' 판정으로 생략. 조건별 근거는 위 '판정' 참조. 필요 시 `--tier b`로 강제 생성.")

    text = "\n".join(lines)
    save_and_print(text, args.incident, iid, "경영진이사회보고", args.out, args.stdout_only)


if __name__ == "__main__":
    main()
