#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
금감원 정보기술부문 사고보고서 생성기 (전자금융감독규정 시행세칙 제7조의4 / 별지 제2호서식).

입력: incident.json (shared/incident.schema.json 구조)
출력: 자기완결적 사고보고서 (Markdown). 담당자·유관자가 이 문서만 읽어도 상황을 파악하도록:
  - 문서 생성시각(초단위)·보고단계·상태 메타
  - 한눈 요약(Executive Summary)
  - 보고 대상 판정 / 보고 시한(생성시각 기준 남은 시간, 초단위)
  - 사고 타임라인 / 영향 상세 / 원인 상세 / 대응 현황
  - 필수항목 점검 & 다음 조치
  - [제출물] EFARS 입력용 필드블록 + 첨부용 별지 제2호서식
산출물은 항상 .md 파일로 저장한다(기본: <incident.json 폴더>/out/<id>_금감원_<단계>보고.md).
결정적(rule-based) 부분만 처리하며 숫자·사실을 지어내지 않는다. EFARS 자동 제출은 하지 않는다.
표준 라이브러리만 사용.
"""
import argparse
import importlib.util as _il
import json
import os
import sys
from datetime import datetime, timedelta, timezone

# 공통 사전 검증(단독 호출 시에도 자동 검증)
_VD = os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "scripts", "validate_incident.py")
_vspec = _il.spec_from_file_location("validate_incident", _VD)
_validate = _il.module_from_spec(_vspec)
_vspec.loader.exec_module(_validate)

KST = timezone(timedelta(hours=9))
STAGE_LABEL = {"initial": "최초", "interim": "중간", "final": "종결"}


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def fmt_min(dt):
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M (KST)") if dt else "(미입력)"


def fmt_sec(dt):
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S (KST)") if dt else "(미입력)"


def fmt_remaining(delta):
    total = int(delta.total_seconds())
    sign = "남음" if total >= 0 else "경과(지연)"
    a = abs(total)
    d, r = divmod(a, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    head = f"{d}일 " if d else ""
    return f"{head}{h}시간 {m}분 {s}초 {sign}"


def minutes_between(a, b):
    if not a or not b:
        return None
    return int((b - a).total_seconds() // 60)


def get(d, path, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur not in (None, "") else default


# --------------------------------------------------------------------------
# 판정 로직 (시행세칙 제7조의4 ①②)
# --------------------------------------------------------------------------
def assess_trigger(inc):
    cat = get(inc, "classification.incident_category")
    dis = get(inc, "impact.disruption_minutes", 0) or 0
    users_raw = get(inc, "impact.affected_users_count")
    users = users_raw if isinstance(users_raw, int) else 0
    users_known = isinstance(users_raw, int)
    users_disp = f"{users:,}명" if users_known else "미상(확인 필요)"
    amount = get(inc, "impact.incident_amount_krw")
    single_branch = get(inc, "impact.single_branch_only", False)
    public_web = get(inc, "impact.public_webserver_only", False)

    reasons, excluded = [], []
    reportable = False
    if cat == "전산장애사고":
        if dis >= 30:
            reportable = True
            reasons.append(f"①1-가: 전자금융업무 지연·중단 {dis}분 (≥30분)")
        if dis >= 10 and users >= 10000:
            reportable = True
            reasons.append(f"①1-나: 지연·중단 {dis}분(≥10분) + 영향 이용자 {users:,}명 (≥1만명)")
        if not reasons:
            tail = " (⚠️ 영향 이용자수 미확인 — 확정 시 '10분+1만명' 요건 재판정 필요)" if (not users_known and dis >= 10) else ""
            reasons.append(f"전산장애이나 시간기준 미달(중단 {dis}분, 이용자 {users_disp}) → 현재 정보로는 보고대상 아님{tail}")
        if single_branch:
            excluded.append("②1: 1개 영업점에 국한된 중단·지연 → 보고 제외 대상")
        if public_web:
            excluded.append("②2: 단순 정보제공 공개 웹서버 등 금융서비스 무관 장애 → 보고 제외 대상")
    elif cat == "침해사고":
        reportable = True
        reasons.append("①3: 전자적 침해행위로 인한 시스템 사고 또는 이용자 금전피해 통지")
    elif cat == "전자금융사기사고":
        reportable = True
        reasons.append("①4(법 제9조1항) 관련 사고")
        if amount is not None and amount < 1_000_000:
            excluded.append("②3: 법9조1항1·3호 사고 중 사고금액 100만원 미만 → 보고 제외 가능")

    batch_note = None
    if cat == "전자금융사기사고" and amount is not None and amount < 300_000_000:
        batch_note = "법9조1항1호 사고 중 사고금액 3억원 미만 → 매월분을 익월 15일까지 별첨2로 일괄보고 가능"

    return {"reportable": reportable and not excluded, "reasons": reasons,
            "excluded": excluded, "batch_note": batch_note}


CORE = [
    ("incident_id", "장애 식별자"),
    ("detection.first_recognizer", "최초 인지 주체"),
    ("detection.detected_at", "사고인지일시"),
    ("timeline.occurred_at", "사고발생일시"),
    ("classification.incident_category", "사고유형"),
    ("impact.disruption_minutes", "지연·중단 시간"),
    ("impact.affected_users_count", "사고 영향 이용자수"),
    ("cause.root_cause", "사고원인"),
    ("system_name", "사고발생 업무(시스템)명"),
    ("description", "사고내용(현상 및 결과)"),
]
EXTRA = {
    "interim": [("timeline.events", "대응 타임라인(시각별 action)")],
    "final": [("timeline.resolved_at", "사고종료일시"), ("handling", "처리결과"), ("measures", "대책(재발방지)")],
}


def check_fields(inc, stage):
    missing, soft = [], []
    for path, label in list(CORE) + EXTRA.get(stage, []):
        if get(inc, path) is None:
            missing.append(f"{label} (`{path}`)")
    rc = get(inc, "cause.root_cause", "")
    if rc and ("파악 중" in rc or "미상" in rc or "추정" in rc):
        soft.append("사고원인이 '파악 중/추정' 상태 — 중간·종결보고 전 확정 필요")
    if get(inc, "cause.external_factor") and not get(inc, "cause.responsible_company"):
        soft.append("외부요인 장애인데 '사고 원인 회사명' 미입력 — 파급영향 칸 보완")
    if get(inc, "timeline.resolved_at") is None:
        soft.append("사고종료일시 미입력(대응 중) — 고객 '정상화' 공지 및 종결보고 잠금 상태")
    return missing, soft


# --------------------------------------------------------------------------
# EFARS 제출물 (별지 제2호서식)
# --------------------------------------------------------------------------
def render_efars_block(inc, stage):
    cat = get(inc, "classification.incident_category", "(미입력)")
    sub = get(inc, "classification.failure_subtype")
    sub_detail = get(inc, "classification.failure_detail")
    sago_type = cat + (f" / {sub}" if sub else "") + (f" ({sub_detail})" if sub_detail else "")
    ext = get(inc, "cause.external_factor")
    pagup = []
    if get(inc, "cause.affected_other_firms"):
        pagup.append(f"영향받은 금융회사 등: {get(inc,'cause.affected_other_firms')}")
    pagup.append(f"외부요인으로 인한 장애: {'예 / 사고 원인 회사명: ' + str(get(inc,'cause.responsible_company','(미입력)')) if ext else '아니오'}")
    victims = get(inc, "victims", []) or []
    vict_str = "; ".join(f"{v.get('name','')}/{v.get('birth','')}/{v.get('damage_amount_krw','')}원" for v in victims) or "(해당 없음)"
    users = get(inc, "impact.affected_users_count")
    users_str = f"{users:,}명" if isinstance(users, int) else "(미입력)"
    rows = [
        ("보고형태", f"□최초 □중간 □종결 → [{STAGE_LABEL.get(stage,'?')}]"),
        ("사고유형", sago_type),
        ("최초 인지", get(inc, "detection.first_recognizer", "(미입력)")),
        ("사고인지일시", fmt_min(parse_dt(get(inc, "detection.detected_at")))),
        ("사고발생일시", fmt_min(parse_dt(get(inc, "timeline.occurred_at")))),
        ("사고종료일시", fmt_min(parse_dt(get(inc, "timeline.resolved_at")))),
        ("피해자 정보 및 피해금액", vict_str),
        ("배상금액 / 배상인원수", f"{get(inc,'compensation.total_amount_krw','(미정)')} / {get(inc,'compensation.count','(미정)')}"),
        ("사고금액 / 사고 영향 이용자수", f"{get(inc,'impact.incident_amount_krw','(미상)')} / {users_str}"),
        ("사고발생 업무(시스템)명", get(inc, "system_name", "(미입력)")),
        ("사고내용(현상 및 결과)", get(inc, "description", "(미입력)")),
        ("사고원인(변경시점 및 사유 등)", get(inc, "cause.root_cause", "(미입력)")),
        ("파급영향", " / ".join(pagup)),
        ("처리결과", get(inc, "handling", "(미입력)")),
        ("대책", get(inc, "measures", "(미입력)")),
    ]
    return "```text\n" + "\n".join(f"{k} : {v}" for k, v in rows) + "\n```"


# --------------------------------------------------------------------------
# 보고서 렌더링 (자기완결형)
# --------------------------------------------------------------------------
def build_report(inc, stage, now):
    R = []
    A = R.append
    iid = get(inc, "incident_id", "?")
    title = get(inc, "title", "")
    occurred = parse_dt(get(inc, "timeline.occurred_at"))
    detected = parse_dt(get(inc, "detection.detected_at"))
    resolved = parse_dt(get(inc, "timeline.resolved_at"))
    dis = get(inc, "impact.disruption_minutes")
    users = get(inc, "impact.affected_users_count")
    svcs = ", ".join(get(inc, "impact.affected_services", []) or get(inc, "impact.affected_markets", []) or ["(미입력)"])
    trig = assess_trigger(inc)
    missing, soft = check_fields(inc, stage)
    stage_ko = STAGE_LABEL.get(stage, "?")
    users_disp = f"{users:,}명" if isinstance(users, int) else "(미입력)"

    if resolved:
        status = f"✅ 복구 완료 (종료 {fmt_min(resolved)})"
    else:
        elapsed = minutes_between(occurred, now)
        status = "🔴 대응 중 (진행 중" + (f", 발생 후 {elapsed}분 경과" if elapsed is not None else "") + ")"

    A(f"# [금감원 사고보고서 · {stage_ko}보고] {iid}" + (f" — {title}" if title else ""))
    A("")
    A(f"> **문서 생성시각(기준)**: {fmt_sec(now)}  ·  **보고 단계**: {stage_ko}보고  ·  **상태**: 초안(EFARS 미제출)  ·  **대상**: 설정된 금융회사")
    A("> ⚠️ 본 문서는 자동 생성 **초안**입니다. EFARS(전자금융사고대응시스템) 실제 제출은 비상연락 담당자가 수행합니다. 근거: 전자금융감독규정 제37조의5·시행세칙 제7조의4.")
    A("")

    initial_dl = (detected + timedelta(hours=24)) if detected else None
    A("## 0. 한눈 요약 (Executive Summary)")
    A(f"- **무슨 일이**: {get(inc,'description','(미입력)')}")
    gap = minutes_between(occurred, detected)
    A(f"- **언제**: 발생 {fmt_min(occurred)} · 인지 {fmt_min(detected)}" + (f" (발생→인지 {gap}분)" if gap is not None else ""))
    A(f"- **현재 상태**: {status}")
    A(f"- **영향**: {svcs} / 이용자 {users_disp}" + (f" / 중단 {dis}분" if dis is not None else ""))
    A(f"- **원인**: {get(inc,'cause.root_cause','(파악 중)')}")
    A(f"- **보고 의무**: {'⭕ 대상' if trig['reportable'] else '❌ 비대상/제외'} — {trig['reasons'][0] if trig['reasons'] else ''}")
    if initial_dl:
        A(f"- **최초보고 마감**: {fmt_sec(initial_dl)}  →  **{fmt_remaining(initial_dl - now)}** (문서 생성시각 기준)")
    A("")

    A("## 1. 보고 대상 판정 (시행세칙 제7조의4 ①②)")
    A(f"- **판정: {'⭕ 보고 대상' if trig['reportable'] else '❌ 비대상/제외'}**")
    for r in trig["reasons"]:
        A(f"  - {r}")
    for e in trig["excluded"]:
        A(f"  - 🚫 {e}")
    if trig["batch_note"]:
        A(f"  - ℹ️ {trig['batch_note']}")
    A("")

    # 병행 신고 점검 — 금감원 전자금융 보고로 '갈음되지 않는' 별도 법정 신고
    cat = get(inc, "classification.incident_category")
    pii = get(inc, "security.personal_data_affected", False)
    ext_attack = get(inc, "cause.external_factor", False)
    dmg = get(inc, "security.attack_damage") or ""
    money_harm = ("금전" in dmg or "손실" in dmg or bool(get(inc, "victims")))
    if cat in ("침해사고", "전자금융사기사고") or pii:
        A("## 1-1. ⚠️ 병행 신고·후속 트랙 점검 (금감원 보고로 갈음되지 않는 별도 의무)")
        if cat == "침해사고":
            A("- 🔴 **정보통신망법 제48조의3(침해사고 신고)**: 해킹·DDoS·악성코드 등 침해사고는 **KISA(한국인터넷진흥원)/과학기술정보통신부에 인지 후 24시간 이내 신고** 대상일 수 있음. **전자금융감독규정 금감원 보고로 자동 갈음되지 않음**(개인정보 유출이 없어도 성립 가능).")
            A(f"  - 신고 시한(참고): 인지 후 24시간 → **{fmt_sec((detected + timedelta(hours=24)) if detected else None)}**")
            A("  - ⚠️ 증권사 포섭 여부는 서비스 형태에 따라 법적 판단 필요 → **사내 법무·정보보호책임자 확인 후 신고 여부 확정**.")
        if pii:
            A("- 🔴 **개인정보보호법 제34조·시행령 제40조**: 개인정보·신용정보 유출 동반 → 정보주체 통지(지체 없이) + 감독기관(보호위·KISA) **72시간 이내 신고**. → **`privacy-breach-filing` 스킬로 별도 산출물 생성**.")
        elif cat == "침해사고" and not ext_attack:
            A("- ℹ️ 개인정보 유출 미확인 — 유출 정황 확인 시 개인정보보호법 신고(72h)도 병행 대상.")
        if cat == "침해사고" and money_harm:
            A("- 🟠 **전자금융거래법 제9조(금융회사 배상책임)**: 해킹 등 **무권한 전자금융거래**로 이용자 금전피해 발생 시 회사 배상책임·이용자 통지 별도 검토(범위밖 트랙 — 사내 배상절차 확인).")
        if cat == "전자금융사기사고":
            A("- 🟠 **통신사기피해환급법**: 전자금융사기(피싱·파밍 등) 피해자에 대한 **지급정지·피해자 통지·채권소멸 공고** 등 별도 트랙 존재(본 플러그인 범위밖 — 사내 전담절차 확인).")
        A("- ✅ 위 신고·통지는 **금감원 사고보고(본 문서)와 병행**한다. 어느 하나로 다른 하나를 대체하지 않는다.")
        A("")

    A("## 2. 보고 시한 (문서 생성시각 기준)")
    A(f"- **기준시각(문서 생성)**: {fmt_sec(now)}")
    if initial_dl:
        rem = initial_dl - now
        A(f"- **최초보고 마감**: {fmt_sec(initial_dl)} (인지 후 24시간)")
        A(f"- **남은 시간**: {fmt_remaining(rem)}")
        if rem.total_seconds() < 0:
            A("  - ❗ **24시간 경과** — 지연 사유를 보고서에 기재해 제출")
        elif rem.total_seconds() < 2 * 3600:
            A("  - 🔴 **마감 임박(2시간 이내)** — 최우선 제출")
    else:
        A("- ⚠️ 사고인지일시 미입력 — 24시간 시한 계산 불가")
    if stage in ("interim", "final"):
        A("- 중간보고: 보완 필요 시 즉시. 조치완료까지 2개월 이상 소요 시 인지일로부터 2개월 이내 + **종결 시까지 매 6개월마다**")
    if stage == "final":
        A(f"- 종결보고: 사고종료 {fmt_min(resolved)} — 원인·조치·재발방지(+배상 시 배상조치) 완료 후 제출")
    A("")

    A("## 3. 사고 타임라인")
    A("| 시각 | 발생 후 경과 | 이벤트 |")
    A("|---|---|---|")

    def elapsed_str(dt):
        m = minutes_between(occurred, dt)
        return f"+{m}분" if m is not None else "-"
    if occurred:
        A(f"| {fmt_min(occurred)} | +0분 | 사고 발생 |")
    if detected:
        A(f"| {fmt_min(detected)} | {elapsed_str(detected)} | 최초 인지 ({get(inc,'detection.first_recognizer','')}) |")
    for ev in (get(inc, "timeline.events", []) or []):
        edt = parse_dt(ev.get("at"))
        A(f"| {fmt_min(edt)} | {elapsed_str(edt)} | {ev.get('action','')} |")
    if resolved:
        A(f"| {fmt_min(resolved)} | {elapsed_str(resolved)} | 사고 종료(정상화) |")
    else:
        A(f"| (진행 중) | +{minutes_between(occurred, now)}분 | 대응 중 — 미복구 |")
    A("")

    A("## 4. 영향 상세")
    A("| 구분 | 내용 |")
    A("|---|---|")
    A(f"| 영향 서비스 | {svcs} |")
    A(f"| 영향 시장/상품 | {', '.join(get(inc,'impact.affected_markets',[]) or ['-'])} |")
    A(f"| 지연·중단 시간 | {dis}분{' (진행 중, 계속 증가)' if not resolved and dis is not None else ''} |")
    A(f"| 영향 이용자수 | {users_disp} |")
    A(f"| 사고금액 | {get(inc,'impact.incident_amount_krw','(미상)')} |")
    A(f"| 1개 영업점 국한 / 공개웹서버 | {'예' if get(inc,'impact.single_branch_only') else '아니오'} / {'예' if get(inc,'impact.public_webserver_only') else '아니오'} (보고 제외 판정용) |")
    A("")

    A("## 5. 원인 상세")
    ext = get(inc, "cause.external_factor")
    A(f"- **원인 구분**: {'외부요인 장애' if ext else '내부요인'}" + (f" — {get(inc,'classification.failure_subtype','')}" if get(inc, 'classification.failure_subtype') else ""))
    if ext:
        A(f"- **외부 원인 회사**: {get(inc,'cause.responsible_company','(미입력)')}")
        A(f"- **타사 동시영향(파급)**: {get(inc,'cause.affected_other_firms','(확인 필요)')}")
    A(f"- **상세 원인**: {get(inc,'cause.root_cause','(파악 중)')}")
    if get(inc, "classification.failure_detail"):
        A(f"- **분류 근거**: {get(inc,'classification.failure_detail')}")
    A("")

    A("## 6. 대응 현황 및 재발방지")
    A(f"- **처리결과(조치)**: {get(inc,'handling') or '(작성 필요 — 대응 진행 중)'}")
    A(f"- **재발방지 대책**: {get(inc,'measures') or '(작성 필요 — 종결보고 전 확정)'}")
    A("")

    A("## 7. 필수항목 점검 & 다음 조치")
    if missing:
        A("- ❗ **누락(보고 전 입력 필요)**:")
        for m in missing:
            A(f"  - {m}")
    else:
        A("- ✅ 단계별 필수항목 모두 입력됨")
    if soft:
        A("- ⚠️ **보완 권고**:")
        for s in soft:
            A(f"  - {s}")
    nxt = {"initial": "복구 후 → 종결보고(`--stage final`)로 원인·처리결과·재발방지·배상 확정. 2개월 이상 지속 시 중간보고.",
           "interim": "종결 시 → 종결보고로 마무리.",
           "final": "제출 후 사후관리 종료. 배상액 산정·지급은 사내 OMS/정산 시스템에서 처리."}.get(stage, "")
    A(f"- ➡️ **다음 조치**: {nxt}")
    A("- ➡️ **제출 주체**: 비상연락 담당자(CISO 조직)가 EFARS에 [제출물 A]를 입력하거나 [제출물 B]를 첨부.")
    A("")

    A("## 8. [제출물 A] EFARS 입력용 필드 블록")
    A("> EFARS 화면 대응 필드에 입력/복붙. (자동 제출 아님)")
    A("")
    A(render_efars_block(inc, stage))
    A("")

    A("## 9. [제출물 B] 첨부용 별지 제2호서식 (별첨1)")
    A("| 항목 | 내용 |")
    A("|---|---|")
    b_rows = [
        ("보고형태", f"{stage_ko}보고"),
        ("사고유형", f"{get(inc,'classification.incident_category','')} / {get(inc,'classification.failure_subtype','')}".strip(" /")),
        ("최초 인지 / 인지일시", f"{get(inc,'detection.first_recognizer','')} / {fmt_min(detected)}"),
        ("사고발생 / 종료일시", f"{fmt_min(occurred)} / {fmt_min(resolved)}"),
        ("사고금액 / 영향 이용자수", f"{get(inc,'impact.incident_amount_krw','(미상)')} / {users if users is not None else '(미입력)'}"),
        ("사고발생 업무(시스템)명", get(inc, "system_name", "")),
        ("사고내용(현상 및 결과)", get(inc, "description", "")),
        ("사고원인", get(inc, "cause.root_cause", "")),
        ("파급영향(외부요인/원인회사)", f"외부요인={'예' if ext else '아니오'} / 원인회사={get(inc,'cause.responsible_company','-')} / 타사영향={get(inc,'cause.affected_other_firms','-')}"),
        ("처리결과", get(inc, "handling") or "(작성 필요)"),
        ("대책(재발방지)", get(inc, "measures") or "(작성 필요)"),
    ]
    for k, v in b_rows:
        A(f"| {k} | {str(v).replace(chr(10),' ')} |")
    A("")
    A("---")
    A(f"*생성: kakaopaysec-incident-response/regulator-incident-report · 기준시각 {fmt_sec(now)} · 이 문서는 초안이며 수치 중 `[추정]`·`(미입력)`은 제출 전 확정 필요.*")
    return "\n".join(R)


def main():
    ap = argparse.ArgumentParser(description="금감원 사고보고서 생성기 (별지 제2호서식)")
    ap.add_argument("incident", help="incident.json 경로")
    ap.add_argument("--stage", choices=["initial", "interim", "final"], default="initial")
    ap.add_argument("--now", default=None, help="기준 현재시각(ISO). 미지정 시 실제 현재시각")
    ap.add_argument("--out", default=None, help="저장 경로(미지정 시 <incident 폴더>/out/<id>_금감원_<단계>보고.md)")
    ap.add_argument("--stdout-only", action="store_true", help="파일 저장 없이 화면 출력만")
    ap.add_argument("--no-validate", action="store_true", help="사전 검증 생략")
    args = ap.parse_args()

    with open(args.incident, encoding="utf-8") as f:
        inc = json.load(f)
    _validate.preflight_or_exit(inc, skip=args.no_validate)
    now = parse_dt(args.now) or datetime.now(KST)

    report = build_report(inc, args.stage, now)

    if not args.stdout_only:
        iid = get(inc, "incident_id", "incident")
        out_path = args.out or os.path.join(
            os.path.dirname(os.path.abspath(args.incident)), "out",
            f"{iid}_금감원_{STAGE_LABEL.get(args.stage,'')}보고.md")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"💾 보고서 저장: {out_path}", file=sys.stderr)

    print(report)


if __name__ == "__main__":
    main()
