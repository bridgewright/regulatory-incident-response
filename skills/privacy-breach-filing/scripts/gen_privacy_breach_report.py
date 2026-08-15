#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
개인정보·신용정보 유출 별도 통지·신고 산출물 생성기.

침해사고로 개인정보/신용정보가 유출된 경우, 전산장애 보고(금감원)와 '별도로':
- 개인정보보호법 제34조: 정보주체에게 지체 없이 통지 + 일정 규모 이상이면 보호위원회·전문기관(KISA)에 72시간 이내 신고.
- 신용정보법: 신용정보 누설 시 금융위/금감원 신고 등.

통지·신고 포함사항(개인정보보호법 제34조·시행령):
  ① 유출된 개인정보 항목  ② 유출 시점·경위  ③ 정보주체가 할 수 있는 피해 최소화 조치
  ④ 사업자 대응조치·피해구제절차  ⑤ 신고·상담 접수 부서·연락처

주의: 활성 조건 = security.personal_data_affected == true. 산출물 생성까지만(실제 신고는 사람).
신고 임계/세부 기준은 최신 법령으로 확인. 표준 라이브러리만 사용.
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


def get(d, path, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur not in (None, "") else default


def save_and_print(text, incident_path, incident_id, suffix, out, stdout_only):
    print(text)
    if not stdout_only:
        path = out or os.path.join(os.path.dirname(os.path.abspath(incident_path)), "out", f"{incident_id}_{suffix}.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"💾 저장: {path}", file=sys.stderr)


# 민감정보·고유식별정보 키워드 (개인정보보호법 시행령 제40조1항2호)
SENSITIVE_UNIQUE = ("주민등록번호", "여권번호", "운전면허", "외국인등록번호",
                    "건강", "진료", "생체", "유전", "사상", "신념", "정치", "노동조합", "성생활")


def assess_report_duty(inc):
    """감독기관 신고 의무 판정 (개인정보보호법 시행령 제40조①). 셋 중 하나면 72시간 내 신고 대상."""
    cnt = get(inc, "security.leaked_count")
    n = cnt if isinstance(cnt, int) else 0
    items = get(inc, "security.leaked_items", []) or []
    ext = get(inc, "cause.external_factor", False)
    cat = get(inc, "classification.incident_category")
    c1 = n >= 1000
    c2 = any(any(s in it for s in SENSITIVE_UNIQUE) for it in items)
    c3 = bool(ext) or cat == "침해사고"
    criteria = [
        {"no": "1호", "label": "1천명 이상 정보주체 유출",
         "met": c1, "detail": (f"{cnt:,}명" if isinstance(cnt, int) else "규모 미상 — 확인 필요")},
        {"no": "2호", "label": "민감정보·고유식별정보 유출 (규모 무관)",
         "met": c2, "detail": ("해당 항목 포함" if c2 else "해당 항목 없음")},
        {"no": "3호", "label": "외부 불법접근(침해)에 의한 유출 (규모 무관)",
         "met": c3, "detail": ("외부 침해행위 정황" if c3 else "내부 요인")},
    ]
    return {"required": c1 or c2 or c3, "criteria": criteria}


def main():
    ap = argparse.ArgumentParser(description="개인정보·신용정보 유출 통지·신고 생성기")
    ap.add_argument("incident")
    ap.add_argument("--company", default=None)
    ap.add_argument("--now", default=None)
    ap.add_argument("--out", default=None, help="저장 경로(미지정 시 <incident 폴더>/out/<id>_개인정보유출신고.md)")
    ap.add_argument("--stdout-only", action="store_true", help="파일 저장 없이 화면 출력만")
    ap.add_argument("--no-validate", action="store_true", help="사전 검증 생략")
    args = ap.parse_args()

    with open(args.incident, encoding="utf-8") as f:
        inc = json.load(f)
    _validate.preflight_or_exit(inc, skip=args.no_validate)
    comp_path = args.company or os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "company.json")
    with open(comp_path, encoding="utf-8") as f:
        comp = json.load(f)
    now = parse_dt(args.now) or datetime.now(KST)

    iid = get(inc, "incident_id", "incident")
    title = get(inc, "title", "")
    SUFFIX = "개인정보유출신고"

    L = []
    A = L.append
    A(f"# [개인정보·신용정보 유출 통지·신고] {iid}" + (f" — {title}" if title else ""))
    A("")
    A(f"> 문서 생성시각: {fmt_sec(now)}  ·  상태: 초안  ·  대상: {comp['company_name']}")
    A("> ⚠️ 자동 생성 초안입니다. 실제 통지·신고는 담당자가 수행합니다. 전산장애 금감원 보고(regulator-incident-report)와 별개입니다.")
    A("")

    if not get(inc, "security.personal_data_affected"):
        A("> ➖ **해당없음**: `security.personal_data_affected`가 false입니다.")
        A("> 개인정보·신용정보 유출이 없으면 이 산출물은 불필요합니다(전산장애 보고만 진행).")
        save_and_print("\n".join(L), args.incident, iid, SUFFIX, args.out, args.stdout_only)
        sys.exit(0)

    detected = parse_dt(get(inc, "detection.detected_at"))
    info_type = get(inc, "security.info_type", "개인정보")
    items = get(inc, "security.leaked_items", []) or []
    cnt = get(inc, "security.leaked_count")
    cs = comp.get("customer_center_phone", "")

    # 신고 의무·시한 판정 (개인정보보호법 제34조 / 시행령 제40조)
    duty = assess_report_duty(inc)
    A("## 1. 신고 의무·시한 판정 (개인정보보호법 제34조 / 시행령 제40조)")
    A("- **정보주체 통지**: 규모 무관 **지체 없이** 통지 (법 제34조①)")
    A(f"- **감독기관(보호위·KISA) 신고 대상**: **{'⭕ 신고 대상' if duty['required'] else '➖ 신고 대상 아님(통지는 필요)'}** — 시행령 제40조① (아래 1~3호 중 하나면 대상)")
    for c in duty["criteria"]:
        A(f"  - {c['no']} {c['label']}: {'✅ 충족' if c['met'] else '❌ 미충족'} ({c['detail']})")
    if detected:
        dl72 = detected + timedelta(hours=72)
        rem = dl72 - now
        sign = "남음" if rem.total_seconds() >= 0 else "경과(지연)"
        A(f"- **신고 기한**: 인지 후 **72시간 이내** → 마감 **{fmt(dl72)}** ({abs(rem.days)}일 {abs(rem.seconds)//3600}시간 {sign}) (시행령 제40조①)")
    else:
        A("- ⚠️ 사고인지일시 미입력 — 72시간 시한 계산 불가")
    # 신용정보법 이원 신고(개인정보위 신고와 분리 트랙)
    if info_type in ("신용정보", "둘 다"):
        cr_dl = f"(예: 인지+{'72시간' if not detected else fmt(detected + timedelta(hours=72))})"
        big = isinstance(cnt, int) and cnt >= 10000
        A("- **신용정보 포함 → 신용정보법 별도 신고(이원 신고)**: 개인정보보호법 신고(보호위·KISA, 72h)와 **분리된 트랙**으로 "
          "**신용정보법 제39조의4에 따라 금융위원회·금융감독원에 신고**"
          + (" — **1만명 이상**이므로 신고 대상 가능성 높음(지체 없이 신고, 5영업일 내 조치결과 보고 등)." if big
             else " — 규모·요건은 신용정보법 시행령으로 확인.") )
    # 침해사고면 정보통신망법 KISA 신고도 별개
    if get(inc, "classification.incident_category") == "침해사고" or get(inc, "cause.external_factor", False):
        A("- **침해사고 병행 신고**: 해킹·악성코드·DDoS 등 침해사고는 **정보통신망법 제48조의3에 따라 KISA/과기정통부에 인지 후 24시간 이내 신고**가 별도로 성립할 수 있음(개인정보 유출 여부와 무관, 금감원 보고·개인정보 신고로 갈음 안 됨 → regulator-incident-report 「1-1 병행 신고 점검」 참조).")
    A(f"- 유출 규모: {cnt:,}명" if isinstance(cnt, int) else "- 유출 규모: **미상 — 정확한 정보주체 수 확인 권장**(신고서·피해대응 정확도)")
    A("- ⚠️ 신고 임계·전문기관 세부 요건은 **최신 법령(개인정보보호법 시행령 제40조·신용정보법 제39조의4·정보통신망법 제48조의3)** 으로 재확인. `korean-law` MCP 교차확인 권장.")
    A("")

    # 정보주체 통지문 (5대 포함사항)
    A("## 2. [산출물 A] 정보주체 통지문 (개인정보보호법 제34조 5대 포함사항)")
    A("```text")
    A(f"[{comp['company_name']}] 개인정보 유출 안내")
    A("고객님께 개인정보 유출 사실을 안내드립니다. 불편과 우려를 끼쳐 진심으로 사과드립니다.")
    A(f"① 유출된 항목: {', '.join(items) if items else '(확인 필요)'}")
    A(f"② 유출 시점·경위: {fmt(parse_dt(get(inc,'timeline.occurred_at')))} / {get(inc,'cause.root_cause','(경위 확인 중)')}")
    A("③ 정보주체가 할 수 있는 조치: 비밀번호 변경, 보이스피싱 주의, 명의도용 모니터링 신청 등")
    A(f"④ 당사 대응 및 피해구제: {get(inc,'handling','(조치 진행 중)')} / 피해구제 절차 안내")
    A(f"⑤ 신고·상담 접수: 고객센터({cs}) / 개인정보 침해 신고(118, KISA)")
    A("```")

    # 감독기관 신고서 초안
    A("")
    A("## 3. [산출물 B] 감독기관 신고서 초안")
    A("| 항목 | 내용 |")
    A("|---|---|")
    rows = [
        ("근거법", "개인정보보호법 제34조" + (" + 신용정보법" if info_type in ("신용정보", "둘 다") else "")),
        ("사고 인지일시", fmt(detected)),
        ("유출 정보 종류", info_type),
        ("유출 항목", ", ".join(items) if items else "(확인 필요)"),
        ("유출 규모(정보주체 수)", f"{cnt:,}명" if isinstance(cnt, int) else "(미상)"),
        ("유출 경위", get(inc, "cause.root_cause", "(파악 중)")),
        ("피해 최소화 조치", get(inc, "handling", "(진행 중)")),
        ("재발방지 대책", get(inc, "measures", "(수립 중)")),
        ("정보주체 통지 여부·방법", "(기재 필요: 통지 일시/방법)"),
    ]
    for k, v in rows:
        A(f"| {k} | {str(v).replace(chr(10),' ')} |")
    A("")
    A("> 이 산출물은 전산장애 금감원 보고(스킬1)와 **별개**입니다. 둘 다 필요합니다.")

    save_and_print("\n".join(L), args.incident, iid, SUFFIX, args.out, args.stdout_only)


if __name__ == "__main__":
    main()
