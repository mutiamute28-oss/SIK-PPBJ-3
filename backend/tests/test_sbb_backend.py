"""End-to-end backend tests for PT SBB Sistem Keuangan."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dependency-installer-14.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "mutiamute28@gmail.com"
ADMIN_PW = "PtSbb2026!"
KEU_EMAIL = "keuangan@sbb.co.id"
KEU_PW = "keuangan123"


# ---- Fixtures ----
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def keu_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": KEU_EMAIL, "password": KEU_PW}, timeout=30)
    assert r.status_code == 200, f"Keuangan login failed: {r.status_code} {r.text}"
    return s


# ---- Auth ----
class TestAuth:
    def test_login_success_admin(self, admin_session):
        r = admin_session.get(f"{API}/auth/me")
        assert r.status_code == 200
        u = r.json()
        assert u["email"] == ADMIN_EMAIL
        assert u["role"] == "admin"

    def test_login_success_keuangan(self, keu_session):
        r = keu_session.get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json()["role"] == "keuangan"

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"}, timeout=30)
        assert r.status_code in (401, 429)

    def test_me_requires_auth(self):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401

    def test_forgot_password_generic(self):
        r = requests.post(f"{API}/auth/forgot-password", json={"email": "nobody@example.com"}, timeout=30)
        assert r.status_code == 200
        assert "message" in r.json()


# ---- Master data ----
class TestMasterData:
    def test_accounts_list(self, admin_session):
        r = admin_session.get(f"{API}/accounts")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) > 0
        codes = [a["code"] for a in data]
        assert "1-10400" in codes  # PPN Masukan
        assert "2-10004" in codes  # PPh 23

    def test_tax_settings(self, admin_session):
        r = admin_session.get(f"{API}/tax-settings")
        assert r.status_code == 200
        t = r.json()
        assert t["ppn_rate"] == 11.0
        assert any(x["code"] == "PPH23_JASA" for x in t["taxes"])

    def test_tax_settings_update(self, admin_session):
        current = admin_session.get(f"{API}/tax-settings").json()
        payload = {"ppn_rate": current["ppn_rate"], "ppn_account": current["ppn_account"], "taxes": current["taxes"]}
        r = admin_session.put(f"{API}/tax-settings", json=payload)
        assert r.status_code == 200


# ---- Documents & Approval & Journal ----
class TestPPWorkflow:
    doc_id = None

    def test_create_pp_document(self, admin_session):
        payload = {
            "doc_type": "PP", "kegiatan": "TEST_Pembelian_Jasa", "supplier": "PT Jasa Test",
            "dpp": 10000000, "ppn_enabled": True, "pph_code": "PPH23_JASA",
            "expense_account": "6-10005", "payment_account": "1-10002",
            "keterangan": "TEST_PP journal balance"
        }
        r = admin_session.post(f"{API}/documents", json=payload)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["status"] == "pending_approval"
        assert doc["dpp"] == 10000000
        assert len(doc["approvals"]) == 4
        TestPPWorkflow.doc_id = doc["id"]

    def test_approve_all_steps(self, admin_session):
        assert TestPPWorkflow.doc_id
        for i in range(4):
            r = admin_session.post(f"{API}/documents/{TestPPWorkflow.doc_id}/approve",
                                   json={"step_index": i, "action": "approve", "note": ""})
            assert r.status_code == 200, r.text
        final = r.json()
        assert final["status"] == "approved"

    def test_generate_journal_and_balance(self, admin_session):
        r = admin_session.post(f"{API}/documents/{TestPPWorkflow.doc_id}/generate-journal")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["balanced"] is True
        # Expected: Debit Beban 10M + PPN 1.1M = 11.1M ; Kredit PPh23 200k + Kas 10.9M = 11.1M
        assert j["total_debit"] == 11100000
        assert j["total_kredit"] == 11100000
        # find lines
        lines = j["lines"]
        beban = next(l for l in lines if l["account_code"] == "6-10005")
        assert beban["debit"] == 10000000
        ppn = next(l for l in lines if l["account_code"] == "1-10400")
        assert ppn["debit"] == 1100000
        pph = next(l for l in lines if l["account_code"] == "2-10004")
        assert pph["kredit"] == 200000
        kas = next(l for l in lines if l["account_code"] == "1-10002")
        assert kas["kredit"] == 10900000

    def test_doc_status_posted(self, admin_session):
        r = admin_session.get(f"{API}/documents/{TestPPWorkflow.doc_id}")
        assert r.status_code == 200
        assert r.json()["status"] == "posted"
        assert r.json()["journal_generated"] is True


class TestPPBJPUMPTUM:
    def test_create_ppbj_with_items(self, admin_session):
        payload = {
            "doc_type": "PPBJ", "kegiatan": "TEST_PPBJ", "supplier": "Supplier X",
            "items": [
                {"uraian": "Barang A", "kuantitas": 2, "harga_estimasi": 500000, "total": 1000000},
                {"uraian": "Barang B", "kuantitas": 1, "harga_estimasi": 250000, "total": 250000},
            ]
        }
        r = admin_session.post(f"{API}/documents", json=payload)
        assert r.status_code == 200
        assert r.json()["total"] == 1250000

    def test_create_pum(self, admin_session):
        r = admin_session.post(f"{API}/documents", json={
            "doc_type": "PUM", "kegiatan": "TEST_PUM", "total": 5000000,
            "advance_account": "1-10200", "payment_account": "1-10002"
        })
        assert r.status_code == 200
        assert r.json()["doc_type"] == "PUM"

    def test_journal_list(self, admin_session):
        r = admin_session.get(f"{API}/journals")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_dashboard(self, admin_session):
        r = admin_session.get(f"{API}/dashboard/summary")
        assert r.status_code == 200
        d = r.json()
        for k in ("by_type", "pending", "approved", "posted", "journals", "recent", "total_nilai"):
            assert k in d
        assert "PPBJ" in d["by_type"]


# ---- Role based ----
class TestRBAC:
    def test_users_admin_only(self, admin_session, keu_session):
        r1 = admin_session.get(f"{API}/users")
        assert r1.status_code == 200
        r2 = keu_session.get(f"{API}/users")
        assert r2.status_code == 403

    def test_keuangan_can_read_journals(self, keu_session):
        r = keu_session.get(f"{API}/journals")
        assert r.status_code == 200

    def test_keuangan_can_read_tax(self, keu_session):
        r = keu_session.get(f"{API}/tax-settings")
        assert r.status_code == 200
