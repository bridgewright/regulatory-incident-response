#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""별지 제2호서식 체크박스 매핑의 단일 원천(single source of truth).

md 생성기(generate_fss_report.py)·PDF 생성기(generate_fss_pdf.py)·
정합성 검증기(verify_fss_consistency.py)가 모두 이 모듈을 import 해
"사고 데이터 → 서식 항목" 규칙을 한 곳에서만 정의한다(중복 제거).

세부유형·공격유형을 추가/변경하려면 이 파일의 옵션 리스트만 고치면
md·PDF·검증기가 자동으로 동일하게 따라간다. 표준 라이브러리만 사용.
"""

STAGE_KO = {"initial": "최초", "interim": "중간", "final": "종결"}
INCIDENT_CATEGORIES = ["전산장애사고", "침해사고", "전자금융사기사고"]

# 전산장애 세부유형: (스키마 정규값, 서식 표시 라벨)
FAILURE_SUBTYPE_OPTIONS = [
    ("업무처리 프로그램 오류", "업무처리 프로그램 오류 (로직/데이터 오류)"),
    ("시스템 장애", "시스템 장애 (서버·네트워크·스토리지·보안장비 / OS·DBMS·미들웨어·WAS 등)"),
    ("시설·설비 장애", "시설·설비 장애 (전원차단·통신회선 훼손 등)"),
    ("외부요인으로 인한 장애", "외부요인으로 인한 장애 (클라우드·통신·제휴업체 등)"),
    ("미정(파악 중)", "미정(파악 중)"),
]
FAILURE_SUBTYPES = [k for k, _ in FAILURE_SUBTYPE_OPTIONS]

FRAUD_OPTIONS = [  # 전자금융사기 세부 (표시라벨, 매칭 키워드들)
    ("피싱/파밍(인터넷)", ("인터넷",)),
    ("피싱/파밍(모바일)", ("모바일",)),
    ("피싱/파밍(텔레뱅킹)", ("텔레",)),
    ("전자상거래/매체 위변조", ("위변조", "매체")),
    ("신종 전자금융사기사고", ("신종",)),
    ("원인미정(파악 중)", ()),  # 아무것도 안 맞으면 원인미정
]
RECOGNIZERS = ["금융회사", "고객(민원인)", "기타"]


def get(d, path, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur not in (None, "") else default


def selected_category(inc):
    return get(inc, "classification.incident_category")


def is_valid_category(inc):
    return selected_category(inc) in INCIDENT_CATEGORIES


def raw_subtype(inc):
    return (get(inc, "classification.failure_subtype") or "").strip()


def is_valid_subtype(inc):
    """전산장애일 때 세부유형이 스키마 정규값인가(빈값은 미입력으로 허용)."""
    if selected_category(inc) != "전산장애사고":
        return True
    sub = raw_subtype(inc)
    return sub == "" or sub in FAILURE_SUBTYPES


def selected_subtype(inc):
    """failure_subtype → 서식에서 체크할 정규 세부유형. 모르면 '미정(파악 중)'."""
    sub = raw_subtype(inc)
    if sub in FAILURE_SUBTYPES:
        return sub
    if "프로그램" in sub:
        return "업무처리 프로그램 오류"
    if "외부" in sub:
        return "외부요인으로 인한 장애"
    if "시설" in sub or "설비" in sub:
        return "시설·설비 장애"
    if "시스템" in sub:
        return "시스템 장애"
    return "미정(파악 중)"


def selected_recognizer(inc):
    fr = get(inc, "detection.first_recognizer", "") or ""
    if fr.startswith("금융회사"):
        return "금융회사"
    if "고객" in fr:
        return "고객(민원인)"
    if fr:
        return "기타"
    return None


def _has(s, *kw):
    s = s or ""
    return any(k in s for k in kw)


def form_checkboxes(inc, stage):
    """서식 전체 체크박스 상태를 계산 — {그룹: {표시라벨: 체크여부}}.

    비활성(사고유형에 맞지 않는) 열은 전부 False로 게이트된다.
    PDF는 이걸 그대로 렌더하고, 검증기는 렌더된 HTML의 ☑ 집합과 대조한다.
    """
    cat = selected_category(inc)
    pii = get(inc, "security.personal_data_affected", False)
    at = get(inc, "security.attack_target") or ""
    am = get(inc, "security.attack_method") or ""
    ad = get(inc, "security.attack_damage") or ""
    fd = get(inc, "classification.failure_detail") or ""

    chim_active = cat == "침해사고" or bool(pii)
    jan_active = cat == "전산장애사고"
    sagi_active = cat == "전자금융사기사고"

    sub_sel = selected_subtype(inc)
    at_known_other = at != "" and not _has(at, "내부망", "DMZ", "미상")

    out = {}
    out["보고형태"] = {ko: (STAGE_KO.get(stage) == ko) for ko in ["최초", "중간", "종결"]}

    out["전산장애"] = {disp: (jan_active and sub_sel == key) for key, disp in FAILURE_SUBTYPE_OPTIONS}

    out["침해_공격대상"] = {
        "내부망 시스템": chim_active and "내부망" in at,
        "DMZ구간 시스템": chim_active and "DMZ" in at,
        "기타": chim_active and at_known_other,
        "미상(파악 중)": chim_active and ("미상" in at or at == ""),
    }
    out["침해_공격방법"] = {
        "악성코드(웹쉘, 랜섬웨어, 바이러스 등)": chim_active and _has(am, "악성코드", "웹쉘", "랜섬", "바이러스"),
        "서비스거부공격": chim_active and _has(am, "서비스거부", "DDoS", "디도스"),
        "보안 취약점 해킹": chim_active and "취약점" in am,
        "무단 접속 및 조작": chim_active and _has(am, "무단", "조작"),
        "공급망 보안 침해(연계기관 해킹 등)": chim_active and _has(am, "공급망", "연계기관"),
        "기타": False,
        "미상(파악 중)": chim_active and ("미상" in am or am == ""),
    }
    out["침해_공격피해"] = {
        "시스템 및 서비스 중단": chim_active and "중단" in ad,
        "정보유출": chim_active and ("유출" in ad or bool(pii)),
        "중요정보 조작": chim_active and "조작" in ad,
        "금전적 손실": chim_active and _has(ad, "금전", "손실"),
        "기타": False,
        "미상(파악 중)": chim_active and ("미상" in ad or ad == ""),
    }

    sagi = {}
    matched = False
    for disp, kws in FRAUD_OPTIONS[:-1]:
        m = sagi_active and _has(fd, *kws) if kws else False
        sagi[disp] = m
        matched = matched or m
    sagi["원인미정(파악 중)"] = sagi_active and not matched
    out["전자금융사기"] = sagi

    rec = selected_recognizer(inc)
    out["최초인지"] = {r: (rec == r) for r in RECOGNIZERS}
    return out


def checked_set(inc, stage):
    """체크(True)된 표시라벨 집합 — '기타'는 최초인지 값 접미사 없이 정규화."""
    s = set()
    for group, opts in form_checkboxes(inc, stage).items():
        for label, on in opts.items():
            if on:
                s.add(label)
    return s
