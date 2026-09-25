"""Tests for Anggaran Bulanan (monthly budgets) endpoints."""
import os
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dependency-installer-14.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "mutiamute28@gmail.com", "password": "PtSbb2026!"}
KEUANGAN = {"email": "keuangan@sbb.co.id", "password": "keuangan123"}

PERIOD = "2026-09"
UNIT_A = f"TEST_UNIT_{uuid.uuid4().hex[:6]}"
UNIT_B = f"TEST_UNIT_{uuid.uuid4().hex[:6]}"


def _session(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login {creds['email']} failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _session(ADMIN)


@pytest.fixture(scope="module")
def keu():
    return _session(KEUANGAN)


@pytest.fixture(scope="module")
def approver_and_user(admin):
    """Create temp approver + user roles via admin register."""
    tag = uuid.uuid4().hex[:6]
    users = {}
    for role in ("approver", "user"):
        email = f"test_{role}_{tag}@example.com"
        password = "TestPass123!"
        r = admin.post(f"{API}/auth/register",
                       json={"email": email, "password": password, "name": f"T {role}", "role": role})
        assert r.status_code in (200, 201), f"register {role}: {r.status_code} {r.text}"
        s = requests.Session()
        lr = s.post(f"{API}/auth/login", json={"email": email, "password": password})
        assert lr.status_code == 200, f"login temp {role}: {lr.text}"
        users[role] = s
    return users


# ---------- basic list & units ----------

def test_get_budget_units(admin):
    r = admin.get(f"{API}/budget-units")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_budgets_period_shape(admin):
    r = admin.get(f"{API}/budgets", params={"period": PERIOD})
    assert r.status_code == 200
    data = r.json()
    for k in ("period", "rows", "total_pagu", "total_realisasi"):
        assert k in data
    assert data["period"] == PERIOD
    assert isinstance(data["rows"], list)


# ---------- CREATE / UPSERT ----------

def test_create_budget_admin_and_upsert(admin):
    r = admin.post(f"{API}/budgets",
                   json={"unit_kerja": UNIT_A, "period": PERIOD, "amount": 10_000_000, "catatan": "TEST init"})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["unit_kerja"] == UNIT_A
    assert doc["period"] == PERIOD
    assert doc["amount"] == 10_000_000
    bid = doc["id"]

    # Re-post same unit+period -> upsert (same id, updated amount)
    r2 = admin.post(f"{API}/budgets",
                    json={"unit_kerja": UNIT_A, "period": PERIOD, "amount": 25_000_000, "catatan": "TEST upserted"})
    assert r2.status_code == 200
    doc2 = r2.json()
    assert doc2["id"] == bid, "upsert should reuse same id"
    assert doc2["amount"] == 25_000_000
    assert doc2["catatan"] == "TEST upserted"

    # GET to verify persisted
    lr = admin.get(f"{API}/budgets", params={"period": PERIOD})
    rows = lr.json()["rows"]
    match = [x for x in rows if x["unit_kerja"] == UNIT_A]
    assert match and match[0]["amount"] == 25_000_000
    assert match[0]["no_budget"] is False


def test_create_budget_keuangan(keu):
    r = keu.post(f"{API}/budgets",
                 json={"unit_kerja": UNIT_B, "period": PERIOD, "amount": 5_000_000, "catatan": "TEST keu"})
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 5_000_000


# ---------- RBAC 403 ----------

def test_rbac_approver_user_cannot_write(approver_and_user):
    for role, s in approver_and_user.items():
        body = {"unit_kerja": f"TEST_RBAC_{role}", "period": PERIOD, "amount": 1, "catatan": ""}
        r = s.post(f"{API}/budgets", json=body)
        assert r.status_code == 403, f"{role} POST expected 403 got {r.status_code}"
        r = s.put(f"{API}/budgets/nonexistent", json=body)
        assert r.status_code == 403
        r = s.delete(f"{API}/budgets/nonexistent")
        assert r.status_code == 403
        # But GETs must work
        assert s.get(f"{API}/budgets", params={"period": PERIOD}).status_code == 200
        assert s.get(f"{API}/budget-units").status_code == 200


# ---------- Realisasi computation ----------

def test_realisasi_only_counts_approved_or_posted(admin):
    """Create PPBJ doc for a unit, approve all steps, verify realisasi shows in budget row."""
    unit = f"TEST_REAL_{uuid.uuid4().hex[:6]}"
    # create budget for this unit
    admin.post(f"{API}/budgets",
               json={"unit_kerja": unit, "period": PERIOD, "amount": 100_000_000, "catatan": "TEST realisasi"})

    # Baseline realisasi = 0
    base = admin.get(f"{API}/budgets", params={"period": PERIOD}).json()
    base_row = [x for x in base["rows"] if x["unit_kerja"] == unit][0]
    assert base_row["realisasi"] == 0
    assert base_row["doc_count"] == 0

    # Create PPBJ pending_approval
    doc_payload = {
        "doc_type": "PPBJ",
        "tanggal": f"{PERIOD}-15",
        "unit_kerja": unit,
        "keterangan": "TEST realisasi ppbj",
        "total": 40_000_000,
        "items": [{"deskripsi": "Item", "kuantitas": 1, "satuan": "unit",
                   "harga_estimasi": 40_000_000, "total": 40_000_000}],
    }
    cr = admin.post(f"{API}/documents", json=doc_payload)
    assert cr.status_code == 200, cr.text
    doc = cr.json()
    did = doc["id"]

    # Confirm pending_approval => not counted
    pend = admin.get(f"{API}/budgets", params={"period": PERIOD}).json()
    pend_row = [x for x in pend["rows"] if x["unit_kerja"] == unit][0]
    assert pend_row["realisasi"] == 0, "pending_approval must NOT count"

    # Approve every step
    for idx in range(len(doc["approvals"])):
        ar = admin.post(f"{API}/documents/{did}/approve",
                        json={"step_index": idx, "action": "approve", "note": "ok"})
        assert ar.status_code == 200

    # Confirm doc now approved
    dget = admin.get(f"{API}/documents/{did}").json()
    assert dget["status"] == "approved", f"expected approved got {dget['status']}"

    # Verify realisasi now reflects total
    final = admin.get(f"{API}/budgets", params={"period": PERIOD}).json()
    row = [x for x in final["rows"] if x["unit_kerja"] == unit][0]
    assert row["realisasi"] == 40_000_000
    assert row["doc_count"] == 1
    assert row["sisa"] == 100_000_000 - 40_000_000
    assert row["persen"] == 40.0
    assert row["no_budget"] is False

    # cleanup
    admin.delete(f"{API}/documents/{did}")


def test_no_budget_flag(admin):
    """A unit with realisasi in period but no budget row -> no_budget=true, amount=0."""
    unit = f"TEST_NOBUDGET_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "doc_type": "PPBJ",
        "tanggal": f"{PERIOD}-10",
        "unit_kerja": unit,
        "keterangan": "TEST nobudget",
        "total": 7_000_000,
        "items": [{"deskripsi": "X", "kuantitas": 1, "satuan": "u",
                   "harga_estimasi": 7_000_000, "total": 7_000_000}],
    }
    cr = admin.post(f"{API}/documents", json=doc_payload).json()
    did = cr["id"]
    for idx in range(len(cr["approvals"])):
        admin.post(f"{API}/documents/{did}/approve",
                   json={"step_index": idx, "action": "approve", "note": ""})

    data = admin.get(f"{API}/budgets", params={"period": PERIOD}).json()
    row = [x for x in data["rows"] if x["unit_kerja"] == unit]
    assert row, f"unit {unit} should appear as row"
    row = row[0]
    assert row["no_budget"] is True
    assert row["amount"] == 0
    assert row["realisasi"] == 7_000_000
    assert row["sisa"] == -7_000_000

    admin.delete(f"{API}/documents/{did}")


def test_rejected_not_counted(admin):
    unit = f"TEST_REJ_{uuid.uuid4().hex[:6]}"
    admin.post(f"{API}/budgets",
               json={"unit_kerja": unit, "period": PERIOD, "amount": 1_000_000, "catatan": ""})
    doc_payload = {
        "doc_type": "PPBJ", "tanggal": f"{PERIOD}-05", "unit_kerja": unit,
        "keterangan": "TEST reject", "total": 500_000,
        "items": [{"deskripsi": "X", "kuantitas": 1, "satuan": "u",
                   "harga_estimasi": 500_000, "total": 500_000}],
    }
    d = admin.post(f"{API}/documents", json=doc_payload).json()
    admin.post(f"{API}/documents/{d['id']}/approve",
               json={"step_index": 0, "action": "reject", "note": "no"})
    data = admin.get(f"{API}/budgets", params={"period": PERIOD}).json()
    row = [x for x in data["rows"] if x["unit_kerja"] == unit][0]
    assert row["realisasi"] == 0, "rejected doc must not count"
    admin.delete(f"{API}/documents/{d['id']}")


# ---------- PUT / DELETE ----------

def test_put_and_delete_budget(admin):
    unit = f"TEST_PUT_{uuid.uuid4().hex[:6]}"
    c = admin.post(f"{API}/budgets",
                   json={"unit_kerja": unit, "period": PERIOD, "amount": 1_000_000, "catatan": "before"}).json()
    bid = c["id"]

    unit2 = f"TEST_PUT2_{uuid.uuid4().hex[:6]}"
    p = admin.put(f"{API}/budgets/{bid}",
                  json={"unit_kerja": unit2, "period": PERIOD, "amount": 9_999_999, "catatan": "after"})
    assert p.status_code == 200
    upd = p.json()
    assert upd["amount"] == 9_999_999
    assert upd["unit_kerja"] == unit2
    assert upd["catatan"] == "after"

    # DELETE
    d = admin.delete(f"{API}/budgets/{bid}")
    assert d.status_code == 200

    data = admin.get(f"{API}/budgets", params={"period": PERIOD}).json()
    assert not [x for x in data["rows"] if x.get("id") == bid]


# ---------- cleanup (best effort) ----------

def test_zzz_cleanup(admin):
    data = admin.get(f"{API}/budgets", params={"period": PERIOD}).json()
    for row in data["rows"]:
        if row.get("id") and row["unit_kerja"].startswith("TEST_"):
            admin.delete(f"{API}/budgets/{row['id']}")
