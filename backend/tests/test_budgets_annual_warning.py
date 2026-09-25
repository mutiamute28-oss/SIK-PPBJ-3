"""Tests for Anggaran Tahunan + Peringatan Pagu + budget check endpoints (iteration 5)."""
import os
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://dependency-installer-14.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "mutiamute28@gmail.com", "password": "PtSbb2026!"}
YEAR = 2026
PERIOD = f"{YEAR}-09"


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def unit_name():
    return f"TEST_ANN_{uuid.uuid4().hex[:6]}"


# ---------- /budgets/annual ----------

def test_budgets_annual_shape_no_unit(admin):
    r = admin.get(f"{API}/budgets/annual", params={"year": YEAR})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["year"] == YEAR
    assert data["unit_kerja"] == ""
    assert isinstance(data["months"], list) and len(data["months"]) == 12
    for i, m in enumerate(data["months"]):
        assert m["month"] == i + 1
        assert "pagu" in m and "realisasi" in m
    assert "total_pagu" in data and "total_realisasi" in data


def test_budgets_annual_with_unit_filter(admin, unit_name):
    # Create budgets for 2 months
    r1 = admin.post(f"{API}/budgets",
                    json={"unit_kerja": unit_name, "period": f"{YEAR}-03", "amount": 3_000_000, "catatan": "TEST"})
    assert r1.status_code == 200
    r2 = admin.post(f"{API}/budgets",
                    json={"unit_kerja": unit_name, "period": f"{YEAR}-07", "amount": 7_000_000, "catatan": "TEST"})
    assert r2.status_code == 200

    ann = admin.get(f"{API}/budgets/annual", params={"year": YEAR, "unit_kerja": unit_name}).json()
    assert ann["unit_kerja"] == unit_name
    assert ann["months"][2]["pagu"] == 3_000_000  # March
    assert ann["months"][6]["pagu"] == 7_000_000  # July
    assert ann["total_pagu"] == 10_000_000
    # Realisasi 0 (no approved docs yet)
    assert ann["total_realisasi"] == 0

    # cleanup
    for row in admin.get(f"{API}/budgets", params={"period": f"{YEAR}-03"}).json()["rows"]:
        if row["unit_kerja"] == unit_name and row.get("id"):
            admin.delete(f"{API}/budgets/{row['id']}")
    for row in admin.get(f"{API}/budgets", params={"period": f"{YEAR}-07"}).json()["rows"]:
        if row["unit_kerja"] == unit_name and row.get("id"):
            admin.delete(f"{API}/budgets/{row['id']}")


# ---------- /budgets/check ----------

def test_budgets_check_no_budget(admin):
    unit = f"TEST_NOBUD_{uuid.uuid4().hex[:6]}"
    r = admin.get(f"{API}/budgets/check",
                  params={"unit_kerja": unit, "period": PERIOD, "amount": 500_000})
    assert r.status_code == 200
    data = r.json()
    assert data["pagu"] == 0
    assert data["over"] is False


def test_budgets_check_with_budget(admin):
    unit = f"TEST_CHK_{uuid.uuid4().hex[:6]}"
    admin.post(f"{API}/budgets",
               json={"unit_kerja": unit, "period": PERIOD, "amount": 1_000_000, "catatan": ""})
    # extra 2M -> over
    r = admin.get(f"{API}/budgets/check",
                  params={"unit_kerja": unit, "period": PERIOD, "amount": 2_000_000}).json()
    assert r["pagu"] == 1_000_000
    assert r["committed"] == 2_000_000
    assert r["over"] is True
    assert r["over_amount"] == 1_000_000
    assert r["sisa"] == -1_000_000

    # extra 500k -> under
    r2 = admin.get(f"{API}/budgets/check",
                   params={"unit_kerja": unit, "period": PERIOD, "amount": 500_000}).json()
    assert r2["over"] is False
    assert r2["sisa"] == 500_000

    # cleanup budget
    for row in admin.get(f"{API}/budgets", params={"period": PERIOD}).json()["rows"]:
        if row["unit_kerja"] == unit and row.get("id"):
            admin.delete(f"{API}/budgets/{row['id']}")


# ---------- Peringatan Pagu (POST /documents) ----------

def test_post_document_over_pagu(admin):
    unit = f"TEST_WARN_{uuid.uuid4().hex[:6]}"
    admin.post(f"{API}/budgets",
               json={"unit_kerja": unit, "period": PERIOD, "amount": 1_000_000, "catatan": ""})

    payload = {
        "doc_type": "PP", "tanggal": f"{PERIOD}-15", "unit_kerja": unit,
        "keterangan": "TEST warn", "total": 5_000_000,
        "items": [{"deskripsi": "X", "kuantitas": 1, "satuan": "u",
                   "harga_estimasi": 5_000_000, "total": 5_000_000}],
    }
    r = admin.post(f"{API}/documents", json=payload)
    assert r.status_code == 200, r.text
    doc = r.json()
    bw = doc.get("budget_warning")
    assert bw is not None, "expected budget_warning object when over pagu"
    assert bw["over"] is True
    assert bw["pagu"] == 1_000_000
    assert bw["committed"] == 5_000_000
    assert bw["over_amount"] == 4_000_000
    assert bw["unit_kerja"] == unit
    assert bw["period"] == PERIOD

    # cleanup doc
    admin.delete(f"{API}/documents/{doc['id']}")

    # Now under-pagu
    payload2 = dict(payload)
    payload2["total"] = 500_000
    payload2["items"] = [{"deskripsi": "X", "kuantitas": 1, "satuan": "u",
                          "harga_estimasi": 500_000, "total": 500_000}]
    r2 = admin.post(f"{API}/documents", json=payload2)
    assert r2.status_code == 200
    doc2 = r2.json()
    assert doc2.get("budget_warning") is None, "under-pagu should have no warning"
    admin.delete(f"{API}/documents/{doc2['id']}")

    # cleanup budget
    for row in admin.get(f"{API}/budgets", params={"period": PERIOD}).json()["rows"]:
        if row["unit_kerja"] == unit and row.get("id"):
            admin.delete(f"{API}/budgets/{row['id']}")


def test_post_document_no_budget_no_warning(admin):
    unit = f"TEST_NOWARN_{uuid.uuid4().hex[:6]}"
    payload = {
        "doc_type": "PP", "tanggal": f"{PERIOD}-15", "unit_kerja": unit,
        "keterangan": "TEST nowarn", "total": 999_999_999,
        "items": [{"deskripsi": "X", "kuantitas": 1, "satuan": "u",
                   "harga_estimasi": 999_999_999, "total": 999_999_999}],
    }
    r = admin.post(f"{API}/documents", json=payload)
    assert r.status_code == 200
    doc = r.json()
    assert doc.get("budget_warning") is None, "no budget defined => no warning"
    admin.delete(f"{API}/documents/{doc['id']}")


def test_budgets_annual_realisasi_from_approved(admin):
    """Approved doc should count into annual realisasi bucket for its month."""
    unit = f"TEST_ANNR_{uuid.uuid4().hex[:6]}"
    admin.post(f"{API}/budgets",
               json={"unit_kerja": unit, "period": PERIOD, "amount": 50_000_000, "catatan": ""})
    payload = {
        "doc_type": "PPBJ", "tanggal": f"{PERIOD}-20", "unit_kerja": unit,
        "keterangan": "TEST annual real", "total": 12_345_000,
        "items": [{"deskripsi": "X", "kuantitas": 1, "satuan": "u",
                   "harga_estimasi": 12_345_000, "total": 12_345_000}],
    }
    cr = admin.post(f"{API}/documents", json=payload).json()
    did = cr["id"]
    for idx in range(len(cr["approvals"])):
        admin.post(f"{API}/documents/{did}/approve",
                   json={"step_index": idx, "action": "approve", "note": ""})
    ann = admin.get(f"{API}/budgets/annual",
                    params={"year": YEAR, "unit_kerja": unit}).json()
    assert ann["months"][8]["realisasi"] == 12_345_000  # September (idx 8)
    assert ann["total_realisasi"] == 12_345_000

    # cleanup
    admin.delete(f"{API}/documents/{did}")
    for row in admin.get(f"{API}/budgets", params={"period": PERIOD}).json()["rows"]:
        if row["unit_kerja"] == unit and row.get("id"):
            admin.delete(f"{API}/budgets/{row['id']}")
