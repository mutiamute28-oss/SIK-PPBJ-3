from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import logging
import uuid
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

import bcrypt
import jwt
import httpx
from html import escape
from urllib.parse import urlparse
from bson import ObjectId
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, BackgroundTasks, UploadFile, File, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
import requests

from seed_data import DEFAULT_COA, DEFAULT_TAX_SETTINGS
import budget_excel as bx

# ------------------------------------------------------------------ DB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Sistem Keuangan PT SBB")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ AUTH utils
JWT_ALGORITHM = "HS256"
EMAIL_BASE_URL = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip().rstrip("/") or "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME") or "Sistem Keuangan"

ROLES = ["superadmin", "admin", "keuangan", "approver", "user"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str, token_version: int = 0) -> str:
    payload = {"sub": user_id, "email": email, "ver": token_version,
               "exp": datetime.now(timezone.utc) + timedelta(minutes=15), "type": "access"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str, token_version: int = 0) -> str:
    payload = {"sub": user_id, "ver": token_version,
               "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "refresh"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def set_auth_cookies(response: Response, access: str, refresh: str):
    response.set_cookie("access_token", access, httponly=True, secure=True, samesite="none", max_age=900, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="none", max_age=604800, path="/")


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Belum login")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Token tidak valid")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User tidak ditemukan")
        if payload.get("ver", 0) != user.get("token_version", 0):
            raise HTTPException(status_code=401, detail="Sesi berakhir")
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token kedaluwarsa")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token tidak valid")


def require_roles(*roles):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        # Super admin selalu diizinkan mengakses semua endpoint
        if user.get("role") == "superadmin":
            return user
        if roles and user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Akses ditolak untuk peran Anda")
        return user
    return checker


def public_user(u: dict) -> dict:
    return {"id": str(u["_id"]) if "_id" in u else u.get("id"), "email": u["email"],
            "name": u.get("name", ""), "role": u.get("role", "user"), "active": u.get("active", True)}


async def log_activity(actor: dict, action: str, target: dict = None, details: str = None):
    """Catat jejak audit aksi akun/user."""
    entry = {
        "id": str(uuid.uuid4()),
        "action": action,
        "actor_id": str(actor.get("_id") or actor.get("id") or ""),
        "actor_email": actor.get("email", ""),
        "actor_name": actor.get("name", ""),
        "actor_role": actor.get("role", ""),
        "created_at": now_iso(),
    }
    if target is not None:
        entry["target_id"] = str(target.get("_id") or target.get("id") or "")
        entry["target_email"] = target.get("email", "")
        entry["target_name"] = target.get("name", "")
        entry["target_role"] = target.get("role", "")
    if details:
        entry["details"] = details
    try:
        await db.audit_logs.insert_one(entry)
    except Exception as e:
        logger.error(f"Gagal mencatat audit log: {e}")


# ------------------------------------------------------------------ Brute force
async def is_locked(ip: str, email: str) -> bool:
    ident = f"{ip}:{email}"
    doc = await db.login_attempts.find_one({"identifier": ident})
    if doc and doc.get("count", 0) >= 5:
        last = doc.get("last")
        if last and (datetime.now(timezone.utc) - datetime.fromisoformat(last)) < timedelta(minutes=15):
            return True
    return False


async def record_fail(ip: str, email: str):
    ident = f"{ip}:{email}"
    await db.login_attempts.update_one(
        {"identifier": ident},
        {"$inc": {"count": 1}, "$set": {"email": email, "last": datetime.now(timezone.utc).isoformat()}},
        upsert=True)


async def clear_attempts(ip: str, email: str):
    await db.login_attempts.delete_many({"email": email})


async def send_password_reset_email(to_email: str, token: str) -> bool:
    base = os.environ.get("FRONTEND_URL", "").rstrip("/")
    link = f"{base}/reset-password?token={token}"
    if not EMAIL_KEY or EMAIL_KEY.startswith("{") or not base.startswith("https://"):
        if urlparse(base).hostname in ("localhost", "127.0.0.1", "::1"):
            logger.warning("Email not configured; password reset link: %s", link)
        else:
            logger.error("Password reset email not configured (EMERGENT_EMAIL_KEY / FRONTEND_URL)")
        return False
    brand = escape(EMAIL_FROM_NAME)
    html = (f'<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif">'
            f'<p>Kami menerima permintaan reset kata sandi {brand}.</p>'
            f'<p><a href="{escape(link)}">Reset kata sandi Anda</a></p>'
            f'<p>Tautan ini berlaku 1 jam dan hanya dapat dipakai sekali. Abaikan email ini jika Anda tidak meminta.</p>'
            f'<p style="font-size:12px;color:#888">Dikirim oleh {brand}.</p></td></tr></table>')
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(f"{EMAIL_BASE_URL}/api/v1/email/send",
                                headers={"X-Email-Key": EMAIL_KEY},
                                json={"to": [to_email], "subject": f"Reset kata sandi {EMAIL_FROM_NAME}",
                                      "html": html, "from_name": EMAIL_FROM_NAME})
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Password reset email failed: {e}")
        return False


# ------------------------------------------------------------------ Models
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Optional[str] = "user"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    password: str


class UserUpdateIn(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None


class StatusIn(BaseModel):
    active: bool


class ResetPwIn(BaseModel):
    password: str


class Account(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str
    name: str
    category: str = "Beban"
    type: str = ""
    normal: str = "debit"


class TaxLine(BaseModel):
    code: str
    name: str
    rate: float
    account: str
    kind: str = "wht"
    desc: str = ""
    mode: Optional[str] = "flat"          # flat | progressive | tiered
    brackets: Optional[List[dict]] = None  # untuk progressive: [{upto, rate}]
    tiers: Optional[List[dict]] = None      # untuk tiered: [{label, rate}]


class TaxSettingsIn(BaseModel):
    ppn_rate: float
    ppn_account: str
    taxes: List[TaxLine]


class LineItem(BaseModel):
    kode: Optional[str] = ""
    uraian: str = ""
    tanggal_dibutuhkan: Optional[str] = ""
    kuantitas: float = 1
    satuan: str = "Ls"
    harga_estimasi: float = 0
    total: float = 0


class ApprovalStep(BaseModel):
    role_label: str
    name: str = ""
    status: str = "pending"  # pending | approved | rejected
    note: str = ""
    at: Optional[str] = None


class DocIn(BaseModel):
    doc_type: str  # PPBJ | PUM | PP | PTUM
    sub_type: Optional[str] = None  # Rutin | Investasi | Tidak Rutin
    entitas: str = "POLITEKNIK HASNUR"
    unit_kerja: str = ""
    kegiatan: str = ""
    lokasi: str = ""
    anggaran_status: str = "Dianggarkan"
    tanggal: Optional[str] = None
    supplier: str = ""
    keterangan: str = ""
    items: List[LineItem] = []
    total: float = 0
    # tax / journal fields (PP, PTUM)
    dpp: float = 0
    ppn_enabled: bool = False
    pph_code: Optional[str] = None
    faktur_pajak: Optional[str] = ""
    # account mapping
    expense_account: Optional[str] = None
    payment_account: Optional[str] = "1-10002"
    advance_account: Optional[str] = "1-10200"
    # link
    related_id: Optional[str] = None
    uang_muka_amount: float = 0
    pph_rate_override: Optional[float] = None
    pph_tier: Optional[str] = ""
    attachments: List[dict] = []


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def approval_template(doc_type: str) -> List[dict]:
    templates = {
        "KASKECIL": ["Diajukan Oleh (User)", "Diverifikasi (Keuangan)", "Diketahui (Direktur)", "Dibukukan (Kabag Keuangan)"],
        "NRP": ["Diajukan Oleh (User)", "Disetujui Oleh (Keuangan)"],
    }
    labels = templates.get(doc_type, [
        "Diajukan Oleh (User)", "Diperiksa Anggaran (Kabag Keuangan)",
        "Diverifikasi (Wadir)", "Disetujui (Direktur)"])
    return [ApprovalStep(role_label=l).model_dump() for l in labels]


# ------------------------------------------------------------------ AUTH endpoints
@api_router.post("/auth/register")
async def register(body: RegisterIn, response: Response, user: dict = Depends(require_roles("admin"))):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    role = body.role if body.role in ROLES else "user"
    # Hanya super admin yang boleh membuat akun super admin
    if role == "superadmin" and user.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Hanya super admin yang dapat membuat akun super admin")
    doc = {"email": email, "password_hash": hash_password(body.password), "name": body.name,
           "role": role, "token_version": 0, "active": True, "created_at": now_iso()}
    res = await db.users.insert_one(doc)
    doc["_id"] = res.inserted_id
    await log_activity(user, "user.create", doc, f"Membuat pengguna baru (peran: {role})")
    return public_user(doc)


@api_router.post("/auth/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.lower()
    ip = request.client.host if request.client else "?"
    if await is_locked(ip, email):
        raise HTTPException(status_code=429, detail="Terlalu banyak percobaan. Coba lagi dalam 15 menit.")
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        await record_fail(ip, email)
        raise HTTPException(status_code=401, detail="Email atau kata sandi salah")
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="Akun dinonaktifkan. Hubungi administrator.")
    await clear_attempts(ip, email)
    ver = user.get("token_version", 0)
    uid = str(user["_id"])
    set_auth_cookies(response, create_access_token(uid, email, ver), create_refresh_token(uid, ver))
    return public_user(user)


@api_router.post("/auth/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logout berhasil"}


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


@api_router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Tidak ada refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token tidak valid")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user or payload.get("ver", 0) != user.get("token_version", 0):
            raise HTTPException(status_code=401, detail="Sesi berakhir")
        response.set_cookie("access_token", create_access_token(str(user["_id"]), user["email"], user.get("token_version", 0)),
                            httponly=True, secure=True, samesite="none", max_age=900, path="/")
        return public_user(user)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token tidak valid")


GENERIC_RESET = {"message": "Jika email terdaftar, tautan reset telah dikirim."}


@api_router.post("/auth/forgot-password")
async def forgot_password(body: ForgotIn, background_tasks: BackgroundTasks):
    email = body.email.lower()
    await db.password_reset_requests.insert_one({"email": email, "created_at": now_iso()})
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    count = await db.password_reset_requests.count_documents({"email": email, "created_at": {"$gt": cutoff}})
    if count > 5:
        return GENERIC_RESET
    user = await db.users.find_one({"email": email})
    if not user:
        return GENERIC_RESET
    token = secrets.token_urlsafe(32)
    await db.password_reset_tokens.insert_one({
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "user_id": str(user["_id"]), "email": user["email"],
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1), "used": False})
    background_tasks.add_task(send_password_reset_email, user["email"], token)
    return GENERIC_RESET


@api_router.post("/auth/reset-password")
async def reset_password(body: ResetIn):
    h = hashlib.sha256(body.token.encode()).hexdigest()
    doc = await db.password_reset_tokens.find_one_and_update(
        {"token_hash": h, "used": False, "expires_at": {"$gt": datetime.now(timezone.utc)}},
        {"$set": {"used": True}})
    if not doc:
        raise HTTPException(status_code=400, detail="Tautan reset tidak valid atau kedaluwarsa")
    await db.users.update_one({"_id": ObjectId(doc["user_id"])},
                              {"$set": {"password_hash": hash_password(body.password)}, "$inc": {"token_version": 1}})
    await db.password_reset_tokens.delete_many({"user_id": doc["user_id"], "used": False})
    await db.login_attempts.delete_many({"email": doc["email"]})
    return {"message": "Kata sandi berhasil diubah"}


# ------------------------------------------------------------------ USERS (admin)
@api_router.get("/users")
async def list_users(user: dict = Depends(require_roles("admin"))):
    users = await db.users.find({}).to_list(500)
    return [public_user(u) for u in users]


@api_router.put("/users/{uid}")
async def update_user(uid: str, body: UserUpdateIn, user: dict = Depends(require_roles("admin"))):
    target = await db.users.find_one({"_id": ObjectId(uid)})
    if not target:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    is_super = user.get("role") == "superadmin"
    # Hanya super admin yang boleh mengubah akun super admin
    if target.get("role") == "superadmin" and not is_super:
        raise HTTPException(status_code=403, detail="Hanya super admin yang dapat mengubah akun super admin")
    # Hanya super admin yang boleh menaikkan peran menjadi super admin
    if body.role == "superadmin" and not is_super:
        raise HTTPException(status_code=403, detail="Hanya super admin yang dapat menetapkan peran super admin")
    upd = {}
    changes = []
    if body.name is not None and body.name != target.get("name"):
        upd["name"] = body.name
        changes.append("nama")
    if body.role in ROLES and body.role != target.get("role"):
        upd["role"] = body.role
        changes.append(f"peran → {body.role}")
    if body.password:
        upd["password_hash"] = hash_password(body.password)
        changes.append("kata sandi")
    if upd:
        await db.users.update_one({"_id": ObjectId(uid)}, {"$set": upd, "$inc": {"token_version": 1} if body.password else {}})
        await log_activity(user, "user.update", target, "Mengubah " + ", ".join(changes) if changes else "Memperbarui pengguna")
    u = await db.users.find_one({"_id": ObjectId(uid)})
    return public_user(u)


@api_router.post("/users/{uid}/reset-password")
async def reset_user_password(uid: str, body: ResetPwIn, user: dict = Depends(require_roles("admin"))):
    target = await db.users.find_one({"_id": ObjectId(uid)})
    if not target:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    is_super = user.get("role") == "superadmin"
    if target.get("role") == "superadmin" and not is_super:
        raise HTTPException(status_code=403, detail="Hanya super admin yang dapat mereset sandi akun super admin")
    if not body.password or len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Kata sandi minimal 6 karakter")
    await db.users.update_one({"_id": ObjectId(uid)},
                              {"$set": {"password_hash": hash_password(body.password)}, "$inc": {"token_version": 1}})
    await db.login_attempts.delete_many({"email": target["email"]})
    await log_activity(user, "user.reset_password", target, "Mereset kata sandi pengguna")
    return {"message": "Kata sandi pengguna berhasil direset"}


@api_router.patch("/users/{uid}/active")
async def set_user_active(uid: str, body: StatusIn, user: dict = Depends(require_roles("admin"))):
    actor_id = str(user["_id"] if "_id" in user else user.get("id"))
    if actor_id == uid:
        raise HTTPException(status_code=400, detail="Tidak dapat menonaktifkan akun sendiri")
    target = await db.users.find_one({"_id": ObjectId(uid)})
    if not target:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    is_super = user.get("role") == "superadmin"
    if target.get("role") == "superadmin" and not is_super:
        raise HTTPException(status_code=403, detail="Hanya super admin yang dapat mengubah status akun super admin")
    await db.users.update_one({"_id": ObjectId(uid)},
                              {"$set": {"active": body.active}, "$inc": {"token_version": 1}})
    action = "user.activate" if body.active else "user.deactivate"
    await log_activity(user, action, target, "Mengaktifkan akun" if body.active else "Menonaktifkan akun")
    u = await db.users.find_one({"_id": ObjectId(uid)})
    return public_user(u)


@api_router.delete("/users/{uid}")
async def delete_user(uid: str, user: dict = Depends(require_roles("admin"))):
    if str(user["_id"] if "_id" in user else user.get("id")) == uid:
        raise HTTPException(status_code=400, detail="Tidak dapat menghapus akun sendiri")
    target = await db.users.find_one({"_id": ObjectId(uid)})
    if not target:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    is_super = user.get("role") == "superadmin"
    if target.get("role") == "superadmin":
        if not is_super:
            raise HTTPException(status_code=403, detail="Hanya super admin yang dapat menghapus akun super admin")
        # Cegah penghapusan super admin terakhir
        remaining = await db.users.count_documents({"role": "superadmin"})
        if remaining <= 1:
            raise HTTPException(status_code=400, detail="Tidak dapat menghapus super admin terakhir")
    await db.users.delete_one({"_id": ObjectId(uid)})
    await log_activity(user, "user.delete", target, f"Menghapus pengguna (peran: {target.get('role')})")
    return {"message": "User dihapus"}


@api_router.get("/audit-logs")
async def list_audit_logs(user: dict = Depends(require_roles("admin")), limit: int = 200):
    limit = max(1, min(limit, 500))
    logs = await db.audit_logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return logs


# ------------------------------------------------------------------ MASTER: Accounts (COA)
@api_router.get("/accounts")
async def list_accounts(user: dict = Depends(get_current_user)):
    accs = await db.accounts.find({}, {"_id": 0}).sort("code", 1).to_list(1000)
    return accs


@api_router.post("/accounts")
async def create_account(body: Account, user: dict = Depends(require_roles("admin", "keuangan"))):
    if await db.accounts.find_one({"code": body.code}):
        raise HTTPException(status_code=400, detail="Kode akun sudah ada")
    await db.accounts.insert_one(body.model_dump())
    return body


@api_router.put("/accounts/{acc_id}")
async def update_account(acc_id: str, body: Account, user: dict = Depends(require_roles("admin", "keuangan"))):
    await db.accounts.update_one({"id": acc_id}, {"$set": body.model_dump()})
    return body


@api_router.delete("/accounts/{acc_id}")
async def delete_account(acc_id: str, user: dict = Depends(require_roles("admin", "keuangan"))):
    await db.accounts.delete_one({"id": acc_id})
    return {"message": "Akun dihapus"}


# ------------------------------------------------------------------ Tax settings
@api_router.get("/tax-settings")
async def get_tax_settings(user: dict = Depends(get_current_user)):
    doc = await db.tax_settings.find_one({"key": "default"}, {"_id": 0})
    return doc or DEFAULT_TAX_SETTINGS


@api_router.put("/tax-settings")
async def update_tax_settings(body: TaxSettingsIn, user: dict = Depends(require_roles("admin", "keuangan"))):
    doc = {"key": "default", "ppn_rate": body.ppn_rate, "ppn_account": body.ppn_account,
           "taxes": [t.model_dump() for t in body.taxes]}
    await db.tax_settings.update_one({"key": "default"}, {"$set": doc}, upsert=True)
    return doc


# ------------------------------------------------------------------ Documents
async def next_doc_number(doc_type: str) -> str:
    year = datetime.now(timezone.utc).year
    month = f"{datetime.now(timezone.utc).month:02d}"
    count = await db.documents.count_documents({"doc_type": doc_type}) + 1
    return f"{count:03d}/{doc_type}-BJM/{month}/{year}"


@api_router.get("/documents")
async def list_documents(doc_type: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {}
    if doc_type:
        q["doc_type"] = doc_type
    docs = await db.documents.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs


@api_router.get("/documents/{doc_id}")
async def get_document(doc_id: str, user: dict = Depends(get_current_user)):
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    return doc


@api_router.post("/documents")
async def create_document(body: DocIn, user: dict = Depends(get_current_user)):
    if body.doc_type not in ("PPBJ", "PUM", "PP", "PTUM", "KASKECIL", "NRP"):
        raise HTTPException(status_code=400, detail="Jenis dokumen tidak valid")
    total = sum((it.total or (it.kuantitas * it.harga_estimasi)) for it in body.items) if body.items else body.total
    doc = body.model_dump()
    doc.update({
        "id": str(uuid.uuid4()),
        "no": await next_doc_number(body.doc_type),
        "total": total,
        "status": "pending_approval",
        "approvals": approval_template(body.doc_type),
        "created_by": public_user(user),
        "created_at": now_iso(),
        "journal_generated": False,
    })
    await db.documents.insert_one(doc)
    doc.pop("_id", None)
    period = (doc.get("tanggal") or doc.get("created_at") or "")[:7]
    check = await compute_budget_check(doc.get("unit_kerja"), period)
    doc["budget_warning"] = check if (check and check.get("over")) else None
    return doc


@api_router.put("/documents/{doc_id}")
async def update_document(doc_id: str, body: DocIn, user: dict = Depends(get_current_user)):
    existing = await db.documents.find_one({"id": doc_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    total = sum((it.total or (it.kuantitas * it.harga_estimasi)) for it in body.items) if body.items else body.total
    upd = body.model_dump()
    upd["total"] = total
    await db.documents.update_one({"id": doc_id}, {"$set": upd})
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    return doc


@api_router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user: dict = Depends(require_roles("admin", "keuangan"))):
    await db.documents.delete_one({"id": doc_id})
    await db.journals.delete_many({"source_id": doc_id})
    return {"message": "Dokumen dihapus"}


class ApprovalIn(BaseModel):
    step_index: int
    action: str  # approve | reject
    note: str = ""


@api_router.post("/documents/{doc_id}/approve")
async def approve_document(doc_id: str, body: ApprovalIn, user: dict = Depends(require_roles("admin", "approver", "keuangan"))):
    doc = await db.documents.find_one({"id": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    approvals = doc.get("approvals", [])
    if body.step_index < 0 or body.step_index >= len(approvals):
        raise HTTPException(status_code=400, detail="Langkah otorisasi tidak valid")
    approvals[body.step_index].update({
        "status": "approved" if body.action == "approve" else "rejected",
        "name": user.get("name", ""), "note": body.note, "at": now_iso()})
    if body.action == "reject":
        status = "rejected"
    elif all(a["status"] == "approved" for a in approvals):
        status = "approved"
    else:
        status = "pending_approval"
    await db.documents.update_one({"id": doc_id}, {"$set": {"approvals": approvals, "status": status}})
    return await db.documents.find_one({"id": doc_id}, {"_id": 0})


# ------------------------------------------------------------------ JURNAL UMUM engine
def compute_pph(dpp: float, t: dict, override_rate=None) -> float:
    """Hitung PPh: progresif (bracket), tiered (rate terpilih), atau flat."""
    dpp = float(dpp or 0)
    mode = (t or {}).get("mode", "flat")
    if mode == "progressive" and t.get("brackets"):
        tax_amt = 0.0
        prev = 0.0
        for b in t["brackets"]:
            upto = b.get("upto")
            top = float(upto) if upto is not None else dpp
            if dpp > prev:
                taxable = min(dpp, top) - prev
                if taxable > 0:
                    tax_amt += taxable * (float(b["rate"]) / 100.0)
                prev = top
            else:
                break
        return tax_amt
    rate = override_rate if override_rate is not None else t.get("rate", 0)
    return dpp * (float(rate) / 100.0)


async def account_name(code: str) -> str:
    acc = await db.accounts.find_one({"code": code}, {"_id": 0})
    return acc["name"] if acc else code


async def build_journal_lines(doc: dict, tax: dict):
    """Kembalikan list baris jurnal (debit/kredit) sesuai jenis dokumen & pajak Indonesia."""
    lines = []
    dtype = doc["doc_type"]
    ket = doc.get("keterangan") or doc.get("kegiatan") or doc.get("no")

    async def line(code, debit=0.0, kredit=0.0, memo=""):
        return {"account_code": code, "account_name": await account_name(code),
                "debit": round(debit, 2), "kredit": round(kredit, 2), "memo": memo or ket}

    if dtype == "PUM":
        amt = doc.get("total") or doc.get("uang_muka_amount") or 0
        lines.append(await line(doc.get("advance_account") or "1-10200", debit=amt, memo=f"Uang muka - {ket}"))
        lines.append(await line(doc.get("payment_account") or "1-10002", kredit=amt, memo=f"Pembayaran uang muka - {ket}"))
        return lines

    # PP & PTUM & PPBJ realisasi menggunakan DPP + pajak
    dpp = doc.get("dpp") or doc.get("total") or 0
    ppn = 0.0
    if doc.get("ppn_enabled"):
        ppn = dpp * (tax.get("ppn_rate", 11) / 100.0)
    pph = 0.0
    pph_account = None
    pph_name = ""
    if doc.get("pph_code"):
        t = next((x for x in tax.get("taxes", []) if x["code"] == doc["pph_code"]), None)
        if t:
            pph = compute_pph(dpp, t, doc.get("pph_rate_override"))
            pph_account = t["account"]
            pph_name = t["name"]
            if doc.get("pph_tier"):
                pph_name = f"{t['name']} ({doc['pph_tier']})"

    if dtype == "PTUM":
        # realisasi beban menutup uang muka
        expense = doc.get("expense_account") or "6-10009"
        realized = doc.get("total") or dpp
        advance = doc.get("uang_muka_amount") or 0
        lines.append(await line(expense, debit=realized, memo=f"Realisasi beban - {ket}"))
        if ppn:
            lines.append(await line(tax.get("ppn_account", "1-10400"), debit=ppn, memo="PPN Masukan"))
        if pph:
            lines.append(await line(pph_account, kredit=pph, memo=pph_name))
        lines.append(await line(doc.get("advance_account") or "1-10200", kredit=advance, memo="Penutupan uang muka"))
        selisih = (realized + ppn - pph) - advance
        if abs(selisih) > 0.5:
            if selisih > 0:  # perusahaan bayar kekurangan
                lines.append(await line(doc.get("payment_account") or "1-10002", kredit=selisih, memo="Pembayaran kekurangan"))
            else:  # pengembalian sisa ke kas
                lines.append(await line(doc.get("payment_account") or "1-10002", debit=-selisih, memo="Pengembalian sisa uang muka"))
        return lines

    if dtype == "NRP":
        # transaksi tanpa bukti resmi, umumnya tanpa pajak, dibayar kas kecil
        expense = doc.get("expense_account") or "6-10009"
        amt = doc.get("total") or dpp
        lines.append(await line(expense, debit=amt, memo=f"{ket}"))
        lines.append(await line(doc.get("payment_account") or "1-10003", kredit=amt, memo="Pembayaran kas"))
        return lines

    # PP / PPBJ / KASKECIL realisasi pembelian barang/jasa
    expense = doc.get("expense_account") or "6-10009"
    lines.append(await line(expense, debit=dpp, memo=f"{ket}"))
    if ppn:
        lines.append(await line(tax.get("ppn_account", "1-10400"), debit=ppn, memo="PPN Masukan"))
    if pph:
        lines.append(await line(pph_account, kredit=pph, memo=f"Potongan {pph_name}"))
    payable = dpp + ppn - pph
    lines.append(await line(doc.get("payment_account") or "1-10002", kredit=payable,
                            memo=f"Pembayaran ke {doc.get('supplier') or 'supplier'}"))
    return lines


@api_router.post("/documents/{doc_id}/generate-journal")
async def generate_journal(doc_id: str, user: dict = Depends(require_roles("admin", "keuangan"))):
    doc = await db.documents.find_one({"id": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    if doc.get("status") != "approved":
        raise HTTPException(status_code=400, detail="Dokumen harus disetujui (approved) sebelum dijurnal")
    tax = await db.tax_settings.find_one({"key": "default"}, {"_id": 0}) or DEFAULT_TAX_SETTINGS
    lines = await build_journal_lines(doc, tax)
    total_debit = round(sum(l["debit"] for l in lines), 2)
    total_kredit = round(sum(l["kredit"] for l in lines), 2)
    await db.journals.delete_many({"source_id": doc_id})
    journal = {
        "id": str(uuid.uuid4()),
        "source_id": doc_id,
        "no_bukti": doc.get("no"),
        "doc_type": doc["doc_type"],
        "tanggal": doc.get("tanggal") or now_iso()[:10],
        "keterangan": doc.get("keterangan") or doc.get("kegiatan") or "",
        "supplier": doc.get("supplier", ""),
        "unit_kerja": doc.get("unit_kerja", ""),
        "faktur_pajak": doc.get("faktur_pajak", ""),
        "lines": lines,
        "total_debit": total_debit,
        "total_kredit": total_kredit,
        "balanced": abs(total_debit - total_kredit) < 0.5,
        "created_at": now_iso(),
        "created_by": user.get("name", ""),
    }
    await db.journals.insert_one(journal)
    await db.documents.update_one({"id": doc_id}, {"$set": {"journal_generated": True, "status": "posted"}})
    journal.pop("_id", None)
    return journal


@api_router.get("/journals")
async def list_journals(start: Optional[str] = None, end: Optional[str] = None,
                        doc_type: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {}
    if doc_type:
        q["doc_type"] = doc_type
    if start:
        q.setdefault("tanggal", {})["$gte"] = start
    if end:
        q.setdefault("tanggal", {})["$lte"] = end
    journals = await db.journals.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return journals


@api_router.get("/journals/{jid}")
async def get_journal(jid: str, user: dict = Depends(get_current_user)):
    j = await db.journals.find_one({"id": jid}, {"_id": 0})
    if not j:
        raise HTTPException(status_code=404, detail="Jurnal tidak ditemukan")
    return j


# ------------------------------------------------------------------ ANGGARAN BULANAN (budget per unit kerja)
class BudgetIn(BaseModel):
    unit_kerja: str
    period: str  # YYYY-MM
    amount: float = 0
    catatan: Optional[str] = ""


@api_router.get("/budget-units")
async def budget_units(user: dict = Depends(get_current_user)):
    units = await db.documents.distinct("unit_kerja")
    return sorted([u for u in units if u])


@api_router.get("/budgets")
async def list_budgets(period: str, user: dict = Depends(get_current_user)):
    return await _budget_recap(period)


async def _budget_recap(period: str):
    budgets = await db.budgets.find({"period": period}, {"_id": 0}).to_list(500)
    docs = await db.documents.find(
        {"status": {"$in": ["approved", "posted"]}},
        {"_id": 0, "unit_kerja": 1, "total": 1, "tanggal": 1, "created_at": 1}).to_list(5000)
    real, cnt = {}, {}
    for d in docs:
        dt = (d.get("tanggal") or d.get("created_at") or "")[:7]
        if dt != period:
            continue
        u = d.get("unit_kerja") or "(Tanpa Unit)"
        real[u] = real.get(u, 0) + (d.get("total") or 0)
        cnt[u] = cnt.get(u, 0) + 1
    rows, seen = [], set()
    for b in budgets:
        u = b["unit_kerja"]
        seen.add(u)
        r = real.get(u, 0)
        pagu = b.get("amount", 0) or 0
        rows.append({**b, "realisasi": r, "doc_count": cnt.get(u, 0), "sisa": pagu - r,
                     "persen": round(r / pagu * 100, 1) if pagu else 0, "no_budget": False})
    for u, r in real.items():
        if u not in seen:
            rows.append({"id": None, "unit_kerja": u, "period": period, "amount": 0, "catatan": "",
                         "realisasi": r, "doc_count": cnt.get(u, 0), "sisa": -r, "persen": 0, "no_budget": True})
    rows.sort(key=lambda x: x["unit_kerja"])
    return {"period": period, "rows": rows,
            "total_pagu": sum((b.get("amount", 0) or 0) for b in budgets),
            "total_realisasi": sum(real.values())}


@api_router.get("/budgets/export")
async def export_budgets(period: str, user: dict = Depends(get_current_user)):
    data = await _budget_recap(period)
    content = bx.build_monthly_workbook(data, period, user.get("name", ""))
    filename = f"Rekap_Anggaran_{period}.xlsx"
    return Response(
        content=content,
        media_type=bx.MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _annual_recap(year: int, unit_kerja: Optional[str] = None):
    bq = {"period": {"$regex": f"^{year}-"}}
    if unit_kerja:
        bq["unit_kerja"] = unit_kerja
    budgets = await db.budgets.find(bq, {"_id": 0}).to_list(5000)
    dq = {"status": {"$in": ["approved", "posted"]}}
    if unit_kerja:
        dq["unit_kerja"] = unit_kerja
    docs = await db.documents.find(dq, {"_id": 0, "unit_kerja": 1, "total": 1, "tanggal": 1, "created_at": 1}).to_list(20000)
    pagu_m = [0.0] * 12
    real_m = [0.0] * 12
    per_unit = {}
    for b in budgets:
        u = b.get("unit_kerja") or "(Tanpa Unit)"
        amt = b.get("amount", 0) or 0
        per_unit.setdefault(u, [0.0, 0.0])[0] += amt
        try:
            m = int(b["period"].split("-")[1])
            if 1 <= m <= 12:
                pagu_m[m - 1] += amt
        except (ValueError, IndexError):
            pass
    for d in docs:
        dt = d.get("tanggal") or d.get("created_at") or ""
        if not dt.startswith(f"{year}-"):
            continue
        try:
            m = int(dt[5:7])
        except ValueError:
            continue
        if not (1 <= m <= 12):
            continue
        u = d.get("unit_kerja") or "(Tanpa Unit)"
        tot = d.get("total") or 0
        per_unit.setdefault(u, [0.0, 0.0])[1] += tot
        real_m[m - 1] += tot
    per_unit_rows = [{"unit_kerja": u, "pagu": v[0], "realisasi": v[1]} for u, v in sorted(per_unit.items())]
    per_month = [{"month": i + 1, "pagu": pagu_m[i], "realisasi": real_m[i]} for i in range(12)]
    return {"year": year, "unit_kerja": unit_kerja or "", "per_unit": per_unit_rows, "per_month": per_month,
            "total_pagu": sum(pagu_m), "total_realisasi": sum(real_m)}


@api_router.get("/budgets/export-annual")
async def export_budgets_annual(year: int, unit_kerja: Optional[str] = None, user: dict = Depends(get_current_user)):
    annual = await _annual_recap(year, unit_kerja)
    content = bx.build_annual_workbook(annual, year, unit_kerja or "", user.get("name", ""))
    filename = f"Rekap_Anggaran_Tahunan_{year}.xlsx"
    return Response(
        content=content,
        media_type=bx.MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.get("/budgets/export-range")
async def export_budgets_range(start: str, end: str, user: dict = Depends(get_current_user)):
    periods = bx.month_range(start, end)
    if not periods:
        raise HTTPException(status_code=400, detail="Rentang periode tidak valid (format YYYY-MM).")
    months = [(p, await _budget_recap(p)) for p in periods]
    content = bx.build_range_workbook(months, user.get("name", ""))
    filename = f"Rekap_Anggaran_{periods[0]}_sd_{periods[-1]}.xlsx"
    return Response(
        content=content,
        media_type=bx.MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.post("/budgets")
async def create_budget(body: BudgetIn, user: dict = Depends(require_roles("admin", "keuangan"))):
    existing = await db.budgets.find_one({"unit_kerja": body.unit_kerja, "period": body.period})
    if existing:
        await db.budgets.update_one({"id": existing["id"]},
                                    {"$set": {"amount": body.amount, "catatan": body.catatan}})
        return await db.budgets.find_one({"id": existing["id"]}, {"_id": 0})
    doc = body.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso()})
    await db.budgets.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.put("/budgets/{bid}")
async def update_budget(bid: str, body: BudgetIn, user: dict = Depends(require_roles("admin", "keuangan"))):
    await db.budgets.update_one({"id": bid}, {"$set": {"amount": body.amount, "catatan": body.catatan,
                                                       "unit_kerja": body.unit_kerja, "period": body.period}})
    return await db.budgets.find_one({"id": bid}, {"_id": 0})


@api_router.delete("/budgets/{bid}")
async def delete_budget(bid: str, user: dict = Depends(require_roles("admin", "keuangan"))):
    await db.budgets.delete_one({"id": bid})
    return {"message": "Anggaran dihapus"}


async def compute_budget_check(unit_kerja: Optional[str], period: str, extra: float = 0.0):
    """Cek komitmen (semua dokumen non-rejected) unit+bulan terhadap pagu."""
    if not unit_kerja or not period:
        return None
    b = await db.budgets.find_one({"unit_kerja": unit_kerja, "period": period}, {"_id": 0})
    if not b:
        return None
    pagu = b.get("amount", 0) or 0
    docs = await db.documents.find(
        {"unit_kerja": unit_kerja, "status": {"$ne": "rejected"}},
        {"_id": 0, "total": 1, "tanggal": 1, "created_at": 1}).to_list(5000)
    committed = 0.0
    for d in docs:
        dt = (d.get("tanggal") or d.get("created_at") or "")[:7]
        if dt == period:
            committed += d.get("total") or 0
    committed += extra
    return {"unit_kerja": unit_kerja, "period": period, "pagu": pagu, "committed": committed,
            "sisa": pagu - committed, "over": committed > pagu, "over_amount": max(0, committed - pagu)}


@api_router.get("/budgets/check")
async def budget_check(unit_kerja: str, period: str, amount: float = 0, user: dict = Depends(get_current_user)):
    return await compute_budget_check(unit_kerja, period, extra=amount) or {"pagu": 0, "over": False}


@api_router.get("/budgets/annual")
async def budgets_annual(year: int, unit_kerja: Optional[str] = None, user: dict = Depends(get_current_user)):
    bq = {"period": {"$regex": f"^{year}-"}}
    if unit_kerja:
        bq["unit_kerja"] = unit_kerja
    budgets = await db.budgets.find(bq, {"_id": 0}).to_list(2000)
    dq = {"status": {"$in": ["approved", "posted"]}}
    if unit_kerja:
        dq["unit_kerja"] = unit_kerja
    docs = await db.documents.find(dq, {"_id": 0, "unit_kerja": 1, "total": 1, "tanggal": 1, "created_at": 1}).to_list(10000)
    pagu_m = [0.0] * 12
    real_m = [0.0] * 12
    for b in budgets:
        try:
            m = int(b["period"].split("-")[1])
            pagu_m[m - 1] += b.get("amount", 0) or 0
        except (ValueError, IndexError):
            pass
    for d in docs:
        dt = d.get("tanggal") or d.get("created_at") or ""
        if not dt.startswith(f"{year}-"):
            continue
        try:
            m = int(dt[5:7])
        except ValueError:
            continue
        if 1 <= m <= 12:
            real_m[m - 1] += d.get("total") or 0
    months = [{"month": i + 1, "pagu": pagu_m[i], "realisasi": real_m[i]} for i in range(12)]
    return {"year": year, "unit_kerja": unit_kerja or "", "months": months,
            "total_pagu": sum(pagu_m), "total_realisasi": sum(real_m)}


@api_router.get("/dashboard/summary")
async def dashboard_summary(user: dict = Depends(get_current_user)):
    async def count(q):
        return await db.documents.count_documents(q)
    by_type = {}
    for t in ("PPBJ", "PUM", "PP", "PTUM"):
        by_type[t] = await count({"doc_type": t})
    pending = await count({"status": "pending_approval"})
    approved = await count({"status": "approved"})
    posted = await count({"status": "posted"})
    journals = await db.journals.count_documents({})
    recent = await db.documents.find({}, {"_id": 0}).sort("created_at", -1).to_list(6)
    total_nilai = 0
    async for d in db.documents.find({}, {"total": 1}):
        total_nilai += d.get("total", 0)
    return {"by_type": by_type, "pending": pending, "approved": approved, "posted": posted,
            "journals": journals, "recent": recent, "total_nilai": total_nilai}


# ------------------------------------------------------------------ OBJECT STORAGE (upload nota)
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
APP_NAME = "sbb-keuangan"
_storage_key = None

MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif",
        "webp": "image/webp", "heic": "image/heic", "heif": "image/heif", "pdf": "application/pdf"}


def init_storage(force: bool = False):
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=120)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Ukuran file maksimal 10MB")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
    ct = file.content_type or MIME.get(ext, "application/octet-stream")
    uid = str(user.get("_id") or user.get("id"))
    path = f"{APP_NAME}/uploads/{uid}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, data, ct)
    except Exception as e:
        logger.error(f"upload failed: {e}")
        raise HTTPException(status_code=502, detail="Gagal mengunggah file ke penyimpanan")
    spath = result.get("path", path)
    await db.files.insert_one({"id": str(uuid.uuid4()), "storage_path": spath,
                               "original_filename": file.filename, "content_type": ct,
                               "size": result.get("size", len(data)), "is_deleted": False,
                               "created_at": now_iso()})
    return {"name": file.filename, "storage_path": spath, "content_type": ct, "url": f"/api/files/{spath}"}


@api_router.get("/files/{path:path}")
async def download_file(path: str, request: Request):
    await get_current_user(request)  # cookie auth (auto-sent for <img> same-origin)
    rec = await db.files.find_one({"storage_path": path, "is_deleted": False})
    if not rec:
        raise HTTPException(status_code=404, detail="File tidak ditemukan")
    data, ct = get_object(path)
    return Response(content=data, media_type=rec.get("content_type", ct))


# ------------------------------------------------------------------ startup / seed
@api_router.get("/")
async def root():
    return {"message": "Sistem Keuangan PT SBB API"}


async def seed():
    # indexes
    await db.users.create_index("email", unique=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    try:
        await db.password_reset_tokens.create_index("token_hash", unique=True)
    except Exception:
        pass
    await db.login_attempts.create_index("email")
    await db.login_attempts.create_index("identifier")
    await db.password_reset_requests.create_index("email")
    await db.password_reset_requests.create_index("created_at", expireAfterSeconds=900)
    # super admin (pemilik aplikasi)
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
    admin_pw = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({"email": admin_email, "password_hash": hash_password(admin_pw),
                                   "name": "Super Admin", "role": "superadmin", "token_version": 0,
                                   "created_at": now_iso()})
    else:
        upd = {}
        if not verify_password(admin_pw, existing["password_hash"]):
            upd["password_hash"] = hash_password(admin_pw)
        if existing.get("role") != "superadmin":
            upd["role"] = "superadmin"
        if upd:
            await db.users.update_one({"email": admin_email}, {"$set": upd})
    # demo users per peran yang direncanakan (idempoten)
    demo_users = [
        {"email": "admin@sbb.co.id", "password": "admin123", "name": "Administrator", "role": "admin"},
        {"email": "keuangan@sbb.co.id", "password": "keuangan123", "name": "Staff Keuangan", "role": "keuangan"},
        {"email": "approver@sbb.co.id", "password": "approver123", "name": "Approver Otorisasi", "role": "approver"},
        {"email": "pemohon@sbb.co.id", "password": "pemohon123", "name": "Pemohon", "role": "user"},
    ]
    for du in demo_users:
        if not await db.users.find_one({"email": du["email"]}):
            await db.users.insert_one({"email": du["email"], "password_hash": hash_password(du["password"]),
                                       "name": du["name"], "role": du["role"], "token_version": 0,
                                       "active": True, "created_at": now_iso()})
    # migrasi: pastikan semua user punya field 'active'
    await db.users.update_many({"active": {"$exists": False}}, {"$set": {"active": True}})
    # COA
    if await db.accounts.count_documents({}) == 0:
        for a in DEFAULT_COA:
            await db.accounts.insert_one({**a, "id": str(uuid.uuid4())})
    # tax settings
    if not await db.tax_settings.find_one({"key": "default"}):
        await db.tax_settings.insert_one(dict(DEFAULT_TAX_SETTINGS))
    # migrasi: pastikan PPH21 progresif & PPH42_KONSTRUKSI tiered tersedia pada data lama
    ts = await db.tax_settings.find_one({"key": "default"})
    if ts:
        default_map = {t["code"]: t for t in DEFAULT_TAX_SETTINGS["taxes"]}
        changed = False
        for t in ts.get("taxes", []):
            if t.get("code") in ("PPH21", "PPH42_KONSTRUKSI") and not t.get("mode", "flat") in ("progressive", "tiered"):
                src = default_map.get(t["code"], {})
                t["mode"] = src.get("mode", "flat")
                t["name"] = src.get("name", t.get("name"))
                if src.get("brackets"):
                    t["brackets"] = src["brackets"]
                if src.get("tiers"):
                    t["tiers"] = src["tiers"]
                changed = True
        if changed:
            await db.tax_settings.update_one({"key": "default"}, {"$set": {"taxes": ts["taxes"]}})


@app.on_event("startup")
async def on_startup():
    await seed()
    try:
        init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000"), "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
