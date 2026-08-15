#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
플러그인 핵심 로직 회귀 테스트 (표준 라이브러리 unittest).
실행: python3 tests/test_plugin.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KST = timezone(timedelta(hours=9))


def load(modname, relpath):
    spec = importlib.util.spec_from_file_location(modname, os.path.join(ROOT, relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fss = load("fss", "skills/regulator-incident-report/scripts/generate_fss_report.py")
tracker = load("tracker", "skills/response-deadline-tracker/scripts/incident_tracker.py")
board = load("board", "skills/exec-board-report/scripts/generate_management_report.py")
fm = load("fm", "shared/scripts/form_mapping.py")
verifier = load("verifier", "shared/scripts/verify_fss_consistency.py")
validator = load("validator", "shared/scripts/validate_incident.py")


class TestFSSTrigger(unittest.TestCase):
    def mk(self, minutes, users, cat="전산장애사고", **extra):
        inc = {"classification": {"incident_category": cat},
               "impact": {"disruption_minutes": minutes, "affected_users_count": users}}
        inc["impact"].update(extra)
        return inc

    def test_30min_reportable(self):
        self.assertTrue(fss.assess_trigger(self.mk(30, 100))["reportable"])

    def test_10min_10k_reportable(self):
        self.assertTrue(fss.assess_trigger(self.mk(10, 10000))["reportable"])

    def test_small_not_reportable(self):
        self.assertFalse(fss.assess_trigger(self.mk(5, 500))["reportable"])

    def test_29min_under_10k_not_reportable(self):
        self.assertFalse(fss.assess_trigger(self.mk(29, 9999))["reportable"])

    def test_single_branch_excluded(self):
        r = fss.assess_trigger(self.mk(40, 20000, single_branch_only=True))
        self.assertFalse(r["reportable"])
        self.assertTrue(r["excluded"])

    def test_breach_always_reportable(self):
        self.assertTrue(fss.assess_trigger(self.mk(1, 1, cat="침해사고"))["reportable"])


class TestBusinessDays(unittest.TestCase):
    # 보상 통지기한(접수+14영업일) 계산은 response-deadline-tracker가 담당 (compensation-calc 제외됨)
    def test_business_days_skip_weekend(self):
        start = datetime(2026, 7, 1, 9, 0, tzinfo=KST)  # 수요일
        self.assertEqual(tracker.add_business_days(start, 2, set()).strftime("%Y-%m-%d"), "2026-07-03")

    def test_business_days_skip_holiday(self):
        start = datetime(2026, 7, 1, 9, 0, tzinfo=KST)
        self.assertEqual(tracker.add_business_days(start, 1, {"2026-07-02"}).strftime("%Y-%m-%d"), "2026-07-03")


class TestBoardSeverity(unittest.TestCase):
    TH = {"affected_users": 100000, "disruption_minutes": 60, "incident_amount_krw": 100000000, "factors_required_for_board": 2}

    def base(self, **kw):
        inc = {"classification": {"incident_category": "전산장애사고"},
               "security": {"personal_data_affected": False},
               "impact": {"affected_users_count": 0, "disruption_minutes": 0, "incident_amount_krw": 0},
               "cause": {"external_factor": False, "affected_other_firms": None}}
        for k, v in kw.items():
            grp, key = k.split("__")
            inc[grp][key] = v
        return inc

    def test_pii_mandatory_board(self):
        inc = self.base()
        inc["security"]["personal_data_affected"] = True
        self.assertTrue(board.assess_board(inc, self.TH)["required"])

    def test_one_factor_not_board(self):
        inc = self.base(impact__disruption_minutes=120)  # 1 factor only
        self.assertFalse(board.assess_board(inc, self.TH)["required"])

    def test_two_factors_board(self):
        inc = self.base(impact__disruption_minutes=120, impact__affected_users_count=200000)
        self.assertTrue(board.assess_board(inc, self.TH)["required"])


class TestSubprocess(unittest.TestCase):
    def write_tmp(self, data):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(data, f, ensure_ascii=False)
        f.close()
        return f.name

    def test_recovery_lock_exit2(self):
        with open(os.path.join(ROOT, "shared/incident.example.json"), encoding="utf-8") as _f:
            inc = json.load(_f)
        inc["timeline"]["resolved_at"] = None
        p = self.write_tmp(inc)
        r = subprocess.run([sys.executable,
                            os.path.join(ROOT, "skills/customer-outage-notice/scripts/generate_customer_notice.py"),
                            p, "--mode", "recovery"], capture_output=True)
        self.assertEqual(r.returncode, 2)
        os.unlink(p)

    def test_set_status_writeback(self):
        with open(os.path.join(ROOT, "shared/incident.example.json"), encoding="utf-8") as _f:
            inc = json.load(_f)
        p = self.write_tmp(inc)
        subprocess.run([sys.executable, os.path.join(ROOT, "shared/scripts/set_status.py"),
                        p, "--key", "fss_initial", "--status", "초안"], capture_output=True, check=True)
        with open(p, encoding="utf-8") as _f:
            updated = json.load(_f)
        self.assertEqual(updated["reporting"]["fss_initial"]["status"], "초안")
        self.assertIn("generated_at", updated["reporting"]["fss_initial"])
        os.unlink(p)

    def test_privacy_not_applicable_exit0(self):
        with open(os.path.join(ROOT, "shared/incident.example.json"), encoding="utf-8") as _f:
            inc = json.load(_f)
        p = self.write_tmp(inc)  # personal_data_affected absent → not applicable
        r = subprocess.run([sys.executable,
                            os.path.join(ROOT, "skills/privacy-breach-filing/scripts/gen_privacy_breach_report.py"), p],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("해당없음", r.stdout)
        os.unlink(p)


class TestFormConsistency(unittest.TestCase):
    """① 단일 매핑 모듈(form_mapping)이 md·PDF·검증기의 유일한 원천인지,
    ② incident.json ↔ PDF 체크박스가 항상 일치하는지 회귀 검증."""

    def mk(self, **kw):
        return {
            "incident_id": "T",
            "detection": {"first_recognizer": kw.get("recognizer", "금융회사"), "detected_at": "2026-06-01T10:00:00+09:00"},
            "timeline": {"occurred_at": "2026-06-01T09:55:00+09:00", "resolved_at": None},
            "classification": {"incident_category": kw.get("cat", "전산장애사고"), "failure_subtype": kw.get("sub", "시스템 장애"),
                               "failure_detail": kw.get("detail", "")},
            "impact": {"disruption_minutes": kw.get("dis", 40), "affected_users_count": kw.get("users", 5000),
                       "incident_amount_krw": kw.get("amount")},
            "cause": {"root_cause": "c", "external_factor": kw.get("ext", False)},
            "security": kw.get("security", {"personal_data_affected": False}),
            "system_name": "s", "description": "d",
        }

    def assertClean(self, inc):
        errs, warns, info = verifier.verify(inc, "initial")
        self.assertEqual(errs, [], f"정합성 오류: {errs}")
        return fm.checked_set(inc, "initial")

    def test_service_disruption_system_failure(self):
        checks = self.assertClean(self.mk(cat="전산장애사고", sub="시스템 장애"))
        self.assertIn("시스템 장애 (서버·네트워크·스토리지·보안장비 / OS·DBMS·미들웨어·WAS 등)", checks)
        # 침해·사기 열은 비활성 → 관련 라벨 미체크
        self.assertNotIn("정보유출", checks)
        self.assertNotIn("피싱/파밍(인터넷)", checks)

    def test_security_incident_with_personal_data(self):
        sec = {"personal_data_affected": True, "info_type": "개인정보", "attack_method": "악성코드 랜섬웨어",
               "attack_target": "내부망 시스템", "attack_damage": "정보유출", "leaked_count": 5000}
        checks = self.assertClean(self.mk(cat="침해사고", sub="미정(파악 중)", ext=True, security=sec))
        self.assertIn("정보유출", checks)
        self.assertIn("악성코드(웹쉘, 랜섬웨어, 바이러스 등)", checks)

    def test_electronic_finance_fraud(self):
        checks = self.assertClean(self.mk(cat="전자금융사기사고", detail="피싱/파밍 모바일", amount=500000000))
        self.assertIn("피싱/파밍(모바일)", checks)

    def test_combined_disruption_and_personal_data(self):
        # 전산장애인데 개인정보 동반 → 침해 열 '정보유출'도 활성
        checks = self.assertClean(self.mk(cat="전산장애사고", sub="시스템 장애",
                                          security={"personal_data_affected": True, "info_type": "개인정보"}))
        self.assertIn("시스템 장애 (서버·네트워크·스토리지·보안장비 / OS·DBMS·미들웨어·WAS 등)", checks)
        self.assertIn("정보유출", checks)

    def test_invalid_enum_must_fail(self):
        # 스키마에 없는 세부유형 → 가드레일이 발동해야 함(음성 테스트)
        errs, warns, info = verifier.verify(self.mk(cat="전산장애사고", sub="네트워크 장애"), "initial")
        self.assertTrue(errs, "깨진 enum을 검증기가 잡지 못함")

    def test_unknown_fields_are_listed(self):
        errs, warns, info = verifier.verify(self.mk(amount=None), "initial")
        self.assertIn("사고금액", info)


class TestPreflightValidation(unittest.TestCase):
    """공통 사전 검증(validate_incident) — enum·필수필드 가드레일."""

    def full(self, **kw):
        inc = {"incident_id": "V", "detection": {"first_recognizer": "금융회사", "detected_at": "2026-06-01T10:00:00+09:00"},
               "timeline": {"occurred_at": "2026-06-01T09:55:00+09:00", "resolved_at": None},
               "classification": {"incident_category": "전산장애사고", "failure_subtype": "시스템 장애"},
               "impact": {"disruption_minutes": 40, "affected_users_count": 5000, "incident_amount_krw": None},
               "cause": {"root_cause": "c", "external_factor": False},
               "security": {"personal_data_affected": False}, "system_name": "s", "description": "d"}
        for k, v in kw.items():
            grp, key = k.split("__", 1)
            inc.setdefault(grp, {})[key] = v
        return inc

    def test_valid_incident_has_no_errors(self):
        errs, warns = validator.validate(self.full())
        self.assertEqual(errs, [])

    def test_invalid_incident_category(self):
        errs, warns = validator.validate(self.full(classification__incident_category="해킹사고"))
        self.assertTrue(any("enum" in e for e in errs))

    def test_invalid_failure_subtype(self):
        errs, warns = validator.validate(self.full(classification__failure_subtype="네트워크 장애"))
        self.assertTrue(any("failure_subtype" in e for e in errs))

    def test_missing_required_field(self):
        inc = self.full()
        inc["system_name"] = ""
        errs, warns = validator.validate(inc)
        self.assertTrue(any("필수" in e for e in errs))

    def test_unknown_user_count_is_warning_not_error(self):
        errs, warns = validator.validate(self.full(impact__affected_users_count=None))
        self.assertEqual(errs, [])
        self.assertTrue(any("1만명" in w for w in warns))


if __name__ == "__main__":
    unittest.main(verbosity=2)
