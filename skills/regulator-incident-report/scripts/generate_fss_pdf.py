#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""incident.json → 전자금융감독규정 시행세칙 별지 제2호서식(정보기술부문 및 전자금융 사고보고서) PDF.

원본 서식(<개정 2025.2.5>)을 그대로 재현: ①표지(공문) ②별첨1(사고내용) [③별첨2(사기 일괄보고)].
표지 첫 페이지에 회사 정식 법인명(company.json legal_name) 반영.

변환: 시스템에 설치된 헤드리스 브라우저(Chrome/Edge)로 HTML→PDF. 없으면 HTML만 저장하고 안내.
표준 라이브러리만 사용. 산출물: <incident 폴더>/out/<id>_금감원_별지제2호서식.pdf (+ 동명 .html).

사용:
    python3 generate_fss_pdf.py <incident.json> --stage <initial|interim|final> [--out PATH] [--html-only]
"""
import argparse
import html
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

# 체크박스 매핑의 단일 원천(single source of truth) — md·PDF·검증기 공용
_FM = os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "scripts", "form_mapping.py")
_spec = importlib.util.spec_from_file_location("form_mapping", _FM)
form_mapping = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(form_mapping)

KST = timezone(timedelta(hours=9))
STAGE_KO = {"initial": "최초", "interim": "중간", "final": "종결"}

BROWSERS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def get(d, path, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur not in (None, "") else default


def esc(s):
    return html.escape(str(s)) if s not in (None, "") else ""


def fmt(s):
    if not s:
        return ""
    try:
        return datetime.fromisoformat(s).astimezone(KST).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return esc(s)


def cb(checked, label):
    """체크박스 한 줄."""
    return f"<div class='opt'>{'☑' if checked else '☐'} {html.escape(label)}</div>"


def find_browser():
    for b in BROWSERS:
        if os.path.exists(b):
            return b
    return None


# --------------------------------------------------------------------------
# 사고유형 3열 체크박스 (침해 / 전산장애 / 전자금융사기)
# 체크 규칙은 form_mapping(단일 원천)에서 계산된 상태(fc)를 그대로 렌더만 한다.
# --------------------------------------------------------------------------
def _opts(d):
    return "".join(cb(on, label) for label, on in d.items())


def col_chimhae(fc):
    return "".join(["<b>침해사고</b>",
        "<u>1. 공격 대상</u>", _opts(fc["침해_공격대상"]),
        "<u>2. 공격 방법</u>", _opts(fc["침해_공격방법"]),
        "<u>3. 공격에 따른 피해</u>", _opts(fc["침해_공격피해"])])


def col_janjang(fc):
    return "<b>전산장애사고</b>" + _opts(fc["전산장애"])


def col_sagi(fc):
    return "<b>전자금융사기사고</b>" + _opts(fc["전자금융사기"])


# --------------------------------------------------------------------------
# HTML 렌더링
# --------------------------------------------------------------------------
def render_cover(inc, comp, stage, now):
    legal = comp.get("legal_name", comp.get("company_name", "○○금융회사"))
    title = comp.get("representative_title", "대표이사")
    name = comp.get("representative_name", "")
    recipient = comp.get("regulator_recipient", "금융감독원장")
    writer_phone = comp.get("customer_center_phone", "")
    docno = f"{now.strftime('%Y')} - {get(inc,'incident_id','')}"
    sign = f"{esc(legal)} &nbsp; {esc(title)} &nbsp; {esc(name)} &nbsp; (인)"
    return f"""
<section class="page cover">
  <table class="writer">
    <tr><td>작 성 자 :</td><td>&nbsp; (직위: 정보보호최고책임자 조직 담당자)</td></tr>
    <tr><td>전화번호 :</td><td>&nbsp; {esc(writer_phone)}</td></tr>
  </table>
  <h1 class="cover-title">정보기술부문 및 전자금융 사고보고서</h1>
  <table class="doc">
    <tr><td class="k">문서번호</td><td>{esc(docno)}</td></tr>
    <tr><td class="k">수 &nbsp; 신</td><td>{esc(recipient)}</td></tr>
    <tr><td class="k">참 &nbsp; 조</td><td></td></tr>
    <tr><td class="k">제 &nbsp; 목</td><td>정보기술부문 및 전자금융 사고보고 ({STAGE_KO.get(stage,'')}보고)</td></tr>
  </table>
  <p class="body">전자금융감독규정 제37조의5에 따라 붙임과 같이 사고를 보고합니다.</p>
  <p class="body">붙&nbsp;&nbsp;임 &nbsp; 사고내용 1부. &nbsp; 끝.</p>
  <p class="sign">{sign}</p>
</section>"""


def render_annex1(inc, stage):
    cat = get(inc, "classification.incident_category")
    fr = get(inc, "detection.first_recognizer") or ""
    victims = get(inc, "victims", []) or []
    vic = victims[0] if victims else {}
    users = get(inc, "impact.affected_users_count")
    users_s = f"{users:,}" if isinstance(users, int) else ""
    amt = get(inc, "impact.incident_amount_krw")
    amt_s = f"{amt:,}" if isinstance(amt, (int, float)) else ""
    comp_amt = get(inc, "compensation.total_amount_krw")
    comp_amt_s = f"{comp_amt:,}" if isinstance(comp_amt, (int, float)) else ""
    resp = get(inc, "cause.responsible_company") or ""
    is_chim = get(inc, "security.personal_data_affected") or cat == "침해사고"

    # 체크박스 상태는 form_mapping(단일 원천)에서 계산
    fc = form_mapping.form_checkboxes(inc, stage)
    rpt = _opts(fc["보고형태"])
    ir_c = fc["최초인지"]
    # '기타'는 실제 인지주체 값을 접미로 표시(체크 여부는 fc를 따름)
    ir = "".join([cb(ir_c["금융회사"], "금융회사"), cb(ir_c["고객(민원인)"], "고객(민원인)"),
                  cb(ir_c["기타"], f"기타: {esc(fr) if ir_c['기타'] else '(　　　　)'}")])

    attacker = ""
    if is_chim:
        attacker = f"""
  <div class="subhdr">&lt;선택 입력사항&gt; 금융회사 공격자의 정보 제공</div>
  <table class="annex">
    <tr><td class="k">공격 유형</td><td>{''.join([cb('DDoS' in (get(inc,'security.attack_method') or ''),'DDoS'), cb('파밍' in (get(inc,'security.attack_method') or ''),'파밍악성코드'), cb('C&C' in (get(inc,'security.attack_method') or ''),'C&C서버'), cb(False,'기타')])}</td></tr>
    <tr><td class="k">공격방법</td><td>{esc(get(inc,'security.attack_method',''))}</td></tr>
    <tr><td class="k">공격자IP</td><td></td></tr>
    <tr><td class="k">공격자 MAC</td><td></td></tr>
    <tr><td class="k">Domain정보</td><td></td></tr>
    <tr><td class="k">상세내용</td><td></td></tr>
  </table>"""

    return f"""
<section class="page">
  <div class="annex-label">&lt;별첨1&gt;</div>
  <h2>정보기술부문 및 전자금융 사고내용</h2>
  <table class="annex">
    <tr><td class="k">보고형태</td><td colspan="3" class="opts-inline">{rpt}</td></tr>
    <tr>
      <td class="k">사고유형</td>
      <td class="third">{col_chimhae(fc)}</td>
      <td class="third">{col_janjang(fc)}</td>
      <td class="third">{col_sagi(fc)}</td>
    </tr>
    <tr><td class="k">최초 인지</td><td colspan="3" class="opts-inline">{ir}</td></tr>
    <tr><td class="k">사고인지일시</td><td colspan="3">{fmt(get(inc,'detection.detected_at'))}</td></tr>
    <tr><td class="k">사고발생일시</td><td colspan="3">{fmt(get(inc,'timeline.occurred_at'))}</td></tr>
    <tr><td class="k">사고종료일시</td><td colspan="3">{fmt(get(inc,'timeline.resolved_at')) or '(미복구/진행 중)'}</td></tr>
    <tr><td class="k">피해자 정보<br>및 피해금액</td><td colspan="3">성명: {esc(vic.get('name',''))} &nbsp;|&nbsp; 생년월일: {esc(vic.get('birth',''))} &nbsp;|&nbsp; 피해금액: {esc(vic.get('damage_amount_krw',''))}</td></tr>
    <tr><td class="k">배상금액 / 배상인원수</td><td colspan="3">{comp_amt_s} 원 &nbsp;/&nbsp; {esc(get(inc,'compensation.count',''))} 명</td></tr>
    <tr><td class="k">사고금액 / 사고 영향 이용자수</td><td colspan="3">{amt_s} {'원' if amt_s else '(미상)'} &nbsp;/&nbsp; {users_s or '(미상)'} {'명' if users_s else ''}</td></tr>
    <tr><td class="k">사고발생 업무(시스템)명</td><td colspan="3">{esc(get(inc,'system_name',''))}</td></tr>
    <tr><td class="k">사고내용<br>(현상 및 결과)</td><td colspan="3" class="para">{esc(get(inc,'description',''))}</td></tr>
    <tr><td class="k">사고원인<br>(변경시점 및 사유 등)</td><td colspan="3" class="para">{esc(get(inc,'cause.root_cause','(파악 중)'))}</td></tr>
    <tr><td class="k">파급영향<br>(영향받은 금융회사 등)</td><td colspan="3" class="para">{esc(get(inc,'cause.affected_other_firms','')) or '(해당 없음)'}</td></tr>
    <tr><td class="k">(외부요인) 사고 원인 회사명</td><td colspan="3">{esc(resp) or '(해당 없음)'}</td></tr>
    <tr><td class="k">처리결과</td><td colspan="3" class="para">{esc(get(inc,'handling','')) or '(조치 진행 중)'}</td></tr>
    <tr><td class="k">대 책</td><td colspan="3" class="para">{esc(get(inc,'measures','')) or '(수립 중)'}</td></tr>
  </table>
  {attacker}
</section>"""


CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { font-family: 'Apple SD Gothic Neo','AppleGothic','Malgun Gothic',sans-serif; }
body { color:#000; font-size:10pt; line-height:1.4; }
.page { page-break-after: always; }
.page:last-child { page-break-after: auto; }
.cover .writer { border-collapse:collapse; margin-left:auto; margin-bottom:40px; }
.cover .writer td { border:1px solid #000; padding:4px 10px; font-size:10pt; }
.cover-title { text-align:center; font-size:17pt; font-weight:bold; text-decoration:underline; margin:30px 0 50px; }
.doc { border-collapse:collapse; width:100%; margin-bottom:40px; }
.doc td { padding:8px 4px; font-size:12pt; vertical-align:top; }
.doc td.k { width:90px; font-weight:bold; white-space:nowrap; }
.body { font-size:12pt; margin:16px 0; text-indent:10px; }
.sign { text-align:center; font-size:14pt; font-weight:bold; margin-top:80px; }
.annex-label { font-size:10pt; margin-bottom:6px; }
h2 { text-align:center; font-size:15pt; font-weight:bold; text-decoration:underline; margin:0 0 16px; }
.annex { border-collapse:collapse; width:100%; }
.annex td { border:1px solid #000; padding:5px 7px; vertical-align:top; }
.annex td.k { width:135px; font-weight:bold; background:#f4f4f4; }
.annex td.third { width:29%; vertical-align:top; }
.opt { font-size:9pt; line-height:1.5; }
.opts-inline .opt, td.opts-inline { display:inline-block; margin-right:18px; }
.para { min-height:34px; white-space:pre-wrap; }
.subhdr { margin:14px 0 5px; font-size:10pt; }
u { text-decoration:underline; font-size:9.5pt; }
"""


def build_html(inc, comp, stage, now):
    parts = [render_cover(inc, comp, stage, now), render_annex1(inc, stage)]
    return f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(parts)}</body></html>"


def main():
    ap = argparse.ArgumentParser(description="별지 제2호서식 PDF 생성기")
    ap.add_argument("incident")
    ap.add_argument("--stage", choices=["initial", "interim", "final"], default="initial")
    ap.add_argument("--company", default=None)
    ap.add_argument("--out", default=None, help="PDF 저장 경로(미지정 시 <incident 폴더>/out/<id>_금감원_별지제2호서식.pdf)")
    ap.add_argument("--html-only", action="store_true", help="HTML만 생성(브라우저 변환 생략)")
    args = ap.parse_args()

    with open(args.incident, encoding="utf-8") as f:
        inc = json.load(f)
    comp_path = args.company or os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "company.json")
    with open(comp_path, encoding="utf-8") as f:
        comp = json.load(f)
    now = datetime.now(KST)

    iid = get(inc, "incident_id", "incident")
    out_pdf = args.out or os.path.join(os.path.dirname(os.path.abspath(args.incident)), "out", f"{iid}_금감원_별지제2호서식.pdf")
    os.makedirs(os.path.dirname(out_pdf), exist_ok=True)
    out_html = os.path.splitext(out_pdf)[0] + ".html"

    with open(out_html, "w", encoding="utf-8") as f:
        f.write(build_html(inc, comp, args.stage, now))
    print(f"💾 HTML 저장: {out_html}", file=sys.stderr)

    if args.html_only:
        print(f"ℹ️ --html-only: 브라우저에서 열어 '인쇄 → PDF로 저장'하면 동일 서식 PDF가 됩니다.", file=sys.stderr)
        print(out_html)
        return

    browser = find_browser()
    if not browser:
        print("⚠️ 헤드리스 브라우저(Chrome/Edge) 미발견 → HTML만 생성했습니다. HTML을 열어 'PDF로 인쇄'하세요.", file=sys.stderr)
        print(out_html)
        return

    cmd = [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={out_pdf}", f"file://{out_html}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_pdf):
        # 구버전 호환: --headless
        cmd[1] = "--headless"
        r = subprocess.run(cmd, capture_output=True, text=True)
    if os.path.exists(out_pdf):
        print(f"💾 PDF 저장: {out_pdf}", file=sys.stderr)
        print(out_pdf)
    else:
        print(f"⚠️ PDF 변환 실패(브라우저). HTML은 생성됨: {out_html}\n{(r.stderr or '')[-300:]}", file=sys.stderr)
        print(out_html)


if __name__ == "__main__":
    main()
