#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
대응 타임라인·체크리스트 (오케스트레이터).

호출할 때마다 incident.json을 읽어 각 보고/공지/산출물의:
  - 규제 시한까지 남은 시간(D-counter)
  - 현재 상태(미생성/초안/제출완료/해당없음) — incident.json의 reporting{}에서
  - 어떤 스킬로 만드는지
를 대시보드로 보여주고 '지금 가장 급한 것'을 강조한다.

상태는 incident.json의 reporting{} 에 누적된다(스킬 1·2·3·5가 갱신하거나 수동 갱신).
표준 라이브러리만 사용.
"""
import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone

# 사고유형 정규목록의 단일 원천(fss·management와 공용)
_FM = os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "scripts", "form_mapping.py")
_spec = importlib.util.spec_from_file_location("form_mapping", _FM)
fm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm)

KST = timezone(timedelta(hours=9))


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def fmt_sec(dt):
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S (KST)") if dt else "(미입력)"


def add_business_days(start, n, holidays=None):
    holidays = holidays or set()
    d, added = start, 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.astimezone(KST).strftime("%Y-%m-%d") not in holidays:
            added += 1
    return d


def get(d, path, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur not in (None, "") else default


def remaining(deadline, now):
    if deadline is None:
        return None, "—"
    delta = deadline - now
    total = int(delta.total_seconds())
    sign = "남음" if total >= 0 else "경과"
    a = abs(total)
    d, rem = divmod(a, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    label = (f"{d}일 " if d else "") + f"{h}시간 {m}분 {sign}"
    return total, label


def status_of(inc, key):
    st = get(inc, f"reporting.{key}.status", "미생성")
    return st


def save_and_print(text, incident_path, incident_id, suffix, out, stdout_only):
    print(text)
    if not stdout_only:
        path = out or os.path.join(os.path.dirname(os.path.abspath(incident_path)), "out", f"{incident_id}_{suffix}.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"💾 저장: {path}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="대응 타임라인·체크리스트")
    ap.add_argument("incident")
    ap.add_argument("--company", default=None)
    ap.add_argument("--now", default=None)
    ap.add_argument("--out", default=None, help="저장 경로(미지정 시 <incident 폴더>/out/<id>_대응타임라인.md)")
    ap.add_argument("--stdout-only", action="store_true", help="파일 저장 없이 화면 출력만")
    args = ap.parse_args()

    with open(args.incident, encoding="utf-8") as f:
        inc = json.load(f)
    comp_path = args.company or os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "company.json")
    with open(comp_path, encoding="utf-8") as f:
        comp = json.load(f)
    now = parse_dt(args.now) or datetime.now(KST)
    bdays = comp.get("compensation_notice_days_business", 14)
    holidays = set(comp.get("business_holidays", []))

    detected = parse_dt(get(inc, "detection.detected_at"))
    resolved = parse_dt(get(inc, "timeline.resolved_at"))

    # 보상 통지기한: 최초 접수일 기준
    claim_dates = [parse_dt(o.get("claim_received_at")) for o in (get(inc, "orders", []) or []) if o.get("claim_received_at")]
    first_claim = min(claim_dates) if claim_dates else None

    fss_initial_dl = (detected + timedelta(hours=24)) if detected else None
    comp_dl = add_business_days(first_claim, bdays, holidays) if first_claim else None
    # 중간보고: 미복구로 조치가 2개월 이상 지속될 때 인지일+2개월이 1차 시한(근사: 60일)
    fss_interim_dl = None
    if detected and resolved is None:
        fss_interim_dl = detected + timedelta(days=60)

    # 병행 신고(금감원 보고로 갈음 안 됨) — 조건부 시한
    is_chimhae = fm.selected_category(inc) == "침해사고"
    pii = get(inc, "security.personal_data_affected", False)
    kisa_dl = (detected + timedelta(hours=24)) if (detected and is_chimhae) else None
    privacy_dl = (detected + timedelta(hours=72)) if (detected and pii) else None

    # (보고종류, 기한, 상태키, 담당스킬, 조건설명)
    items = [
        ("금감원 최초보고", fss_initial_dl, "fss_initial", "regulator-incident-report", "인지+24h"),
        ("금감원 중간보고", fss_interim_dl, "fss_interim", "regulator-incident-report", "미복구 2개월 시 인지+2월 / 이후 매6월"),
        ("금감원 종결보고", None, "fss_final", "regulator-incident-report", "복구·재발방지·배상 완료 후"),
    ]
    if is_chimhae:
        items.append(("정보통신망법 침해신고(KISA/과기정통부)", kisa_dl, "kisa_report", "정보통신망법(사내법무 확인)", "인지+24h·금감원 보고와 별개(§48조의3)"))
    if pii:
        items.append(("개인정보 유출신고", privacy_dl, "privacy_report", "privacy-breach-filing", "인지+72h·개인정보보호법 시행령 §40"))
    items += [
        ("고객 실시간 공지", None, "customer_realtime", "customer-outage-notice", "발생 즉시"),
        ("고객 복구 공지", None, "customer_recovery", "customer-outage-notice", "복구 확인 후"),
        ("보상 통지", comp_dl, "compensation_notice", "컴플라이언스(내부정산)", f"접수+{bdays}영업일"),
        ("경영진 속보", None, "exec_brief", "exec-board-report", "선언 즉시"),
        ("이사회 보고", None, "board_report", "exec-board-report", "중대 시(exec-board-report 판정)"),
    ]

    iid = get(inc, "incident_id", "incident")
    title = get(inc, "title", "")
    R = []
    A = R.append

    A(f"# [대응 타임라인·체크리스트] {iid}" + (f" — {title}" if title else ""))
    A("")
    A(f"> 문서 생성시각(기준): {fmt_sec(now)}  ·  상태: 초안  ·  대상: {comp['company_name']}")
    A("> 남은 시간(D-counter)은 위 기준시각으로 계산됩니다.")
    A("")
    A(f"- 인지 {fmt_sec(detected) if detected else '(미입력)'}"
      f" / 종료 {fmt_sec(resolved) if resolved else '(미복구)'}"
      f" / 기준현재 {fmt_sec(now)}")
    A("")

    A("| 보고/산출물 | 상태 | 시한 | 남은시간 | 스킬 | 조건 |")
    A("|---|---|---|---|---|---|")

    urgent = []
    for name, dl, key, skill, cond in items:
        st = status_of(inc, key)
        secs, label = remaining(dl, now)
        dl_disp = dl.astimezone(KST).strftime("%m-%d %H:%M") if dl else "—"
        icon = {"제출완료": "✅", "초안": "📝", "해당없음": "➖"}.get(st, "⬜")
        # 긴급 판단: 미완료 + 기한 임박/경과
        if dl and st not in ("제출완료", "해당없음") and secs is not None and secs < 6 * 3600:
            flag = "🔴"
            urgent.append((name, label, skill))
        elif dl and st not in ("제출완료", "해당없음") and secs is not None and secs < 24 * 3600:
            flag = "🟠"
        else:
            flag = ""
        A(f"| {flag} {name} | {icon}{st} | {dl_disp} | {label} | {skill} | {cond} |")

    A("")
    A("## 지금 가장 급한 것")
    if urgent:
        for name, label, skill in sorted(urgent, key=lambda x: x[1]):
            A(f"- 🔴 **{name}** — {label} → `{skill}` 실행")
    else:
        # 미완료 중 가장 임박한 기한
        pend = [(n, remaining(dl, now)[0], remaining(dl, now)[1], s)
                for n, dl, k, s, c in items if dl and status_of(inc, k) not in ("제출완료", "해당없음")]
        pend = [p for p in pend if p[1] is not None]
        if pend:
            n, _, label, s = min(pend, key=lambda x: x[1])
            A(f"- 다음 마감: **{n}** — {label} → `{s}`")
        else:
            A("- 시한 임박 항목 없음. 복구·접수 진행 상황에 따라 갱신됨.")

    A("")
    A("> 상태는 incident.json의 `reporting{}`에서 읽음. 각 스킬 실행 후 상태를 갱신하면 정확해집니다.")

    text = "\n".join(R)
    save_and_print(text, args.incident, iid, "대응타임라인", args.out, args.stdout_only)


if __name__ == "__main__":
    main()
