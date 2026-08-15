#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
고객 장애 공지문 생성기.

입력: incident.json (+ company.json 회사 상수)
모드:
  realtime  : 장애 진행 중 실시간 공지 (대체 주문수단 안내 포함, '정상화' 문구 없음)
  recovery  : 복구 완료 공지 (원인 요약 + 보상절차 안내). resolved_at 없으면 거부.
채널 3종(각 모드별): 홈페이지/MTS 상세 · 알림톡(압축) · 요약 배너.

설계 원칙:
- ❗'정상화/복구' 문구 잠금: resolved_at(사고종료일시)이 없으면 recovery 공지를 만들지 않는다.
  (2025.10 '정상화 공지 후에도 미복구' 시점 불일치 재발 방지)
- ❗원인 누락 방지: recovery 공지는 사고원인을 반드시 포함한다(템플릿 재사용·원인 누락 문제 해결).
- 숫자·사실을 지어내지 않는다.
표준 라이브러리만 사용. 실제 발송은 하지 않는다(문안 생성만).
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


def hm(dt):
    return dt.astimezone(KST).strftime("%m월 %d일 %H:%M") if dt else "(시각 미입력)"


def fmt_sec(dt):
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S (KST)") if dt else "(미입력)"


def get(d, path, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur not in (None, "") else default


def services_phrase(inc):
    svcs = get(inc, "impact.affected_services", []) or []
    if svcs:
        return ", ".join(svcs)
    mkts = get(inc, "impact.affected_markets", []) or []
    return ", ".join(mkts) if mkts else "일부 서비스"


def cause_short(inc):
    """원인 한 줄 요약(고객 친화)."""
    detail = get(inc, "classification.failure_detail")
    rc = get(inc, "cause.root_cause", "")
    if get(inc, "cause.external_factor"):
        comp = get(inc, "cause.responsible_company")
        base = f"외부 연계 시스템({comp}) 장애" if comp else "외부 연계 시스템 장애"
        return base
    if detail:
        return detail
    if rc:
        return rc.split(".")[0][:40]
    return "내부 시스템 일시 오류"


def banner(text):
    return text


def alimtalk_len_note(text, target):
    n = len(text)
    flag = "✅" if n <= target else f"⚠️ 권장 {target}자 초과"
    return f"(알림톡 {n}자 {flag})"


def realtime_notice(inc, comp):
    cname = comp["company_name"]
    svc = services_phrase(inc)
    occurred = hm(parse_dt(get(inc, "timeline.occurred_at")))
    alt = " 또는 ".join(comp.get("alt_order_channels", [])) or f"고객센터({comp.get('customer_center_phone','')})"
    target = comp.get("alimtalk_char_target", 200)

    detail = (
        f"[안내] {svc} 이용 지연 현상 안내\n\n"
        f"안녕하세요, {cname}입니다.\n"
        f"{occurred}경부터 {svc} 이용 시 주문 체결이 지연·중단되는 현상이 발생하여 원인 확인 및 조치를 진행하고 있습니다.\n\n"
        f"· 영향 범위: {svc}\n"
        f"· 현재 상태: 조치 중\n"
        f"· 긴급 주문이 필요하신 경우: {alt}을(를) 이용해 주세요.\n\n"
        f"이용에 불편을 드려 진심으로 죄송합니다. 조치가 완료되는 대로 다시 안내드리겠습니다."
    )
    short = (
        f"[{cname}] {occurred}경부터 {svc} 주문 체결 지연이 발생해 조치 중입니다. "
        f"긴급 주문은 {comp.get('customer_center_phone','')}. 불편을 드려 죄송합니다."
    )
    bnr = f"⚠️ 현재 {svc} 주문 체결이 지연되고 있습니다. (원인 확인·조치 중)"
    return detail, short, bnr, target


def recovery_notice(inc, comp):
    cname = comp["company_name"]
    svc = services_phrase(inc)
    occurred = hm(parse_dt(get(inc, "timeline.occurred_at")))
    resolved = hm(parse_dt(get(inc, "timeline.resolved_at")))
    dis = get(inc, "impact.disruption_minutes")
    cs = comp.get("customer_center_phone", "")
    url = comp.get("compensation_info_url", "")
    req = " / ".join(comp.get("compensation_claim_required_fields", []))
    days = comp.get("compensation_notice_days_business", 14)
    cshort = cause_short(inc)
    target = comp.get("alimtalk_char_target", 200)
    dur = f"약 {dis}분" if dis is not None else "일시"

    detail = (
        f"[복구 완료] {svc} 이용 지연 현상 정상화 안내\n\n"
        f"안녕하세요, {cname}입니다.\n"
        f"{occurred} ~ {resolved}({dur}) 동안 발생했던 {svc} 주문 체결 지연 현상이 정상화되었습니다.\n\n"
        f"· 원인: {cshort}\n"
        f"· 영향 시간: {dur}\n\n"
        f"해당 시간 중 주문 미체결 등으로 피해를 입으신 경우 보상을 신청하실 수 있습니다.\n"
        f"· 신청: 고객센터({cs})\n"
        f"· 필요 정보: {req}\n"
        f"· 처리: 접수일로부터 {days}영업일 이내 보상 여부·금액 안내\n"
        f"· 자세히: {url}\n\n"
        f"이용에 불편을 드려 진심으로 죄송합니다."
    )
    short = (
        f"[{cname}] {svc} 주문 지연이 정상화되었습니다(원인: {cshort}). "
        f"피해 보상 신청은 고객센터({cs}). 자세히: {url}"
    )
    bnr = f"✅ {svc} 지연 현상이 정상화되었습니다. (피해 보상 신청 안내)"
    return detail, short, bnr, target


def emit(title, detail, short, bnr, target):
    return "\n".join([
        f"## {title}",
        "",
        "### 채널 1) 홈페이지 / MTS 공지 (상세)",
        "```text",
        detail,
        "```",
        "",
        f"### 채널 2) 알림톡 (압축) {alimtalk_len_note(short, target)}",
        "```text",
        short,
        "```",
        "",
        "### 채널 3) 요약 배너",
        "```text",
        bnr,
        "```",
    ])


def save_and_print(text, incident_path, incident_id, suffix, out, stdout_only):
    print(text)
    if not stdout_only:
        path = out or os.path.join(os.path.dirname(os.path.abspath(incident_path)), "out", f"{incident_id}_{suffix}.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"💾 저장: {path}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="고객 장애 공지문 생성기")
    ap.add_argument("incident", help="incident.json 경로")
    ap.add_argument("--mode", choices=["realtime", "recovery", "auto"], default="auto")
    ap.add_argument("--company", default=None, help="company.json 경로(기본: ../../shared/company.json)")
    ap.add_argument("--now", default=None, help="문서 생성 기준시각(ISO). 미지정 시 실제 현재시각")
    ap.add_argument("--out", default=None, help="저장 경로(미지정 시 <incident 폴더>/out/<id>_고객공지_<모드>.md)")
    ap.add_argument("--stdout-only", action="store_true", help="파일 저장 없이 화면 출력만")
    ap.add_argument("--no-validate", action="store_true", help="사전 검증 생략")
    args = ap.parse_args()

    with open(args.incident, encoding="utf-8") as f:
        inc = json.load(f)
    _validate.preflight_or_exit(inc, skip=args.no_validate)
    comp_path = args.company
    if not comp_path:
        comp_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "company.json")
    with open(comp_path, encoding="utf-8") as f:
        comp = json.load(f)

    now = parse_dt(args.now) or datetime.now(KST)
    incident_id = get(inc, "incident_id", "incident")
    title = get(inc, "title", "")

    resolved = get(inc, "timeline.resolved_at")
    mode = args.mode
    if mode == "auto":
        mode = "recovery" if resolved else "realtime"

    header = (
        f"# [고객 장애 공지문] {incident_id}" + (f" — {title}" if title else "") + "\n\n"
        f"> 문서 생성시각: {fmt_sec(now)}  ·  모드: {mode}  ·  상태: 초안  ·  대상: {comp['company_name']}\n"
        f"> ⚠️ 자동 생성 초안입니다. 실제 게시/알림톡 발송은 담당자가 수행합니다.\n"
    )

    # 복구 공지 잠금 가드
    if mode == "recovery" and not resolved:
        text = header + "\n".join([
            "",
            "> ❌ **복구 공지 생성 잠금**: `timeline.resolved_at`(사고종료일시)이 입력되지 않았습니다.",
            "> 실제 복구가 확인되기 전에는 '정상화' 공지를 만들 수 없습니다(시점 불일치 재발 방지).",
            "> 복구 확인 후 `resolved_at`을 입력하고 다시 실행하세요. 현재는 실시간(realtime) 공지만 가능합니다.",
        ])
        save_and_print(text, args.incident, incident_id, f"고객공지_{mode}", args.out, args.stdout_only)
        sys.exit(2)

    parts = [header]
    if mode == "recovery":
        cause = get(inc, "cause.root_cause") or get(inc, "classification.failure_detail")
        if not cause or "파악 중" in str(cause) or "미상" in str(cause):
            parts.append(
                "> ⚠️ **원인 미확정 경고**: 복구 공지에는 사고원인이 포함되어야 합니다.\n"
                "> 현재 원인이 비어있거나 '파악 중'입니다. 원인을 확정해 입력한 뒤 게시하세요. (아래 초안의 '원인'은 임시값)\n")
        detail, short, bnr, target = recovery_notice(inc, comp)
        parts.append(emit("복구 완료 공지", detail, short, bnr, target))
    else:
        if resolved:
            parts.append(
                "> ℹ️ 이미 복구된 장애입니다. 진행 중 실시간 공지가 필요하면 이 초안을, 복구 공지는 `--mode recovery`로 생성하세요.\n")
        detail, short, bnr, target = realtime_notice(inc, comp)
        parts.append(emit("실시간 장애 공지", detail, short, bnr, target))

    text = "\n".join(parts)
    save_and_print(text, args.incident, incident_id, f"고객공지_{mode}", args.out, args.stdout_only)


if __name__ == "__main__":
    main()
