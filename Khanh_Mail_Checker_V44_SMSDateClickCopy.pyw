import json
import tempfile
import zipfile
import shutil
import base64
import hashlib
import hmac
import struct
import re
import sys
import os
import subprocess
import time
import calendar
import datetime
import threading
import concurrent.futures
import urllib.request
import urllib.parse
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

APP_TITLE = "Khánh Mail Checker V44 SMS Date Click Copy"
APP_VERSION = "44"
DEFAULT_UPDATE_URL = ""
# Bản OneFile: chỉ cần mở file .pyw này. providers.json/history sẽ tự tạo nếu cần.

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", re.I)

PROVIDERS = {
    "gonvl": {
        "name": "Gonvl.pro",
        "type": "gonvl",
        "url": "https://emailscan.jaydinsta01.workers.dev/",
        "limit": 10,
        "delay": 0.05,
        "retry": 2,
        "workers": 3,
        "enabled": True,
        "api_key": ""
    },
    "emailscan": {
        "name": "EmailScan.in",
        "type": "emailscan",
        "url": "https://emailscan.in/api/v1/email-check",
        "limit": 50000,
        "enabled": False,
        "api_key": ""
    },
    "checkmail_live": {
        "name": "Checkmail.live",
        "type": "checkmail_live",
        "url": "https://checkmail.live/check/",
        "limit": 1000,
        "enabled": False,
        "api_key": "",
        "fastCheck": True
    }
}

PROVIDER_ORDER = ["gonvl", "emailscan", "checkmail_live"]

STATUS_PRIORITY = {
    "LIVE": 100,
    "VERIFYED": 90,
    "VERIFY_PHONE": 88,
    "DISABLED": 60,
    "WRONG": 35,
    "NOTEXISTS": 30,
    "DIE": 20,
    "UNKNOW": 0,
    "": 0
}

# Color theme
BG = "#07111f"
PANEL = "#0f172a"
CARD = "#111827"
CARD2 = "#162033"
TEXT = "#e5e7eb"
MUTED = "#94a3b8"
BORDER = "#263449"
BLUE = "#38bdf8"
GREEN = "#22c55e"
PURPLE = "#a78bfa"
RED = "#fb7185"
YELLOW = "#facc15"
ORANGE = "#fb923c"
GRAY = "#64748b"


def app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


CONFIG_FILE = app_dir() / "providers.json"
UPDATE_CONFIG_FILE = app_dir() / "update_config.json"


def default_config():
    return {
        "providers": PROVIDERS,
        "ui": {
            "geometry": "",
            "mode": "Gonvl.pro",
            "speed": "Nhanh x3",
            "keep_blank": False,
            "input_compact": False
        }
    }


def load_config():
    if not CONFIG_FILE.exists():
        save_config(default_config())
        return default_config()

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        cfg = default_config()
        old = (data or {}).get("providers", {})
        for key, value in old.items():
            if key in cfg["providers"] and isinstance(value, dict):
                cfg["providers"][key].update(value)

        old_ui = (data or {}).get("ui", {})
        if isinstance(old_ui, dict):
            cfg["ui"].update(old_ui)

        cfg["providers"]["gonvl"]["limit"] = 10
        cfg["providers"]["gonvl"].setdefault("delay", 0.05)
        cfg["providers"]["gonvl"].setdefault("retry", 2)
        cfg["providers"]["gonvl"].setdefault("workers", 3)
        return cfg
    except Exception:
        save_config(default_config())
        return default_config()



def load_update_config():
    data = {"update_url": DEFAULT_UPDATE_URL}
    try:
        if UPDATE_CONFIG_FILE.exists():
            with UPDATE_CONFIG_FILE.open("r", encoding="utf-8") as f:
                old = json.load(f) or {}
            if isinstance(old, dict):
                data.update(old)
    except Exception:
        pass
    return data

def save_update_config(data):
    try:
        with UPDATE_CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(data or {}, f, ensure_ascii=False, indent=4)
    except Exception:
        pass


def save_config(cfg):
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)


def parse_input_rows(text):
    rows = []
    for line in (text or "").splitlines():
        if not line.strip():
            rows.append({"kind": "blank", "email": "", "raw": line})
            continue

        emails = EMAIL_RE.findall(line)
        if not emails:
            rows.append({"kind": "blank", "email": "", "raw": line})
            continue

        for email in emails:
            rows.append({"kind": "email", "email": email.strip(), "raw": line})
    return rows


def rows_to_email_list(rows):
    return [r["email"] for r in rows if r.get("kind") == "email" and r.get("email")]


def unique_keep_order(items):
    seen = set()
    out = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def remove_duplicate_rows_keep_blank(rows):
    seen = set()
    out = []
    for row in rows:
        if row.get("kind") != "email":
            out.append(row)
            continue
        key = row.get("email", "").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def rows_to_input_text(rows):
    return "\n".join([r.get("email", "") if r.get("kind") == "email" else "" for r in rows])


def chunks(items, size):
    for i in range(0, len(items), size):
        yield i, items[i:i + size]


def detect_status_word(text):
    s = str(text or "").upper()
    s = s.replace("-", "_").replace(" ", "_").replace(".", "_").replace("/", "_").replace("|", "_").replace(":", "_")

    checks = [
        ("VERIFY_PHONE", "VERIFY_PHONE"),
        ("PHONE_VERIFY", "VERIFY_PHONE"),
        ("VERIFYED", "VERIFYED"),
        ("VERIFIED", "VERIFYED"),
        ("VERIFY", "VERIFYED"),
        ("NOT_EXISTS", "NOTEXISTS"),
        ("NOT_EXIST", "NOTEXISTS"),
        ("NOTEXISTS", "NOTEXISTS"),
        ("NOTEXIST", "NOTEXISTS"),
        ("NOT_FOUND", "NOTEXISTS"),
        ("DISABLED", "DISABLED"),
        ("DISABLE", "DISABLED"),
        ("LOCKED", "DISABLED"),
        ("SUSPENDED", "DISABLED"),
        ("UNKNOWN", "UNKNOW"),
        ("UNKNOW", "UNKNOW"),
        ("WRONG", "WRONG"),
        ("INVALID", "WRONG"),
        ("DEAD", "DIE"),
        ("DIE", "DIE"),
        ("LIVE", "LIVE"),
        ("VALID", "LIVE"),
        ("OK", "LIVE"),
    ]
    for needle, status in checks:
        if needle in s:
            return status
    return ""


def normalize_status(status):
    raw = str(status or "").strip().upper()

    if EMAIL_RE.search(raw):
        first = raw.replace("\r", "\n").splitlines()[0]
        email_match = EMAIL_RE.search(first)
        if email_match:
            before = first[:email_match.start()]
            after = first[email_match.end():]
            raw = detect_status_word(before) or detect_status_word(after) or detect_status_word(first) or raw

    raw = raw.replace("-", "_").replace(" ", "_").replace(".", "_").replace("/", "_").replace("|", "_").replace(":", "_")
    raw = re.sub(r"[^A-Z_]", "", raw)

    mapping = {
        "LIVE": "LIVE",
        "VALID": "LIVE",
        "OK": "LIVE",
        "SUCCESS": "LIVE",
        "VERIFYED": "VERIFYED",
        "VERIFIED": "VERIFYED",
        "VERIFY": "VERIFYED",
        "VERIFY_PHONE": "VERIFY_PHONE",
        "PHONE_VERIFY": "VERIFY_PHONE",
        "PHONE": "VERIFY_PHONE",
        "NEED_PHONE": "VERIFY_PHONE",
        "DISABLED": "DISABLED",
        "DISABLE": "DISABLED",
        "LOCKED": "DISABLED",
        "SUSPENDED": "DISABLED",
        "NOT_EXIST": "NOTEXISTS",
        "NOT_EXISTS": "NOTEXISTS",
        "NOTEXIST": "NOTEXISTS",
        "NOTEXISTS": "NOTEXISTS",
        "NOT_FOUND": "NOTEXISTS",
        "NO_EXIST": "NOTEXISTS",
        "WRONG": "WRONG",
        "INVALID": "WRONG",
        "ERROR": "WRONG",
        "DIE": "DIE",
        "DEAD": "DIE",
        "UNKNOWN": "UNKNOW",
        "UNKNOW": "UNKNOW",
        "OTHER": "UNKNOW",
    }

    return mapping.get(raw, detect_status_word(raw) or "UNKNOW")



def display_status(status):
    """Status hiển thị/copy theo chữ thường."""
    return normalize_status(status).lower()

def status_from_key(key):
    return detect_status_word(key)


def find_email_in_obj(obj):
    if not isinstance(obj, dict):
        return ""
    for key in ["email", "mail", "gmail", "account", "value"]:
        val = obj.get(key)
        if isinstance(val, str):
            m = EMAIL_RE.search(val)
            if m:
                return m.group(0)
    for val in obj.values():
        if isinstance(val, str):
            m = EMAIL_RE.search(val)
            if m:
                return m.group(0)
    return ""


def parse_status_email_line(line, parent_status=""):
    out = []
    for part in str(line or "").replace("\r", "\n").splitlines():
        if not part.strip():
            continue

        emails = EMAIL_RE.findall(part)
        if not emails:
            continue

        for email in emails:
            m = re.search(re.escape(email), part, flags=re.I)
            before = part[:m.start()] if m else ""
            after = part[m.end():] if m else ""

            st = (
                detect_status_word(before)
                or detect_status_word(after)
                or detect_status_word(part)
                or normalize_status(parent_status)
            )

            out.append((email.strip(), st or "UNKNOW"))
    return out


def api_post_json(url, payload_obj, headers, timeout=90):
    data = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
        raise RuntimeError(f"HTTP {e.code}: {detail[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Lỗi kết nối: {e.reason}")
    except Exception as e:
        raise RuntimeError(str(e))

    try:
        return json.loads(body)
    except Exception:
        return body


def parse_flexible_result(obj):
    status_map = {}

    def put(email, status):
        email = str(email or "").strip()
        if not email:
            return
        m = EMAIL_RE.search(email)
        if not m:
            return
        email = m.group(0)
        status_map[email.lower()] = normalize_status(status)

    def walk(value, parent_status=""):
        if isinstance(value, str):
            pairs = parse_status_email_line(value, parent_status)
            if pairs:
                for email, status in pairs:
                    put(email, status)
                return

            if parent_status:
                for email in EMAIL_RE.findall(value):
                    put(email, parent_status)
            return

        if isinstance(value, list):
            for item in value:
                walk(item, parent_status)
            return

        if isinstance(value, dict):
            email = find_email_in_obj(value)
            status = (
                value.get("status")
                or value.get("result")
                or value.get("state")
                or value.get("type")
                or value.get("category")
                or parent_status
            )
            if email:
                put(email, status)

            for k, v in value.items():
                st = status_from_key(k) or parent_status
                walk(v, st)
            return

    walk(obj)
    return status_map


def gonvl_headers():
    return {
        "accept": "*/*",
        "accept-language": "vi",
        "content-type": "application/json",
        "origin": "https://check.gonvl.pro",
        "referer": "https://check.gonvl.pro/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    }



def check_gonvl(provider, emails, progress_cb=None):
    """
    Gonvl API ổn nhất khi mỗi request chỉ gửi 10 mail.
    V12 tăng tốc bằng cách chạy nhiều lô 10 mail song song.
    """
    all_status = {}
    limit = 10
    retry = int(provider.get("retry", 2))
    workers = int(provider.get("workers", 3))
    workers = max(1, min(workers, 8))
    total = len(emails)

    batches = list(chunks(emails, limit))
    done_count = 0

    def run_one_batch(start, batch):
        last_error = None

        for attempt in range(retry + 1):
            try:
                obj = api_post_json(
                    provider["url"],
                    {"emails": batch},
                    headers=gonvl_headers(),
                    timeout=90
                )
                parsed = parse_flexible_result(obj)
                return start, batch, parsed, ""
            except Exception as e:
                last_error = str(e)
                time.sleep(0.45 + attempt * 0.25)

        return start, batch, {}, last_error or "batch failed"

    if progress_cb:
        progress_cb(0, total, f"Gonvl Turbo: {total:,} mail | 10/lô × {workers} luồng")

    # Chạy song song nhiều batch. Không raise nếu một vài lô lỗi: email lô đó sẽ UNKNOW.
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(run_one_batch, start, batch): (start, batch)
            for start, batch in batches
        }

        for future in concurrent.futures.as_completed(future_map):
            start, batch = future_map[future]
            try:
                batch_start, batch_items, parsed, error = future.result()
            except Exception as e:
                batch_start, batch_items, parsed, error = start, batch, {}, str(e)

            if parsed:
                all_status.update(parsed)

            done_count += len(batch_items)
            if progress_cb:
                if parsed:
                    msg = f"Gonvl Turbo: xong {min(done_count, total):,}/{total:,} | {workers} luồng"
                else:
                    msg = f"Gonvl Turbo: lô {batch_start + 1}-{min(batch_start + len(batch_items), total)} lỗi/UNKNOW | {min(done_count, total):,}/{total:,}"
                progress_cb(min(done_count, total), total, msg)

    return all_status


def check_emailscan(provider, emails, progress_cb=None):
    api_key = provider.get("api_key", "").strip()
    if not api_key:
        raise RuntimeError("Thiếu x-api-key EmailScan.in")
    if len(emails) > 50000:
        raise RuntimeError("EmailScan.in chỉ cho tối đa 50,000 email / request")

    if progress_cb:
        progress_cb(0, len(emails), "Đang chạy EmailScan.in...")

    obj = api_post_json(
        provider["url"],
        emails,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "User-Agent": "Khanh-Mail-Checker/44.0"
        },
        timeout=300
    )
    return parse_flexible_result(obj)


def check_checkmail_live(provider, emails, progress_cb=None):
    api_key = provider.get("api_key", "").strip()
    if not api_key:
        raise RuntimeError("Thiếu api_key Checkmail.live")

    all_status = {}
    total = len(emails)
    for start, batch in chunks(emails, 1000):
        if progress_cb:
            progress_cb(start, total, f"Checkmail.live: {start + 1}-{min(start + len(batch), total)} / {total}")

        payload = {
            "api_key": api_key,
            "fastCheck": bool(provider.get("fastCheck", True)),
            "emails": batch
        }
        obj = api_post_json(
            provider["url"],
            payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Khanh-Mail-Checker/44.0"
            },
            timeout=120
        )

        if isinstance(obj, dict) and "status" in obj and obj.get("status", False) is False and "data" not in obj:
            raise RuntimeError(str(obj.get("message") or "Checkmail.live báo lỗi"))

        data = obj.get("data", []) if isinstance(obj, dict) else []
        for item in data:
            if isinstance(item, dict):
                email = str(item.get("email", "")).strip()
                status = normalize_status(item.get("status", "UNKNOW"))
                if email:
                    all_status[email.lower()] = status

    return all_status


def check_provider(provider, emails, progress_cb=None):
    ptype = provider.get("type")
    if ptype == "gonvl":
        return check_gonvl(provider, emails, progress_cb)
    if ptype == "emailscan":
        return check_emailscan(provider, emails, progress_cb)
    if ptype == "checkmail_live":
        return check_checkmail_live(provider, emails, progress_cb)
    raise RuntimeError("Provider chưa hỗ trợ: " + str(ptype))


def choose_best_status(old_status, new_status):
    old_status = normalize_status(old_status)
    new_status = normalize_status(new_status)
    return new_status if STATUS_PRIORITY.get(new_status, 0) >= STATUS_PRIORITY.get(old_status, 0) else old_status



SMS_LINK_RE = re.compile(r"(?:https?://)?(?:www\.)?sms222\.us/?\?token=[^\s]+", re.I)
TOKEN_RE = re.compile(r"token=([^&\s]+)", re.I)

def extract_sms_links(text):
    """Tách link SMS222 từ text, giữ dòng trống."""
    rows = []
    for line in (text or "").splitlines():
        raw = line.strip()
        if not raw:
            rows.append({"kind": "blank", "link": "", "token": ""})
            continue

        found = SMS_LINK_RE.findall(raw)
        if not found:
            # Nếu user chỉ paste token, vẫn nhận.
            if re.fullmatch(r"[A-Za-z0-9_\-]{8,}", raw):
                link = "https://sms222.us/?token=" + raw
                rows.append({"kind": "sms", "link": link, "token": raw})
            else:
                rows.append({"kind": "blank", "link": "", "token": ""})
            continue

        for link in found:
            if not link.lower().startswith("http"):
                link = "https://" + link
            m = TOKEN_RE.search(link)
            token = urllib.parse.unquote(m.group(1)) if m else ""
            rows.append({"kind": "sms", "link": link, "token": token})
    return rows

def parse_sms_code_from_text(text):
    """Bắt mã OTP/SMS từ HTML/JSON/text. Ưu tiên mã 4-8 số."""
    s = str(text or "")

    # Nếu JSON, thử đọc các field hay gặp.
    try:
        obj = json.loads(s)
        candidates = []

        def walk(v):
            if isinstance(v, dict):
                for k, val in v.items():
                    key = str(k).lower()
                    if key in {"code", "otp", "sms", "message", "msg", "text", "content", "body"}:
                        candidates.append(str(val))
                    walk(val)
            elif isinstance(v, list):
                for item in v:
                    walk(item)
            elif isinstance(v, str):
                candidates.append(v)

        walk(obj)
        for c in candidates:
            code = parse_sms_code_from_text(c)
            if code and code != "không có mã":
                return code
    except Exception:
        pass

    # Ưu tiên pattern có chữ code/otp/mã.
    patterns = [
        r"(?:code|otp|mã|ma|verification|verify)[^\d]{0,20}(\d{4,8})",
        r"(\d{4,8})[^\d]{0,20}(?:code|otp|mã|ma)",
    ]
    for pat in patterns:
        m = re.search(pat, s, flags=re.I)
        if m:
            return m.group(1)

    # Fallback: mã số 4-8 chữ số, tránh số quá dài.
    nums = re.findall(r"(?<!\d)(\d{4,8})(?!\d)", s)
    if nums:
        # ưu tiên mã 6 số, rồi 4-8 số đầu tiên
        for n in nums:
            if len(n) == 6:
                return n
        return nums[0]

    return "không có mã"


def parse_sms_date_from_text(text):
    """Tìm date trong response SMS222. Ưu tiên format YYYY-MM-DD rồi đổi sang DD/MM/YYYY."""
    s = str(text or "")

    # Nếu JSON, quét toàn bộ string bên trong.
    try:
        obj = json.loads(s)
        candidates = []

        def walk(v):
            if isinstance(v, dict):
                for k, val in v.items():
                    key = str(k).lower()
                    if key in {"date", "time", "created_at", "updated_at", "message", "msg", "text", "content", "body"}:
                        candidates.append(str(val))
                    walk(val)
            elif isinstance(v, list):
                for item in v:
                    walk(item)
            elif isinstance(v, str):
                candidates.append(v)

        walk(obj)
        for c in candidates:
            d = parse_sms_date_from_text(c)
            if d and d != "không có date":
                return d
    except Exception:
        pass

    # Pattern giống tool CodeVIPSupers: có dấu | trước date.
    patterns = [
        r"\|\s*(\d{4})-(\d{2})-(\d{2})",
        r"(\d{4})-(\d{2})-(\d{2})",
        r"(\d{2})/(\d{2})/(\d{4})",
    ]

    for pat in patterns:
        m = re.search(pat, s)
        if not m:
            continue

        if pat.startswith("(\\d{2})"):
            day, month, year = m.groups()
            return f"{day}/{month}/{year}"

        year, month, day = m.groups()
        return f"{day}/{month}/{year}"

    return "không có date"

def fetch_sms_date(link, timeout=45):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "text/html,application/json,text/plain,*/*",
        "Accept-Language": "vi,en;q=0.9",
        "Referer": "https://sms222.us/"
    }

    req = urllib.request.Request(link, method="GET", headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return "lỗi: " + str(e)[:80]

    return parse_sms_date_from_text(body)

def fetch_sms_code(link, timeout=45):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "text/html,application/json,text/plain,*/*",
        "Accept-Language": "vi,en;q=0.9",
        "Referer": "https://sms222.us/"
    }

    req = urllib.request.Request(link, method="GET", headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return "lỗi: " + str(e)[:80]

    return parse_sms_code_from_text(body)



BASE32_RE = re.compile(r"[A-Z2-7]{10,}=*", re.I)

def extract_2fa_secret(raw):
    """Nhận secret thường, otpauth://..., 2fa.live/tok/..., hoặc dòng chứa email|secret."""
    s = str(raw or "").strip()
    if not s:
        return ""

    decoded = urllib.parse.unquote(s)

    m = re.search(r"(?:secret|key)=([^&\s]+)", decoded, flags=re.I)
    if m:
        candidate = m.group(1)
    else:
        m = re.search(r"/tok/([^/?#\s]+)", decoded, flags=re.I)
        if m:
            candidate = m.group(1)
        else:
            compact = decoded.upper().replace(" ", "").replace("-", "")
            possible = BASE32_RE.findall(compact)
            if possible:
                candidate = max(possible, key=len)
            else:
                candidate = decoded

    secret = str(candidate).strip().upper()
    secret = re.sub(r"[^A-Z2-7=]", "", secret)
    return secret

def calc_totp(secret, timestep=30, digits=6, for_time=None):
    if for_time is None:
        for_time = int(time.time())

    clean = extract_2fa_secret(secret)
    if not clean:
        return "không có secret"

    clean = clean.replace("=", "")
    pad = "=" * ((8 - len(clean) % 8) % 8)

    try:
        key = base64.b32decode((clean + pad).encode("ascii"), casefold=True)
    except Exception:
        return "secret lỗi"

    counter = int(for_time // timestep)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    code_num = binary % (10 ** digits)
    return str(code_num).zfill(digits)

def extract_2fa_rows(text):
    rows = []
    for line in (text or "").splitlines():
        raw = line.strip()
        if not raw:
            rows.append({"kind": "blank", "raw": "", "secret": ""})
            continue

        secret = extract_2fa_secret(raw)
        if not secret:
            rows.append({"kind": "blank", "raw": raw, "secret": ""})
        else:
            rows.append({"kind": "2fa", "raw": raw, "secret": secret})
    return rows



def card_pad(n):
    return str(n).zfill(2)

def card_normalize_spaces(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def card_extract_number(line):
    nums = re.findall(r"\d+", str(line or ""))
    for x in nums:
        if 12 <= len(x) <= 19:
            return x

    grouped = re.findall(r"(?:\d[\s-]*){12,19}", str(line or ""))
    for g in grouped:
        digits = re.sub(r"\D", "", g)
        if 12 <= len(digits) <= 19:
            return digits
    return ""

def card_parse_expiry(line):
    s = str(line or "").strip()
    if not s:
        return None

    nums = re.findall(r"\d+", s)
    if not nums or len(nums) < 3:
        return None

    card_index = -1
    for i, x in enumerate(nums):
        if 12 <= len(x) <= 19:
            card_index = i
            break

    candidates = []
    if card_index >= 0 and card_index + 2 < len(nums):
        candidates.append((nums[card_index + 1], nums[card_index + 2]))

    for i in range(len(nums) - 1):
        candidates.append((nums[i], nums[i + 1]))

    for mm_raw, yy_raw in candidates:
        try:
            mm = int(mm_raw)
        except Exception:
            continue
        if not (1 <= mm <= 12):
            continue
        if len(yy_raw) not in (2, 4):
            continue

        try:
            year = int(yy_raw)
        except Exception:
            continue
        if len(yy_raw) == 2:
            year += 2000
        if not (2000 <= year <= 2099):
            continue

        return {"month": mm, "year": year, "rawYear": yy_raw}
    return None

def card_last_day(year, month):
    return datetime.date(year, month, calendar.monthrange(year, month)[1])

def card_get_tail_after_expiry(line, exp):
    if not exp:
        return card_normalize_spaces(line)

    card = card_extract_number(line)
    if not card:
        return card_normalize_spaces(line)

    all_nums = list(re.finditer(r"\d+", str(line or "")))
    card_pos = -1
    for m in all_nums:
        if m.group(0) == card:
            card_pos = m.start()
            break

    if card_pos < 0:
        return card_normalize_spaces(line)

    for i in range(len(all_nums) - 1):
        mm = int(all_nums[i].group(0))
        yy = all_nums[i + 1].group(0)
        year = int(yy)
        if len(yy) == 2:
            year += 2000

        if mm == exp["month"] and year == exp["year"] and all_nums[i].start() > card_pos:
            end_pos = all_nums[i + 1].end()
            return card_normalize_spaces(str(line)[end_pos:])

    return card_normalize_spaces(line)

def card_dedupe_key(line, mode="card_exp_tail"):
    trimmed = str(line or "").strip()

    if mode == "line":
        return "line:" + trimmed

    card = card_extract_number(line)
    if not card:
        return "line:" + trimmed

    if mode == "card_only":
        return "card:" + card

    exp = card_parse_expiry(line)
    if not exp:
        return "line:" + trimmed

    tail = card_get_tail_after_expiry(line, exp)
    return f"card_exp_tail:{card}|{card_pad(exp['month'])}|{exp['year']}|{tail}"

def card_mask_line(line):
    def repl(m):
        s = m.group(0)
        if len(s) <= 10:
            return s
        return s[:6] + ("*" * (len(s) - 10)) + s[-4:]
    return re.sub(r"\b\d{12,19}\b", repl, str(line or ""))


def card_year_to_yy_line(line):
    """Đổi đúng năm hạn thẻ 4 số như 2027 thành 27, không đụng phần đuôi khác."""
    s = str(line or "")
    exp = card_parse_expiry(s)
    if not exp:
        return s

    card = card_extract_number(s)
    if not card:
        return s

    all_nums = list(re.finditer(r"\d+", s))
    card_pos = -1
    for m in all_nums:
        if m.group(0) == card:
            card_pos = m.start()
            break

    if card_pos < 0:
        return s

    for i in range(len(all_nums) - 1):
        mm_raw = all_nums[i].group(0)
        yy_raw = all_nums[i + 1].group(0)

        try:
            mm = int(mm_raw)
            year = int(yy_raw)
        except Exception:
            continue

        if len(yy_raw) == 2:
            year += 2000

        if (
            mm == exp["month"]
            and year == exp["year"]
            and len(yy_raw) == 4
            and yy_raw.startswith("20")
            and all_nums[i].start() > card_pos
        ):
            m = all_nums[i + 1]
            return s[:m.start()] + yy_raw[-2:] + s[m.end():]

    return s


def card_format_item(item, mode="original"):
    line = card_year_to_yy_line(item.get("line", ""))
    if item.get("kind") in {"invalid", "duplicate"}:
        return line
    if mode == "masked":
        return card_mask_line(line)
    if mode == "expiry":
        return f"{card_pad(item.get('month', 0))}/{str(item.get('year', ''))[-2:]}  |  {line}"
    return line

def card_filter_lines(text, check_date_iso=None, dedupe_mode="card_exp_tail", auto_dedupe=True):
    if not check_date_iso:
        check_date = datetime.date.today()
    else:
        try:
            check_date = datetime.date.fromisoformat(check_date_iso)
        except Exception:
            check_date = datetime.date.today()

    results = {
        "valid": [],
        "expired": [],
        "invalid": [],
        "duplicate": [],
        "all": [],
        "uniqueLines": [],
        "total": 0
    }

    seen = set()
    for line in str(text or "").splitlines():
        if not line.strip():
            continue

        results["total"] += 1
        key = card_dedupe_key(line, dedupe_mode)
        is_dup = key in seen

        if is_dup:
            item = {"kind": "duplicate", "line": line}
            results["duplicate"].append(item)
            results["all"].append({**item, "label": "TRÙNG"})
            if auto_dedupe:
                continue
        else:
            seen.add(key)
            results["uniqueLines"].append(line)

        exp = card_parse_expiry(line)
        if not exp:
            item = {"kind": "invalid", "line": line}
            results["invalid"].append(item)
            results["all"].append({**item, "label": "LỖI"})
            continue

        end = card_last_day(exp["year"], exp["month"])
        item = {"kind": "", "line": line, "month": exp["month"], "year": exp["year"], "end": end}

        if end < check_date:
            item["kind"] = "expired"
            results["expired"].append(item)
            results["all"].append({**item, "label": "HẾT HẠN"})
        else:
            item["kind"] = "valid"
            results["valid"].append(item)
            results["all"].append({**item, "label": "CÒN HẠN"})

    return results



def restore_normalize_key(s):
    return str(s or "").strip().lower()

def restore_loose_key(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())

def restore_format_time(ts):
    try:
        return datetime.datetime.fromtimestamp(float(ts)).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return ""

def restore_collect_files(paths, max_files=300000):
    files = []
    seen = set()

    for raw in paths:
        if not raw:
            continue

        p = Path(raw)
        try:
            rp = str(p.resolve()).lower()
        except Exception:
            rp = str(p).lower()

        if p.is_file():
            if rp not in seen:
                seen.add(rp)
                try:
                    st = p.stat()
                    files.append({
                        "path": str(p),
                        "name": p.name,
                        "mtime": st.st_mtime,
                        "size": st.st_size
                    })
                except Exception:
                    pass
            continue

        if p.is_dir():
            for root, dirs, names in os.walk(str(p)):
                for name in names:
                    fp = Path(root) / name
                    try:
                        rfp = str(fp.resolve()).lower()
                    except Exception:
                        rfp = str(fp).lower()

                    if rfp in seen:
                        continue

                    seen.add(rfp)
                    try:
                        st = fp.stat()
                        files.append({
                            "path": str(fp),
                            "name": fp.name,
                            "mtime": st.st_mtime,
                            "size": st.st_size
                        })
                    except Exception:
                        pass

                    if len(files) >= max_files:
                        return files

    return files

def restore_match_one(key, files, mode="newest"):
    key = restore_normalize_key(key)
    loose = restore_loose_key(key)
    if not key:
        return None

    matches = []
    for f in files:
        name_l = str(f.get("name", "")).lower()
        path_l = str(f.get("path", "")).lower()
        loose_name = restore_loose_key(f.get("name", ""))
        loose_path = restore_loose_key(f.get("path", ""))

        score = 0
        if key in name_l:
            score += 120
        elif loose and loose in loose_name:
            score += 100
        elif key in path_l:
            score += 80
        elif loose and loose in loose_path:
            score += 60
        else:
            continue

        # Ưu tiên tên có restore/rt nếu người dùng chọn kiểu ưu tiên restore.
        restore_words = ["restore", "restored", "rt", "recover", "recovery"]
        if any(w in name_l for w in restore_words):
            score += 35

        matches.append((score, f))

    if not matches:
        return None

    if mode == "oldest":
        matches.sort(key=lambda x: (x[1].get("mtime", 0), -x[0]))
    elif mode == "restore_first":
        matches.sort(key=lambda x: (x[0], x[1].get("mtime", 0)), reverse=True)
    else:
        matches.sort(key=lambda x: (x[1].get("mtime", 0), x[0]), reverse=True)

    return matches[0][1]

def restore_build_results(input_text, files, mode="newest"):
    rows = []
    for line in str(input_text or "").splitlines():
        raw = line.strip()
        if not raw:
            rows.append({"kind": "blank", "key": "", "date": "", "file": "", "path": ""})
            continue

        match = restore_match_one(raw, files, mode)
        if match:
            rows.append({
                "kind": "found",
                "key": raw,
                "date": restore_format_time(match.get("mtime", 0)),
                "file": match.get("name", ""),
                "path": match.get("path", "")
            })
        else:
            rows.append({"kind": "notfound", "key": raw, "date": "", "file": "", "path": ""})
    return rows


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x700")
        self.minsize(900, 620)
        self.configure(bg=BG)

        self.cfg = load_config()
        saved_geometry = self.cfg.get("ui", {}).get("geometry", "")
        if saved_geometry:
            try:
                self.geometry(saved_geometry)
            except Exception:
                pass

        self.running = False
        self.results = []
        self.sms_overlay = None
        self.twofa_overlay = None
        self.card_overlay = None
        self.restore_overlay = None
        self.update_overlay = None
        self.multirun_overlay = None
        self.mini_mode = False
        self.mini_hidden_widgets = []

        self.setup_style()
        self._build_ui()
        self.apply_saved_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_style(self):
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        self.style.configure(".", font=("Segoe UI", 9))
        self.style.configure("Root.TFrame", background=BG)
        self.style.configure("Panel.TFrame", background=PANEL)
        self.style.configure("Card.TFrame", background=CARD)
        self.style.configure("TLabel", background=BG, foreground=TEXT)
        self.style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        self.style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 15, "bold"))
        self.style.configure("Sub.TLabel", background=BG, foreground=BLUE, font=("Segoe UI", 9, "bold"))

        self.style.configure("Dark.TLabelframe", background=PANEL, foreground=TEXT, bordercolor=BORDER, relief="flat")
        self.style.configure("Dark.TLabelframe.Label", background=PANEL, foreground=BLUE, font=("Segoe UI", 9, "bold"))

        self.style.configure("Accent.TButton", background=BLUE, foreground="#06101d", borderwidth=0, focusthickness=0, padding=(10, 6), font=("Segoe UI", 9, "bold"))
        self.style.map("Accent.TButton", background=[("active", "#7dd3fc"), ("disabled", "#334155")])

        self.style.configure("Green.TButton", background=GREEN, foreground="#06101d", borderwidth=0, padding=(10, 6), font=("Segoe UI", 9, "bold"))
        self.style.map("Green.TButton", background=[("active", "#86efac"), ("disabled", "#334155")])

        self.style.configure("Purple.TButton", background=PURPLE, foreground="#06101d", borderwidth=0, padding=(10, 6), font=("Segoe UI", 9, "bold"))
        self.style.map("Purple.TButton", background=[("active", "#c4b5fd")])

        self.style.configure("Danger.TButton", background=RED, foreground="#06101d", borderwidth=0, padding=(10, 6), font=("Segoe UI", 9, "bold"))
        self.style.map("Danger.TButton", background=[("active", "#fda4af")])

        self.style.configure("Dark.TButton", background=CARD2, foreground=TEXT, borderwidth=0, padding=(10, 6), font=("Segoe UI", 9, "bold"))
        self.style.map("Dark.TButton", background=[("active", "#25324a")])

        self.style.configure("TCombobox", fieldbackground=CARD, background=CARD2, foreground=TEXT, arrowcolor=BLUE, bordercolor=BORDER)

        self.style.configure("Treeview",
                             background=CARD,
                             foreground=TEXT,
                             fieldbackground=CARD,
                             borderwidth=0,
                             rowheight=26,
                             font=("Segoe UI", 9))
        self.style.configure("Treeview.Heading",
                             background="#1e293b",
                             foreground=BLUE,
                             relief="flat",
                             font=("Segoe UI", 9, "bold"))
        self.style.map("Treeview", background=[("selected", "#075985")], foreground=[("selected", "#ffffff")])

        self.style.configure("Horizontal.TProgressbar",
                             background=BLUE,
                             troughcolor="#0b1220",
                             bordercolor=BORDER,
                             lightcolor=BLUE,
                             darkcolor=BLUE)

        self.style.configure("TCheckbutton", background=BG, foreground=TEXT)
        self.style.map("TCheckbutton", background=[("active", BG)], foreground=[("active", TEXT)])

    def _build_ui(self):
        root = ttk.Frame(self, style="Root.TFrame", padding=10)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root, style="Root.TFrame")
        header.pack(fill="x", pady=(0, 8))
        self.header_frame = header

        title_box = ttk.Frame(header, style="Root.TFrame")
        title_box.pack(side="left", fill="x", expand=True)

        ttk.Label(title_box, text="⚡ Khánh Mail Checker", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="SMS Date Copy • Mail • Thẻ", style="Sub.TLabel").pack(anchor="w")

        self.batch_label = ttk.Label(header, text="Turbo: 10 mail/lô × 3 luồng", style="Muted.TLabel")
        self.batch_label.pack(side="right", anchor="e", padx=(6, 0))

        self.update_bell_btn = tk.Button(
            header,
            text="🔔",
            command=self.open_update_tool,
            bg="#0b1220",
            fg="#38bdf8",
            activebackground="#1e293b",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=7,
            pady=3,
            font=("Segoe UI Emoji", 10, "bold"),
            cursor="hand2"
        )
        self.update_bell_btn.pack(side="right", padx=(0, 6))

        top = ttk.Frame(root, style="Panel.TFrame", padding=8)
        top.pack(fill="x", pady=(0, 8))
        self.top_toolbar = top

        # Hàng 1: nhóm check mail chính
        row1 = ttk.Frame(top, style="Panel.TFrame")
        row1.pack(fill="x")

        ttk.Label(
            row1,
            text="Check mail",
            background=PANEL,
            foreground=BLUE,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 10))

        ttk.Label(row1, text="API:", background=PANEL, foreground=MUTED).pack(side="left")
        self.mode_var = tk.StringVar(value=self.cfg.get("ui", {}).get("mode", "Gonvl.pro"))
        self.mode_box = ttk.Combobox(
            row1,
            textvariable=self.mode_var,
            state="readonly",
            width=14,
            values=["Gonvl.pro", "Auto fallback", "EmailScan.in", "Checkmail.live", "Chạy tất cả"]
        )
        self.mode_box.pack(side="left", padx=(5, 12))

        ttk.Label(row1, text="Tốc độ:", background=PANEL, foreground=MUTED).pack(side="left")
        self.speed_var = tk.StringVar(value=self.cfg.get("ui", {}).get("speed", "Nhanh x3"))
        self.speed_box = ttk.Combobox(
            row1,
            textvariable=self.speed_var,
            state="readonly",
            width=12,
            values=["An toàn x1", "Nhanh x3", "Rất nhanh x5", "Max x8"]
        )
        self.speed_box.pack(side="left", padx=(5, 12))

        self.check_btn = ttk.Button(row1, text="CHECK", command=self.start_check, style="Green.TButton", width=12)
        self.check_btn.pack(side="left", padx=(0, 6))
        ttk.Button(row1, text="AUTO", command=self.auto_detect_input, style="Accent.TButton", width=10).pack(side="left", padx=(0, 6))

        ttk.Label(row1, text="Tiến độ:", background=PANEL, foreground=MUTED).pack(side="left", padx=(10, 4))
        self.top_percent_var = tk.StringVar(value="0%")
        tk.Label(
            row1,
            textvariable=self.top_percent_var,
            bg="#0b1220",
            fg=BLUE,
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 8))

        self.more_tools_btn = ttk.Button(row1, text="Tiện ích ▼", command=self.toggle_more_tools, style="Dark.TButton", width=12)
        self.more_tools_btn.pack(side="left", padx=(0, 6))

        self.keep_blank_var = tk.BooleanVar(value=bool(self.cfg.get("ui", {}).get("keep_blank", False)))
        ttk.Checkbutton(row1, text="Copy giữ dòng cách", variable=self.keep_blank_var).pack(side="right", padx=(10, 0))

        # Khung tiện ích xổ xuống
        self.more_tools_frame = ttk.Frame(top, style="Panel.TFrame")
        self.more_tools_visible = False

        row2 = ttk.Frame(self.more_tools_frame, style="Panel.TFrame")
        row2.pack(fill="x")

        ttk.Label(
            row2,
            text="Dữ liệu:",
            background=PANEL,
            foreground=MUTED,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 6))
        ttk.Button(row2, text="Xóa trùng", command=self.remove_duplicate_input, style="Dark.TButton", width=11).pack(side="left", padx=3)
        self.retry_btn = ttk.Button(row2, text="Retry UNKNOWN", command=self.retry_unknown, style="Accent.TButton", width=14)
        self.retry_btn.pack(side="left", padx=3)
        ttk.Button(row2, text="Xóa", command=self.clear_all, style="Danger.TButton", width=9).pack(side="left", padx=3)

        ttk.Label(
            row2,
            text="Giao diện:",
            background=PANEL,
            foreground=MUTED,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(18, 6))
        ttk.Button(row2, text="Thu gọn", command=self.toggle_input_height, style="Dark.TButton", width=10).pack(side="left", padx=3)
        self.mini_btn = ttk.Button(row2, text="Mini mode", command=self.toggle_mini_mode, style="Green.TButton", width=11)
        self.mini_btn.pack(side="left", padx=3)

        row3 = ttk.Frame(self.more_tools_frame, style="Panel.TFrame")
        row3.pack(fill="x", pady=(8, 0))

        ttk.Label(
            row3,
            text="Công cụ:",
            background=PANEL,
            foreground=MUTED,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 6))
        ttk.Button(row3, text="Restore", command=self.open_restore_tool, style="Green.TButton", width=10).pack(side="left", padx=3)
        ttk.Button(row3, text="Thẻ", command=self.open_card_tool, style="Dark.TButton", width=9).pack(side="left", padx=3)
        ttk.Button(row3, text="SMS Pop", command=self.open_sms_popup, style="Accent.TButton", width=10).pack(side="left", padx=3)
        ttk.Button(row3, text="2FA Pop", command=self.open_2fa_popup, style="Purple.TButton", width=10).pack(side="left", padx=3)
        ttk.Button(row3, text="Thẻ Pop", command=self.open_card_popup, style="Dark.TButton", width=10).pack(side="left", padx=3)

        ttk.Label(
            row3,
            text="Hệ thống:",
            background=PANEL,
            foreground=MUTED,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(18, 6))
        ttk.Button(row3, text="API", command=self.open_api_dialog, style="Purple.TButton", width=9).pack(side="left", padx=3)

        # Copy nhanh + thống kê trạng thái
        quick_area = ttk.Frame(root, style="Root.TFrame")
        quick_area.pack(fill="x", pady=(0, 4))

        copybar = ttk.LabelFrame(quick_area, text="Copy nhanh", style="Dark.TLabelframe")
        copybar.pack(fill="x", pady=(0, 4))
        self.copybar_frame = copybar

        copy_inner = ttk.Frame(copybar, style="Panel.TFrame", padding=6)
        copy_inner.pack(fill="x", padx=4, pady=4)

        copy_row1 = ttk.Frame(copy_inner, style="Panel.TFrame")
        copy_row1.pack(fill="x")

        ttk.Label(
            copy_row1,
            text="Theo trạng thái:",
            background=PANEL,
            foreground=BLUE,
            font=("Segoe UI", 8, "bold")
        ).pack(side="left", padx=(0, 6))
        ttk.Button(copy_row1, text="STATUS", command=self.copy_status_only, style="Purple.TButton", width=10).pack(side="left", padx=2)
        ttk.Button(copy_row1, text="Status chọn", command=self.copy_selected_status, style="Purple.TButton", width=12).pack(side="left", padx=2)
        ttk.Button(copy_row1, text="LIVE", command=lambda: self.copy_by_status({"LIVE"}), style="Green.TButton", width=8).pack(side="left", padx=2)
        ttk.Button(copy_row1, text="LIVE + VERIFY", command=lambda: self.copy_by_status({"LIVE", "VERIFYED", "VERIFY_PHONE"}), style="Accent.TButton", width=13).pack(side="left", padx=2)
        ttk.Button(copy_row1, text="DIE / NOT", command=lambda: self.copy_by_status({"DIE", "NOTEXISTS", "WRONG"}), style="Danger.TButton", width=10).pack(side="left", padx=2)

        copy_row2 = ttk.Frame(copy_inner, style="Panel.TFrame")
        copy_row2.pack(fill="x", pady=(4, 0))

        ttk.Label(
            copy_row2,
            text="Khác:",
            background=PANEL,
            foreground=BLUE,
            font=("Segoe UI", 8, "bold")
        ).pack(side="left", padx=(0, 47))
        ttk.Button(copy_row2, text="Copy ALL", command=self.copy_all_results, style="Dark.TButton", width=10).pack(side="left", padx=2)
        ttk.Button(copy_row2, text="Email chọn", command=self.copy_selected_emails, style="Dark.TButton", width=12).pack(side="left", padx=2)
        ttk.Button(copy_row2, text="Xuất TXT", command=self.export_txt, style="Dark.TButton", width=10).pack(side="left", padx=2)

        stats_wrap = ttk.LabelFrame(quick_area, text="Thống kê trạng thái", style="Dark.TLabelframe")
        stats_wrap.pack(fill="x")
        self.status_dashboard_frame = stats_wrap

        stats_inner = ttk.Frame(stats_wrap, style="Panel.TFrame", padding=6)
        stats_inner.pack(fill="x", padx=4, pady=4)

        ttk.Label(
            stats_inner,
            text="Bấm vào ô để xem/copy mail theo trạng thái",
            background=PANEL,
            foreground=MUTED,
            font=("Segoe UI", 8)
        ).pack(anchor="w", pady=(0, 4))

        self.status_count_vars = {}
        dash = tk.Frame(stats_inner, bg=PANEL)
        dash.pack(fill="x")

        self.status_cards = [
            ("LIVE", "LIVE", GREEN),
            ("VERIFYED", "VERIFY", BLUE),
            ("DISABLED", "DISABLED", YELLOW),
            ("NOTEXISTS", "NOT EXIST", ORANGE),
            ("WRONG", "WRONG/DIE", RED),
            ("UNKNOW", "UNKNOWN", GRAY),
            ("ALL", "ALL", PURPLE),
        ]

        for status_key, label, color in self.status_cards:
            var = tk.StringVar(value=f"{label}\n0")
            self.status_count_vars[status_key] = var

            btn = tk.Button(
                dash,
                textvariable=var,
                command=lambda s=status_key: self.show_status_emails(s),
                bg="#0b1220",
                fg=color,
                activebackground="#1e293b",
                activeforeground="#ffffff",
                relief="flat",
                bd=1,
                highlightthickness=1,
                highlightbackground="#172036",
                highlightcolor="#172036",
                padx=5,
                pady=5,
                font=("Segoe UI", 8, "bold"),
                cursor="hand2"
            )
            btn.pack(side="left", fill="x", expand=True, padx=2)

        mid = ttk.Frame(root, style="Root.TFrame")
        mid.pack(fill="both", expand=True, pady=(0, 6))

        input_frame = ttk.LabelFrame(mid, text="Email input", style="Dark.TLabelframe")
        input_frame.pack(fill="x", pady=(0, 6))

        input_inner = tk.Frame(input_frame, bg=PANEL)
        input_inner.pack(fill="x", expand=False, padx=6, pady=6)

        self.input_text = tk.Text(
            input_inner,
            height=5,
            wrap="none",
            undo=True,
            bg=CARD,
            fg=TEXT,
            insertbackground=BLUE,
            selectbackground="#075985",
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Consolas", 10),
            padx=8,
            pady=8
        )
        self.input_text.pack(side="left", fill="both", expand=True)

        s1 = ttk.Scrollbar(input_inner, command=self.input_text.yview)
        s1.pack(side="right", fill="y")
        self.input_text.configure(yscrollcommand=s1.set)
        self.input_compact = False

        result_frame = ttk.LabelFrame(mid, text="Kết quả", style="Dark.TLabelframe")
        result_frame.pack(fill="both", expand=True)

        result_inner = tk.Frame(result_frame, bg=PANEL)
        result_inner.pack(fill="both", expand=True, padx=6, pady=6)

        cols = ("stt", "email", "status", "source")
        self.tree = ttk.Treeview(result_inner, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("stt", text="#")
        self.tree.heading("email", text="Email")
        self.tree.heading("status", text="Status")
        self.tree.heading("source", text="Nguồn")
        self.tree.column("stt", width=42, anchor="center", stretch=False)
        self.tree.column("email", width=430, anchor="w")
        self.tree.column("status", width=125, anchor="center", stretch=False)
        self.tree.column("source", width=130, anchor="center", stretch=False)
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.tag_configure("LIVE", foreground=GREEN)
        self.tree.tag_configure("VERIFYED", foreground=BLUE)
        self.tree.tag_configure("VERIFY_PHONE", foreground=PURPLE)
        self.tree.tag_configure("DISABLED", foreground=YELLOW)
        self.tree.tag_configure("NOTEXISTS", foreground=ORANGE)
        self.tree.tag_configure("DIE", foreground=RED)
        self.tree.tag_configure("WRONG", foreground=RED)
        self.tree.tag_configure("UNKNOW", foreground=GRAY)
        self.tree.tag_configure("BLANK", background="#0b1220")

        s2 = ttk.Scrollbar(result_inner, command=self.tree.yview)
        s2.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=s2.set)
        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)

        bottom = ttk.Frame(root, style="Root.TFrame")
        bottom.pack(fill="x", pady=(8, 0))

        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True)

        self.percent_var = tk.StringVar(value="0%")
        self.percent_label = ttk.Label(
            bottom,
            textvariable=self.percent_var,
            style="Muted.TLabel",
            width=4,
            anchor="center"
        )
        self.percent_label.pack(side="left", padx=(6, 0))

        self.status_var = tk.StringVar(value="Sẵn sàng. V44 SMS Pop có Lấy Date và click dòng để copy.")
        self.status_label = ttk.Label(bottom, textvariable=self.status_var, style="Muted.TLabel", anchor="e")
        self.status_label.pack(side="right", padx=(8, 0))






    def apply_saved_ui(self):
        ui = self.cfg.get("ui", {})
        try:
            self.mode_var.set(ui.get("mode", self.mode_var.get()))
            self.speed_var.set(ui.get("speed", self.speed_var.get()))
            self.keep_blank_var.set(bool(ui.get("keep_blank", self.keep_blank_var.get())))

            if bool(ui.get("input_compact", False)):
                self.input_text.configure(height=3)
                self.input_compact = True

            # V30 bỏ Mini mode nên không tự bật mini nữa.
        except Exception:
            pass

    def save_ui_config(self):
        try:
            self.cfg = load_config()
            self.cfg.setdefault("ui", {})
            self.cfg["ui"].update({
                "geometry": self.geometry(),
                "mode": self.mode_var.get(),
                "speed": self.speed_var.get(),
                "keep_blank": bool(self.keep_blank_var.get()),
                "input_compact": bool(getattr(self, "input_compact", False))
            })
            save_config(self.cfg)
        except Exception:
            pass

    def on_close(self):
        self.save_ui_config()
        self.destroy()

    def open_history_folder(self):
        messagebox.showinfo("History", "V32 đã xóa phần History.")

    def save_history_text(self, kind, text):
        # V32: đã xóa phần History, không tự lưu file lịch sử nữa.
        return

    def mail_results_to_text(self, results):
        lines = []
        stt = 1
        for r in results:
            if r.get("kind") != "email":
                lines.append("")
                continue
            lines.append(f"{stt}\t{r.get('email','')}\t{display_status(r.get('status',''))}\t{r.get('source','')}")
            stt += 1
        return "\n".join(lines)

    def save_mail_history(self, results, kind="mail"):
        # V32: đã xóa phần History.
        return

    def auto_detect_input(self):
        text = self.input_text.get("1.0", "end").strip("\n")
        if not text.strip():
            messagebox.showwarning("Thiếu dữ liệu", "Bạn chưa paste dữ liệu.")
            return

        sms_rows = extract_sms_links(text)
        sms_count = sum(1 for r in sms_rows if r.get("kind") == "sms")

        email_rows = parse_input_rows(text)
        email_count = len(rows_to_email_list(email_rows))

        twofa_rows = extract_2fa_rows(text)
        twofa_count = sum(1 for r in twofa_rows if r.get("kind") == "2fa")

        # Ưu tiên SMS nếu có link SMS222, rồi email, rồi 2FA.
        if sms_count:
            self.status_var.set(f"AUTO nhận dạng: SMS222 ({sms_count:,} link).")
            self.open_sms_tool(initial_text=text, auto_action="code")
            return

        if email_count:
            self.status_var.set(f"AUTO nhận dạng: Email ({email_count:,} mail).")
            self.start_check()
            return

        if twofa_count:
            self.status_var.set(f"AUTO nhận dạng: 2FA ({twofa_count:,} secret).")
            self.open_2fa_tool(initial_text=text, auto_run=True)
            return

        card_res = card_filter_lines(text)
        if card_res.get("total", 0) and (card_res.get("valid") or card_res.get("expired") or card_res.get("invalid")):
            self.status_var.set(f"AUTO nhận dạng: Dữ liệu thẻ ({card_res.get('total',0):,} dòng).")
            self.open_card_tool(initial_text=text)
            return

        messagebox.showwarning("Không nhận dạng được", "Dữ liệu không giống email, link SMS222, secret 2FA hoặc dòng thẻ.")



    def toggle_more_tools(self):
        try:
            if getattr(self, "more_tools_visible", False):
                self.more_tools_frame.pack_forget()
                self.more_tools_visible = False
                self.more_tools_btn.configure(text="Tiện ích ▼")
                self.status_var.set("Đã thu gọn phần tiện ích.")
            else:
                self.more_tools_frame.pack(fill="x", pady=(8, 0))
                self.more_tools_visible = True
                self.more_tools_btn.configure(text="Tiện ích ▲")
                self.status_var.set("Đã mở phần tiện ích.")
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    def toggle_mini_mode(self):
        try:
            if not getattr(self, "mini_mode", False):
                self.mini_hidden_widgets = []
                for w in [getattr(self, "status_dashboard_frame", None), getattr(self, "copybar_frame", None)]:
                    if w is not None:
                        try:
                            info = w.pack_info()
                            self.mini_hidden_widgets.append((w, info))
                            w.pack_forget()
                        except Exception:
                            pass

                try:
                    self.input_text.configure(height=3)
                except Exception:
                    pass

                self.mini_mode = True
                if hasattr(self, "mini_btn"):
                    self.mini_btn.configure(text="Full mode")
                self.status_var.set("Đã bật Mini mode: ẩn dashboard/copybar, ô nhập gọn hơn.")
            else:
                for w, info in reversed(getattr(self, "mini_hidden_widgets", [])):
                    try:
                        w.pack(**info)
                    except Exception:
                        pass
                self.mini_hidden_widgets = []

                try:
                    self.input_text.configure(height=6 if not getattr(self, "input_compact", False) else 3)
                except Exception:
                    pass

                self.mini_mode = False
                if hasattr(self, "mini_btn"):
                    self.mini_btn.configure(text="Mini mode")
                self.status_var.set("Đã quay lại Full mode.")

            self.save_ui_config()
        except Exception as e:
            messagebox.showerror("Lỗi Mini mode", str(e))





    def _make_popup_window(self, title, size="760x560"):
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry(size)
        win.minsize(620, 420)
        win.configure(bg=BG)
        try:
            win.transient(self)
        except Exception:
            pass
        return win

    def open_sms_popup(self):
        win = self._make_popup_window("SMS Popup", "820x580")

        root = ttk.Frame(win, style="Root.TFrame", padding=10)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root, style="Root.TFrame")
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="SMS Popup", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="Đóng", command=win.destroy, style="Dark.TButton").pack(side="right")

        body = ttk.Frame(root, style="Root.TFrame")
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="Link SMS222", style="Dark.TLabelframe")
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))

        right = ttk.LabelFrame(body, text="Kết quả", style="Dark.TLabelframe")
        right.pack(side="left", fill="both", expand=True, padx=(5, 0))

        inp = tk.Text(left, wrap="none", bg=CARD, fg=TEXT, insertbackground=BLUE, selectbackground="#075985",
                      selectforeground="#ffffff", relief="flat", bd=0, font=("Consolas", 10), padx=8, pady=8)
        inp.pack(fill="both", expand=True, padx=6, pady=6)

        out = tk.Text(right, wrap="none", bg=CARD, fg=TEXT, insertbackground=BLUE, selectbackground="#075985",
                      selectforeground="#ffffff", relief="flat", bd=0, font=("Consolas", 10), padx=8, pady=8)
        out.pack(fill="both", expand=True, padx=6, pady=6)

        status = tk.StringVar(value="Sẵn sàng.")
        bar = ttk.Frame(root, style="Panel.TFrame", padding=6)
        bar.pack(fill="x", pady=(8, 0))
        pct_var = tk.StringVar(value="0%")
        tk.Label(bar, textvariable=pct_var, bg="#0b1220", fg=BLUE, padx=10, pady=4, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))

        def set_out(text):
            out.delete("1.0", "end")
            out.insert("1.0", text or "")

        def copy_current_line(event=None):
            try:
                idx = out.index("@%s,%s linestart" % (event.x, event.y)) if event else out.index("insert linestart")
                line = out.get(idx, idx + " lineend")
                win.clipboard_clear()
                win.clipboard_append(line)
                status.set("Đã copy dòng: " + line[:80] if line.strip() else "Đã copy dòng trống.")
            except Exception as e:
                status.set("Lỗi copy dòng: " + str(e)[:80])

        out.bind("<ButtonRelease-1>", copy_current_line)

        def run_sms_action(action_name, fetch_func):
            raw = inp.get("1.0", "end")
            rows = extract_sms_links(raw)
            sms_rows = [r for r in rows if r.get("kind") == "sms"]
            total = len(sms_rows)

            if not sms_rows:
                status.set("Không có link SMS.")
                pct_var.set("0%")
                return

            status.set(f"0% | Đang {action_name} {total:,} link...")
            pct_var.set("0%")

            def worker():
                result_by_index = {}
                done = 0
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                        future_map = {
                            ex.submit(fetch_func, row.get("link", "")): idx
                            for idx, row in enumerate(rows) if row.get("kind") == "sms"
                        }

                        for fut in concurrent.futures.as_completed(future_map):
                            idx = future_map[fut]
                            try:
                                result_by_index[idx] = fut.result()
                            except Exception as e:
                                result_by_index[idx] = "lỗi: " + str(e)[:80]

                            done += 1
                            pct = int(done * 100 / max(total, 1))
                            self.after(0, lambda d=done, p=pct: (
                                pct_var.set(f"{p}%"),
                                status.set(f"{p}% | {action_name} {d:,}/{total:,}")
                            ))

                    result = []
                    for idx, row in enumerate(rows):
                        if row.get("kind") == "blank":
                            result.append("")
                        else:
                            result.append(result_by_index.get(idx, "không có dữ liệu"))

                    self.after(0, lambda: set_out("\n".join(result)))
                    self.after(0, lambda: (
                        pct_var.set("100%"),
                        status.set(f"100% | Xong {action_name} {total:,} link. Bấm dòng để copy.")
                    ))
                except Exception as e:
                    self.after(0, lambda: status.set("Lỗi: " + str(e)[:100]))

            threading.Thread(target=worker, daemon=True).start()

        def run_sms():
            run_sms_action("lấy SMS", fetch_sms_code)

        def run_date():
            run_sms_action("lấy Date", fetch_sms_date)

        def copy_result():
            data = out.get("1.0", "end").strip("\n")
            win.clipboard_clear()
            win.clipboard_append(data)
            status.set("Đã copy toàn bộ kết quả.")

        def clear_all():
            inp.delete("1.0", "end")
            out.delete("1.0", "end")
            pct_var.set("0%")
            status.set("Đã xóa.")

        ttk.Button(bar, text="Lấy SMS", command=run_sms, style="Green.TButton", width=12).pack(side="left", padx=3)
        ttk.Button(bar, text="Lấy Date", command=run_date, style="Accent.TButton", width=12).pack(side="left", padx=3)
        ttk.Button(bar, text="Copy", command=copy_result, style="Dark.TButton", width=10).pack(side="left", padx=3)
        ttk.Button(bar, text="Xóa", command=clear_all, style="Danger.TButton", width=10).pack(side="left", padx=3)
        ttk.Label(bar, textvariable=status, style="Muted.TLabel").pack(side="right")

    def open_2fa_popup(self):
        win = self._make_popup_window("2FA Popup", "780x560")

        root = ttk.Frame(win, style="Root.TFrame", padding=10)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root, style="Root.TFrame")
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="2FA Popup", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="Đóng", command=win.destroy, style="Dark.TButton").pack(side="right")

        body = ttk.Frame(root, style="Root.TFrame")
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="Secret / otpauth / 2fa.live", style="Dark.TLabelframe")
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))

        right = ttk.LabelFrame(body, text="Code", style="Dark.TLabelframe")
        right.pack(side="left", fill="both", expand=True, padx=(5, 0))

        inp = tk.Text(left, wrap="none", bg=CARD, fg=TEXT, insertbackground=BLUE, selectbackground="#075985",
                      selectforeground="#ffffff", relief="flat", bd=0, font=("Consolas", 10), padx=8, pady=8)
        inp.pack(fill="both", expand=True, padx=6, pady=6)

        out = tk.Text(right, wrap="none", bg=CARD, fg=TEXT, insertbackground=BLUE, selectbackground="#075985",
                      selectforeground="#ffffff", relief="flat", bd=0, font=("Consolas", 10), padx=8, pady=8)
        out.pack(fill="both", expand=True, padx=6, pady=6)

        status = tk.StringVar(value="Sẵn sàng.")
        bar = ttk.Frame(root, style="Panel.TFrame", padding=6)
        bar.pack(fill="x", pady=(8, 0))
        pct_var = tk.StringVar(value="0%")
        tk.Label(bar, textvariable=pct_var, bg="#0b1220", fg=BLUE, padx=10, pady=4, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))

        def set_out(text):
            out.delete("1.0", "end")
            out.insert("1.0", text or "")

        def run_2fa():
            raw = inp.get("1.0", "end")
            rows = extract_2fa_rows(raw)
            valid = [r for r in rows if r.get("kind") == "2fa"]
            total = len(valid)
            if not valid:
                status.set("Không có secret 2FA.")
                pct_var.set("0%")
                return

            result = []
            done = 0
            for row in rows:
                if row.get("kind") == "blank":
                    result.append("")
                    continue
                result.append(calc_totp(row.get("secret", "")))
                done += 1
                pct = int(done * 100 / max(total, 1))
                pct_var.set(f"{pct}%")
                status.set(f"{pct}% | 2FA {done:,}/{total:,}")

            set_out("\n".join(result))
            pct_var.set("100%")
            status.set(f"100% | Xong {total:,} 2FA.")

        def copy_result():
            data = out.get("1.0", "end").strip("\n")
            win.clipboard_clear()
            win.clipboard_append(data)
            status.set("Đã copy kết quả.")

        def clear_all():
            inp.delete("1.0", "end")
            out.delete("1.0", "end")
            pct_var.set("0%")
            status.set("Đã xóa.")

        ttk.Button(bar, text="Lấy 2FA", command=run_2fa, style="Green.TButton", width=12).pack(side="left", padx=3)
        ttk.Button(bar, text="Copy", command=copy_result, style="Dark.TButton", width=10).pack(side="left", padx=3)
        ttk.Button(bar, text="Xóa", command=clear_all, style="Danger.TButton", width=10).pack(side="left", padx=3)
        ttk.Label(bar, textvariable=status, style="Muted.TLabel").pack(side="right")

    def open_card_popup(self):
        win = self._make_popup_window("Thẻ Popup", "880x600")

        root = ttk.Frame(win, style="Root.TFrame", padding=10)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root, style="Root.TFrame")
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Thẻ Popup", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="Đóng", command=win.destroy, style="Dark.TButton").pack(side="right")

        body = ttk.Frame(root, style="Root.TFrame")
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="Input thẻ", style="Dark.TLabelframe")
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))

        right = ttk.LabelFrame(body, text="Kết quả", style="Dark.TLabelframe")
        right.pack(side="left", fill="both", expand=True, padx=(5, 0))

        inp = tk.Text(left, wrap="none", bg=CARD, fg=TEXT, insertbackground=BLUE, selectbackground="#075985",
                      selectforeground="#ffffff", relief="flat", bd=0, font=("Consolas", 10), padx=8, pady=8)
        inp.pack(fill="both", expand=True, padx=6, pady=6)

        out = tk.Text(right, wrap="none", bg=CARD, fg=TEXT, insertbackground=BLUE, selectbackground="#075985",
                      selectforeground="#ffffff", relief="flat", bd=0, font=("Consolas", 10), padx=8, pady=8)
        out.pack(fill="both", expand=True, padx=6, pady=6)

        status = tk.StringVar(value="Sẵn sàng.")
        mode_var = tk.StringVar(value="valid")
        bar = ttk.Frame(root, style="Panel.TFrame", padding=6)
        bar.pack(fill="x", pady=(8, 0))
        pct_var = tk.StringVar(value="0%")
        tk.Label(bar, textvariable=pct_var, bg="#0b1220", fg=BLUE, padx=10, pady=4, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))

        state = {"res": None}

        def render():
            res = state.get("res")
            if not res:
                return
            mode = mode_var.get()
            if mode == "valid":
                items = res.get("valid", [])
            elif mode == "expired":
                items = res.get("expired", [])
            elif mode == "duplicate":
                items = res.get("duplicate", [])
            elif mode == "invalid":
                items = res.get("invalid", [])
            else:
                items = res.get("valid", [])

            text = "\n".join([card_format_item(x, "original") for x in items])
            out.delete("1.0", "end")
            out.insert("1.0", text)

        def run_card():
            raw = inp.get("1.0", "end")
            if not raw.strip():
                status.set("Không có dữ liệu thẻ.")
                pct_var.set("0%")
                return
            res = card_filter_lines(raw)
            state["res"] = res
            pct_var.set("100%")
            status.set(
                f"100% | Còn hạn {len(res.get('valid', [])):,} | Hết hạn {len(res.get('expired', [])):,} | Trùng {len(res.get('duplicate', [])):,}"
            )
            render()

        def copy_result():
            data = out.get("1.0", "end").strip("\n")
            win.clipboard_clear()
            win.clipboard_append(data)
            status.set("Đã copy kết quả.")

        def clear_all():
            inp.delete("1.0", "end")
            out.delete("1.0", "end")
            state["res"] = None
            pct_var.set("0%")
            status.set("Đã xóa.")

        ttk.Combobox(bar, textvariable=mode_var, state="readonly", width=12, values=["valid", "expired", "duplicate", "invalid"]).pack(side="left", padx=3)
        ttk.Button(bar, text="Lọc thẻ", command=run_card, style="Green.TButton", width=12).pack(side="left", padx=3)
        ttk.Button(bar, text="Xem", command=render, style="Accent.TButton", width=8).pack(side="left", padx=3)
        ttk.Button(bar, text="Copy", command=copy_result, style="Dark.TButton", width=10).pack(side="left", padx=3)
        ttk.Button(bar, text="Xóa", command=clear_all, style="Danger.TButton", width=10).pack(side="left", padx=3)
        ttk.Label(bar, textvariable=status, style="Muted.TLabel").pack(side="right")

    def close_multirun_view(self):
        if hasattr(self, "multirun_overlay") and self.multirun_overlay is not None:
            try:
                self.multirun_overlay.destroy()
            except Exception:
                pass
            self.multirun_overlay = None
            self.status_var.set("Đã quay lại màn hình Mail.")

    def open_multirun_tool(self):
        if hasattr(self, "multirun_overlay") and self.multirun_overlay is not None:
            try:
                self.multirun_overlay.lift()
                return
            except Exception:
                self.multirun_overlay = None

        self.multirun_overlay = tk.Frame(self, bg=BG)
        self.multirun_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.multirun_overlay.lift()

        frame = ttk.Frame(self.multirun_overlay, style="Root.TFrame", padding=8)
        frame.pack(fill="both", expand=True)

        header = ttk.Frame(frame, style="Root.TFrame")
        header.pack(fill="x", pady=(0, 6))
        title_box = ttk.Frame(header, style="Root.TFrame")
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text="⚡ Multi Run", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="Chạy Mail + SMS + 2FA + Thẻ cùng lúc", style="Sub.TLabel").pack(anchor="w")
        ttk.Button(header, text="Quay lại Mail", command=self.close_multirun_view, style="Dark.TButton").pack(side="right", padx=3)

        controls = ttk.Frame(frame, style="Panel.TFrame", padding=6)
        controls.pack(fill="x", pady=(0, 6))
        run_mail_var = tk.BooleanVar(value=True)
        run_sms_var = tk.BooleanVar(value=True)
        run_2fa_var = tk.BooleanVar(value=True)
        run_card_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Mail", variable=run_mail_var).pack(side="left", padx=4)
        ttk.Checkbutton(controls, text="SMS", variable=run_sms_var).pack(side="left", padx=4)
        ttk.Checkbutton(controls, text="2FA", variable=run_2fa_var).pack(side="left", padx=4)
        ttk.Checkbutton(controls, text="Thẻ", variable=run_card_var).pack(side="left", padx=4)
        overall_var = tk.StringVar(value="0%")
        ttk.Label(controls, text="Tổng:", background=PANEL, foreground=MUTED).pack(side="left", padx=(20, 4))
        tk.Label(controls, textvariable=overall_var, bg="#0b1220", fg=BLUE, padx=10, pady=4, font=("Segoe UI", 9, "bold")).pack(side="left")

        body = ttk.Frame(frame, style="Root.TFrame")
        body.pack(fill="both", expand=True)
        cols = {}
        for key, title, color in [("mail", "Mail", GREEN), ("sms", "SMS", BLUE), ("twofa", "2FA", PURPLE), ("card", "Thẻ", YELLOW)]:
            box = ttk.LabelFrame(body, text=title, style="Dark.TLabelframe")
            box.pack(side="left", fill="both", expand=True, padx=3)
            ttk.Label(box, text="Input", background=PANEL, foreground=color, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=5)
            inp = tk.Text(box, height=8, wrap="none", bg=CARD, fg=TEXT, insertbackground=BLUE, selectbackground="#075985", selectforeground="#ffffff", relief="flat", bd=0, font=("Consolas", 9), padx=6, pady=6)
            inp.pack(fill="both", expand=True, padx=5, pady=(2, 5))
            ttk.Label(box, text="Kết quả", background=PANEL, foreground=color, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=5)
            out = tk.Text(box, height=8, wrap="none", bg=CARD, fg=TEXT, insertbackground=BLUE, selectbackground="#075985", selectforeground="#ffffff", relief="flat", bd=0, font=("Consolas", 9), padx=6, pady=6)
            out.pack(fill="both", expand=True, padx=5, pady=(2, 5))
            stat = tk.StringVar(value="Sẵn sàng.")
            ttk.Label(box, textvariable=stat, style="Muted.TLabel").pack(anchor="e", padx=5, pady=(0, 4))
            cols[key] = {"input": inp, "output": out, "status": stat, "done": 0, "total": 0}

        def update_overall():
            total = sum(max(int(c.get("total", 0) or 0), 0) for c in cols.values())
            done = sum(max(int(c.get("done", 0) or 0), 0) for c in cols.values())
            pct = 0 if total <= 0 else int(done * 100 / total)
            overall_var.set(f"{max(0, min(100, pct))}%")

        def set_status(key, text, done=None, total=None):
            if done is not None:
                cols[key]["done"] = done
            if total is not None:
                cols[key]["total"] = total
            cols[key]["status"].set(text)
            update_overall()

        def set_output(key, text):
            cols[key]["output"].delete("1.0", "end")
            cols[key]["output"].insert("1.0", text or "")

        def run_mail_task():
            key = "mail"
            try:
                raw = cols[key]["input"].get("1.0", "end")
                rows = parse_input_rows(raw)
                emails = rows_to_email_list(rows)
                total = len(emails)
                self.after(0, lambda: set_status(key, "0% | Đang check mail...", 0, max(total, 1)))
                if not emails:
                    self.after(0, lambda: set_status(key, "Không có email.", 1, 1))
                    return
                cfg = load_config()
                providers = cfg.get("providers", {})
                provider_keys = self.selected_provider_keys()
                if not provider_keys:
                    self.after(0, lambda: set_status(key, "Thiếu API/provider.", 1, 1))
                    return
                combined, sources = {}, {}
                run_all = self.mode_var.get() == "Chạy tất cả"
                workers = self.get_turbo_workers()
                def progress(done, total2, msg):
                    pct = int(done * 100 / max(total2, 1))
                    self.after(0, lambda d=done, t=total2, p=pct: set_status(key, f"{p}% | {d:,}/{t:,} mail", d, max(t, 1)))
                for pkey in provider_keys:
                    p = dict(providers.get(pkey, PROVIDERS[pkey]))
                    if pkey == "gonvl":
                        p["workers"] = workers
                        p["limit"] = 10
                    result_map = check_provider(p, emails, progress)
                    for email_key, status in result_map.items():
                        status = normalize_status(status)
                        if run_all:
                            best = choose_best_status(combined.get(email_key, "UNKNOW"), status)
                            combined[email_key] = best
                            if best == status:
                                sources[email_key] = p["name"]
                        else:
                            combined[email_key] = status
                            sources[email_key] = p["name"]
                    if not run_all:
                        break
                out_lines = []
                for row in rows:
                    if row.get("kind") == "blank":
                        out_lines.append("")
                    else:
                        email = row["email"]
                        k = email.lower()
                        out_lines.append(f"{email}\t{display_status(combined.get(k, 'UNKNOW'))}\t{sources.get(k, '')}")
                self.after(0, lambda: set_output(key, "\n".join(out_lines)))
                self.after(0, lambda: set_status(key, f"100% | Xong {total:,} mail.", max(total, 1), max(total, 1)))
            except Exception as e:
                self.after(0, lambda: set_status(key, "Lỗi: " + str(e)[:80], 1, 1))

        def run_sms_task():
            key = "sms"
            try:
                raw = cols[key]["input"].get("1.0", "end")
                rows = extract_sms_links(raw)
                sms_rows = [r for r in rows if r.get("kind") == "sms"]
                total = len(sms_rows)
                self.after(0, lambda: set_status(key, "0% | Đang lấy SMS...", 0, max(total, 1)))
                if not sms_rows:
                    self.after(0, lambda: set_status(key, "Không có link SMS.", 1, 1))
                    return
                result_by_index, done = {}, 0
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                    future_map = {ex.submit(fetch_sms_code, row.get("link", "")): idx for idx, row in enumerate(rows) if row.get("kind") == "sms"}
                    for fut in concurrent.futures.as_completed(future_map):
                        idx = future_map[fut]
                        try:
                            result_by_index[idx] = fut.result()
                        except Exception as e:
                            result_by_index[idx] = "lỗi: " + str(e)[:80]
                        done += 1
                        pct = int(done * 100 / max(total, 1))
                        self.after(0, lambda d=done, p=pct: set_status(key, f"{p}% | SMS {d:,}/{total:,}", d, max(total, 1)))
                out = []
                for idx, row in enumerate(rows):
                    out.append("" if row.get("kind") == "blank" else result_by_index.get(idx, "không có mã"))
                self.after(0, lambda: set_output(key, "\n".join(out)))
                self.after(0, lambda: set_status(key, f"100% | Xong {total:,} SMS.", max(total, 1), max(total, 1)))
            except Exception as e:
                self.after(0, lambda: set_status(key, "Lỗi: " + str(e)[:80], 1, 1))

        def run_2fa_task():
            key = "twofa"
            try:
                raw = cols[key]["input"].get("1.0", "end")
                rows = extract_2fa_rows(raw)
                valid = [r for r in rows if r.get("kind") == "2fa"]
                total = len(valid)
                self.after(0, lambda: set_status(key, "0% | Đang lấy 2FA...", 0, max(total, 1)))
                if not valid:
                    self.after(0, lambda: set_status(key, "Không có secret 2FA.", 1, 1))
                    return
                out, done = [], 0
                for row in rows:
                    if row.get("kind") == "blank":
                        out.append("")
                    else:
                        out.append(calc_totp(row.get("secret", "")))
                        done += 1
                        pct = int(done * 100 / max(total, 1))
                        self.after(0, lambda d=done, p=pct: set_status(key, f"{p}% | 2FA {d:,}/{total:,}", d, max(total, 1)))
                self.after(0, lambda: set_output(key, "\n".join(out)))
                self.after(0, lambda: set_status(key, f"100% | Xong {total:,} 2FA.", max(total, 1), max(total, 1)))
            except Exception as e:
                self.after(0, lambda: set_status(key, "Lỗi: " + str(e)[:80], 1, 1))

        def run_card_task():
            key = "card"
            try:
                raw = cols[key]["input"].get("1.0", "end")
                if not raw.strip():
                    self.after(0, lambda: set_status(key, "Không có dữ liệu thẻ.", 1, 1))
                    return
                res = card_filter_lines(raw)
                lines = [card_format_item(x, "original") for x in res.get("valid", [])]
                total = max(res.get("total", 0), 1)
                self.after(0, lambda: set_output(key, "\n".join(lines)))
                self.after(0, lambda: set_status(key, f"100% | Còn hạn {len(res.get('valid', [])):,}/{res.get('total', 0):,}", total, total))
            except Exception as e:
                self.after(0, lambda: set_status(key, "Lỗi: " + str(e)[:80], 1, 1))

        def run_selected():
            tasks = []
            overall_var.set("0%")
            for c in cols.values():
                c["done"] = 0
                c["total"] = 0
                c["output"].delete("1.0", "end")
                c["status"].set("Sẵn sàng.")
            if run_mail_var.get():
                tasks.append(run_mail_task)
            if run_sms_var.get():
                tasks.append(run_sms_task)
            if run_2fa_var.get():
                tasks.append(run_2fa_task)
            if run_card_var.get():
                tasks.append(run_card_task)
            if not tasks:
                messagebox.showwarning("Chưa chọn", "Bạn chưa chọn chức năng nào.")
                return
            for task in tasks:
                threading.Thread(target=task, daemon=True).start()
            self.status_var.set(f"Đang chạy song song {len(tasks)} chức năng.")

        def copy_result(key):
            data = cols[key]["output"].get("1.0", "end").strip("\n")
            self.clipboard_clear()
            self.clipboard_append(data)
            cols[key]["status"].set("Đã copy kết quả.")

        def clear_all():
            for c in cols.values():
                c["input"].delete("1.0", "end")
                c["output"].delete("1.0", "end")
                c["status"].set("Đã xóa.")
                c["done"] = 0
                c["total"] = 0
            overall_var.set("0%")

        bottom = ttk.Frame(frame, style="Panel.TFrame", padding=8)
        bottom.pack(fill="x", pady=(6, 0))
        ttk.Button(bottom, text="Chạy tất cả đã chọn", command=run_selected, style="Green.TButton", width=18).pack(side="left", padx=3)
        ttk.Button(bottom, text="Copy Mail", command=lambda: copy_result("mail"), style="Dark.TButton", width=10).pack(side="left", padx=3)
        ttk.Button(bottom, text="Copy SMS", command=lambda: copy_result("sms"), style="Dark.TButton", width=10).pack(side="left", padx=3)
        ttk.Button(bottom, text="Copy 2FA", command=lambda: copy_result("twofa"), style="Dark.TButton", width=10).pack(side="left", padx=3)
        ttk.Button(bottom, text="Copy Thẻ", command=lambda: copy_result("card"), style="Dark.TButton", width=10).pack(side="left", padx=3)
        ttk.Button(bottom, text="Xóa tất cả", command=clear_all, style="Danger.TButton", width=10).pack(side="left", padx=3)
        ttk.Button(bottom, text="Quay lại Mail", command=self.close_multirun_view, style="Dark.TButton", width=14).pack(side="right", padx=3)

    def close_update_view(self):
        if hasattr(self, "update_overlay") and self.update_overlay is not None:
            try:
                self.update_overlay.destroy()
            except Exception:
                pass
            self.update_overlay = None
            self.status_var.set("Đã quay lại màn hình Mail.")


    def _apply_update_zip_simple(self, zip_path, silent=False):
        target = app_dir()
        temp_dir = target / "_quick_update_extract"
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            temp_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(temp_dir)

            copied = 0
            found_app = False
            allowed_exact = {"run_app.bat", "build_exe.bat", "readme.txt"}

            for p in temp_dir.rglob("*"):
                if not p.is_file():
                    continue

                name_l = p.name.lower()
                suffix = p.suffix.lower()

                if "__pycache__" in [x.lower() for x in p.parts]:
                    continue

                should_copy = False
                if name_l in allowed_exact:
                    should_copy = True
                elif suffix in {".pyw", ".py"} and ("mail_checker" in name_l or "khanh" in name_l):
                    should_copy = True
                    found_app = True
                elif name_l in {"providers.json", "update_config.json"}:
                    should_copy = True

                if not should_copy:
                    continue

                dst = target / p.name
                shutil.copy2(p, dst)
                copied += 1

            shutil.rmtree(temp_dir, ignore_errors=True)

            if not found_app:
                messagebox.showwarning("Không thấy file app", "File zip này không có file app .pyw phù hợp.")
                return False

            if not silent:
                messagebox.showinfo(
                    "Update xong",
                    f"Đã cập nhật {copied} file.\nTắt tool rồi mở lại bằng run_app.bat."
                )
            self.status_var.set(f"Update xong {copied} file. Tắt mở lại app.")
            return True
        except Exception as e:
            messagebox.showerror("Lỗi update", str(e))
            self.status_var.set("Lỗi update.")
            return False

    def find_latest_update_zip(self):
        candidates = []

        search_dirs = []
        try:
            search_dirs.append(app_dir())
        except Exception:
            pass

        home = Path.home()
        for name in ["Downloads", "Desktop", "Tải xuống"]:
            p = home / name
            if p.exists():
                search_dirs.append(p)

        patterns = [
            "Khanh_Mail_Checker*.zip",
            "Khanh*Mail*Checker*.zip",
            "Khanh_*.zip",
            "*Mail_Checker*.zip",
        ]

        for folder in search_dirs:
            try:
                for pat in patterns:
                    candidates.extend(folder.glob(pat))
            except Exception:
                pass

        # bỏ qua gói online update pack, tránh chọn nhầm
        clean = []
        for p in candidates:
            name = p.name.lower()
            if "online_update_pack" in name:
                continue
            if "update_pack" in name and "mail_checker" not in name:
                continue
            if p.is_file():
                clean.append(p)

        if not clean:
            return None

        clean = sorted(set(clean), key=lambda x: x.stat().st_mtime, reverse=True)
        return clean[0]

    def quick_update_latest_zip(self):
        z = self.find_latest_update_zip()
        if not z:
            messagebox.showwarning(
                "Không tìm thấy file update",
                "Không thấy file Khanh_Mail_Checker*.zip trong Downloads / Desktop / thư mục app.\n\n"
                "Bạn chỉ cần tải file zip bản mới tôi gửi về rồi bấm Update nhanh lại."
            )
            return

        ok = messagebox.askyesno(
            "Update nhanh",
            "Tool tìm thấy file update mới nhất:\n\n"
            f"{z}\n\n"
            "Bạn muốn update bằng file này không?"
        )
        if not ok:
            return

        self._apply_update_zip_simple(z)

    def open_update_tool(self):
        if hasattr(self, "update_overlay") and self.update_overlay is not None:
            try:
                self.update_overlay.lift()
                return
            except Exception:
                self.update_overlay = None

        self.update_overlay = tk.Frame(self, bg=BG)
        self.update_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.update_overlay.lift()

        update_cfg = load_update_config()

        frame = ttk.Frame(self.update_overlay, style="Root.TFrame", padding=10)
        frame.pack(fill="both", expand=True)

        header = ttk.Frame(frame, style="Root.TFrame")
        header.pack(fill="x", pady=(0, 8))

        title_box = ttk.Frame(header, style="Root.TFrame")
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text="⬆️ Cập nhật online", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_box,
            text=f"Version hiện tại: V{APP_VERSION} • Hỗ trợ link .zip hoặc manifest.json",
            style="Sub.TLabel"
        ).pack(anchor="w")

        ttk.Button(header, text="Quay lại Mail", command=self.close_update_view, style="Dark.TButton").pack(side="right", padx=3)

        cfg_box = ttk.Frame(frame, style="Panel.TFrame", padding=10)
        cfg_box.pack(fill="x", pady=(0, 8))

        ttk.Label(
            cfg_box,
            text="Link update:",
            background=PANEL,
            foreground=BLUE,
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(0, 5))

        url_var = tk.StringVar(value=update_cfg.get("update_url", ""))
        url_entry = tk.Entry(
            cfg_box,
            textvariable=url_var,
            bg=CARD,
            fg=TEXT,
            insertbackground=BLUE,
            relief="flat",
            font=("Consolas", 10)
        )
        url_entry.pack(fill="x", ipady=5)

        guide = (
            "Dùng 1 trong 2 dạng:\n"
            "• Link file .zip trực tiếp: https://domain.com/Khanh_Mail_Checker_Update.zip\n"
            "• Link manifest.json có dạng: {\"version\":\"38\", \"zip_url\":\"https://.../update.zip\", \"notes\":\"...\"}"
        )
        ttk.Label(cfg_box, text=guide, background=PANEL, foreground=MUTED, justify="left").pack(anchor="w", pady=(8, 0))

        info = ttk.Frame(frame, style="Panel.TFrame", padding=10)
        info.pack(fill="both", expand=True)

        log_box = tk.Text(
            info,
            height=14,
            wrap="word",
            bg=CARD,
            fg=TEXT,
            insertbackground=BLUE,
            selectbackground="#075985",
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Consolas", 10),
            padx=8,
            pady=8
        )
        log_box.pack(fill="both", expand=True)

        update_status = tk.StringVar(value="Sẵn sàng.")

        def log(msg):
            log_box.insert("end", str(msg) + "\n")
            log_box.see("end")
            update_status.set(str(msg))

        def save_url():
            u = url_var.get().strip()
            save_update_config({"update_url": u})
            log("Đã lưu link update.")

        def download_file(url, suffix=".zip"):
            tmp_dir = Path(tempfile.mkdtemp(prefix="khanh_update_"))
            out = tmp_dir / ("update" + suffix)

            log(f"Đang tải: {url}")
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Khanh-Mail-Checker-Updater/37.0",
                    "Accept": "*/*"
                }
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = resp.read()
            out.write_bytes(data)
            log(f"Đã tải xong: {len(data):,} bytes")
            return out

        def apply_update_zip(zip_path):
            target = app_dir()
            temp_dir = target / "_update_temp_extract"

            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                temp_dir.mkdir(parents=True, exist_ok=True)

                log(f"Đang giải nén: {zip_path}")
                with zipfile.ZipFile(zip_path, "r") as z:
                    z.extractall(temp_dir)

                copied = 0
                found_app = False
                allowed_exact = {"run_app.bat", "build_exe.bat", "readme.txt"}

                for p in temp_dir.rglob("*"):
                    if not p.is_file():
                        continue

                    name_l = p.name.lower()
                    suffix = p.suffix.lower()

                    if "__pycache__" in [x.lower() for x in p.parts]:
                        continue

                    should_copy = False
                    if name_l in allowed_exact:
                        should_copy = True
                    elif suffix in {".pyw", ".py"} and ("mail_checker" in name_l or "khanh" in name_l):
                        should_copy = True
                        found_app = True
                    elif name_l in {"providers.json", "update_config.json"}:
                        should_copy = True

                    if not should_copy:
                        continue

                    dst = target / p.name
                    try:
                        shutil.copy2(p, dst)
                        copied += 1
                        log(f"Đã cập nhật: {p.name}")
                    except Exception as e:
                        log(f"Lỗi copy {p.name}: {e}")

                if not found_app:
                    messagebox.showwarning("Không thấy file app", "File zip này không có file app .pyw phù hợp.")
                    log("Không thấy file app .pyw trong zip.")
                    return False

                shutil.rmtree(temp_dir, ignore_errors=True)
                messagebox.showinfo("Cập nhật xong", f"Đã cập nhật {copied} file.\nHãy tắt tool và mở lại bằng run_app.bat.")
                log(f"Xong. Đã cập nhật {copied} file. Hãy tắt mở lại app.")
                return True
            except Exception as e:
                messagebox.showerror("Lỗi update", str(e))
                log(f"Lỗi update: {e}")
                return False

        def parse_manifest_or_zip(url):
            # Nếu là link zip thì trả về trực tiếp.
            if url.lower().split("?")[0].endswith(".zip"):
                return {"version": "", "zip_url": url, "notes": "Direct zip"}

            manifest_file = download_file(url, suffix=".json")
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            except Exception:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8-sig"))

            if not isinstance(manifest, dict):
                raise RuntimeError("manifest.json không đúng dạng object.")

            zip_url = manifest.get("zip_url") or manifest.get("url") or manifest.get("download_url")
            if not zip_url:
                raise RuntimeError("manifest.json thiếu zip_url.")

            return {
                "version": str(manifest.get("version", "")),
                "zip_url": str(zip_url),
                "notes": str(manifest.get("notes", ""))
            }

        def check_online_update():
            url = url_var.get().strip()
            if not url:
                messagebox.showwarning("Thiếu link", "Bạn chưa nhập link update online.")
                return

            save_url()
            log_box.delete("1.0", "end")
            log("Đang kiểm tra update online...")

            def worker():
                try:
                    info = parse_manifest_or_zip(url)
                    version = info.get("version", "")
                    notes = info.get("notes", "")
                    zip_url = info.get("zip_url", "")

                    self.after(0, lambda: log(f"Version hiện tại: V{APP_VERSION}"))
                    if version:
                        self.after(0, lambda: log(f"Version online: V{version}"))
                    if notes:
                        self.after(0, lambda: log(f"Ghi chú: {notes}"))
                    self.after(0, lambda: log(f"Zip URL: {zip_url}"))

                    if version:
                        try:
                            if int(version) <= int(APP_VERSION):
                                self.after(0, lambda: log("Bạn đang dùng bản mới nhất hoặc bản online không mới hơn."))
                                return
                        except Exception:
                            pass

                    def ask_and_download():
                        ok = messagebox.askyesno(
                            "Có bản update",
                            f"Có bản update online{(' V' + version) if version else ''}.\nBạn muốn tải và cập nhật ngay không?"
                        )
                        if ok:
                            download_and_apply_zip(zip_url)

                    self.after(0, ask_and_download)
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Lỗi update online", str(e)))
                    self.after(0, lambda: log(f"Lỗi: {e}"))

            threading.Thread(target=worker, daemon=True).start()

        def download_and_apply_zip(zip_url):
            def worker():
                try:
                    zip_file = download_file(zip_url, suffix=".zip")
                    self.after(0, lambda: log("Đã tải file update, đang cài..."))
                    ok = apply_update_zip(zip_file)
                    if ok:
                        save_url()
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Lỗi tải update", str(e)))
                    self.after(0, lambda: log(f"Lỗi tải update: {e}"))

            threading.Thread(target=worker, daemon=True).start()

        def update_direct_zip():
            url = url_var.get().strip()
            if not url:
                messagebox.showwarning("Thiếu link", "Bạn chưa nhập link zip.")
                return
            save_url()
            ok = messagebox.askyesno("Xác nhận", "Tải và update trực tiếp từ link đang nhập?")
            if ok:
                download_and_apply_zip(url)

        def choose_update_zip():
            path = filedialog.askopenfilename(
                title="Chọn file update .zip",
                filetypes=[("Update ZIP", "*.zip"), ("All files", "*.*")]
            )
            if not path:
                return
            ok = messagebox.askyesno("Xác nhận update", f"Update bằng file này?\n\n{path}")
            if ok:
                apply_update_zip(path)

        btns = ttk.Frame(frame, style="Panel.TFrame", padding=10)
        btns.pack(fill="x", pady=(10, 0))

        ttk.Button(btns, text="Lưu link", command=save_url, style="Dark.TButton", width=10).pack(side="left", padx=3)
        ttk.Button(btns, text="Check online update", command=check_online_update, style="Green.TButton", width=20).pack(side="left", padx=3)
        ttk.Button(btns, text="Quay lại Mail", command=self.close_update_view, style="Dark.TButton", width=14).pack(side="right", padx=3)

        bottom = ttk.Frame(frame, style="Root.TFrame")
        bottom.pack(fill="x", pady=(8, 0))
        ttk.Label(bottom, textvariable=update_status, style="Muted.TLabel").pack(side="right")

    def close_restore_view(self):
        if hasattr(self, "restore_overlay") and self.restore_overlay is not None:
            try:
                self.restore_overlay.destroy()
            except Exception:
                pass
            self.restore_overlay = None
            self.status_var.set("Đã quay lại màn hình Mail.")

    def open_restore_tool(self, initial_text=None):
        if hasattr(self, "restore_overlay") and self.restore_overlay is not None:
            try:
                self.restore_overlay.lift()
                return
            except Exception:
                self.restore_overlay = None

        self.restore_overlay = tk.Frame(self, bg=BG)
        self.restore_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.restore_overlay.lift()

        restore_state = {"paths": [], "files": [], "results": []}

        frame = ttk.Frame(self.restore_overlay, style="Root.TFrame", padding=10)
        frame.pack(fill="both", expand=True)

        header = ttk.Frame(frame, style="Root.TFrame")
        header.pack(fill="x", pady=(0, 8))

        title_box = ttk.Frame(header, style="Root.TFrame")
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text="🕒 Check thời gian Restore", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_box,
            text="Paste mail/số cần tìm • thêm file/folder • lấy ngày sửa đổi của file restore",
            style="Sub.TLabel"
        ).pack(anchor="w")

        ttk.Button(header, text="Quay lại Mail", command=self.close_restore_view, style="Dark.TButton").pack(side="right", padx=3)

        top = ttk.Frame(frame, style="Panel.TFrame", padding=8)
        top.pack(fill="x", pady=(0, 8))

        ttk.Label(top, text="Kiểu lấy ngày:", background=PANEL, foreground=MUTED).pack(side="left")
        mode_var = tk.StringVar(value="Mới nhất = restore")
        mode_box = ttk.Combobox(
            top,
            textvariable=mode_var,
            state="readonly",
            width=18,
            values=["Mới nhất = restore", "Cũ nhất", "Ưu tiên tên restore"]
        )
        mode_box.pack(side="left", padx=(5, 12))

        path_count_var = tk.StringVar(value="Chưa thêm file/folder")
        ttk.Label(top, textvariable=path_count_var, background=PANEL, foreground=BLUE).pack(side="left", padx=(0, 10))

        body = ttk.Frame(frame, style="Root.TFrame")
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="Mail / số cần tìm", style="Dark.TLabelframe")
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        right = ttk.LabelFrame(body, text="Kết quả Restore", style="Dark.TLabelframe")
        right.pack(side="right", fill="both", expand=True, padx=(6, 0))

        input_box = tk.Text(
            left,
            height=10,
            wrap="none",
            bg=CARD,
            fg=TEXT,
            insertbackground=BLUE,
            selectbackground="#075985",
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Consolas", 10),
            padx=8,
            pady=8
        )
        input_box.pack(fill="both", expand=True, padx=8, pady=8)

        result_cols = ("stt", "key", "date", "file")
        tree = ttk.Treeview(right, columns=result_cols, show="headings", selectmode="extended")
        tree.heading("stt", text="#")
        tree.heading("key", text="Mail / số")
        tree.heading("date", text="Ngày restore")
        tree.heading("file", text="File tìm thấy")
        tree.column("stt", width=45, anchor="center", stretch=False)
        tree.column("key", width=220, anchor="w")
        tree.column("date", width=135, anchor="center", stretch=False)
        tree.column("file", width=260, anchor="w")
        tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)

        tree.tag_configure("found", foreground=GREEN)
        tree.tag_configure("notfound", foreground=GRAY)
        tree.tag_configure("blank", background="#0b1220")

        scroll = ttk.Scrollbar(right, command=tree.yview)
        scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)
        tree.configure(yscrollcommand=scroll.set)

        bottom = ttk.Frame(frame, style="Root.TFrame")
        bottom.pack(fill="x", pady=(10, 0))

        progress = ttk.Progressbar(bottom, mode="determinate")
        progress.pack(side="left", fill="x", expand=True, padx=(0, 8))

        restore_percent = tk.StringVar(value="0%")
        ttk.Label(bottom, textvariable=restore_percent, style="Sub.TLabel", width=5, anchor="center").pack(side="left", padx=(0, 8))

        status = tk.StringVar(value="Thêm file/folder rồi bấm Tìm restore.")
        ttk.Label(bottom, textvariable=status, style="Muted.TLabel").pack(side="right")

        def refresh_path_label():
            restore_state["paths"] = list(dict.fromkeys(restore_state["paths"]))
            path_count_var.set(f"{len(restore_state['paths']):,} path đã thêm")

        def add_files():
            files = filedialog.askopenfilenames(title="Chọn file để tìm restore")
            if files:
                restore_state["paths"].extend(list(files))
                refresh_path_label()
                status.set(f"Đã thêm {len(files):,} file.")

        def add_folder():
            folder = filedialog.askdirectory(title="Chọn folder chứa file restore")
            if folder:
                restore_state["paths"].append(folder)
                refresh_path_label()
                status.set("Đã thêm folder.")

        def remove_duplicate_paths():
            before = len(restore_state["paths"])
            unique = []
            seen = set()
            for p in restore_state["paths"]:
                try:
                    k = str(Path(p).resolve()).lower()
                except Exception:
                    k = str(p).lower()
                if k in seen:
                    continue
                seen.add(k)
                unique.append(p)
            restore_state["paths"] = unique
            refresh_path_label()
            status.set(f"Đã xóa {before - len(unique):,} path trùng.")

        def clear_paths():
            restore_state["paths"] = []
            restore_state["files"] = []
            refresh_path_label()
            status.set("Đã xóa danh sách file/folder.")

        def get_mode():
            v = mode_var.get()
            if "Cũ" in v:
                return "oldest"
            if "Ưu" in v:
                return "restore_first"
            return "newest"

        def render_results(rows):
            tree.delete(*tree.get_children())
            found = 0
            total = 0
            stt = 1
            for r in rows:
                if r.get("kind") == "blank":
                    tree.insert("", "end", values=("", "", "", ""), tags=("blank",))
                    continue

                total += 1
                if r.get("kind") == "found":
                    found += 1

                tree.insert(
                    "",
                    "end",
                    values=(stt, r.get("key", ""), r.get("date", ""), r.get("file", "")),
                    tags=(r.get("kind", "notfound"),)
                )
                stt += 1

            status.set(f"Xong {total:,} dòng | tìm thấy {found:,} | không thấy {total - found:,}")

        def run_restore():
            if not restore_state["paths"]:
                messagebox.showwarning("Thiếu file/folder", "Bạn chưa thêm file hoặc folder để tìm.")
                return

            raw_input = input_box.get("1.0", "end")
            if not raw_input.strip():
                messagebox.showwarning("Thiếu dữ liệu", "Bạn chưa paste mail/số cần tìm.")
                return

            progress["value"] = 0
            progress["maximum"] = 100
            restore_percent.set("0%")
            status.set("0% | Đang quét file/folder...")

            def worker():
                try:
                    files = restore_collect_files(restore_state["paths"])
                    restore_state["files"] = files
                    rows = restore_build_results(raw_input, files, get_mode())
                    restore_state["results"] = rows

                    history_text = "\n".join([
                        "" if r.get("kind") == "blank" else f"{r.get('key','')}\t{r.get('date','')}\t{r.get('file','')}\t{r.get('path','')}"
                        for r in rows
                    ])

                    self.after(0, lambda: progress.configure(value=100))
                    self.after(0, lambda: restore_percent.set("100%"))
                    self.after(0, lambda: render_results(rows))
                    self.after(0, lambda: status.set("100% | " + status.get() + f" | quét {len(files):,} file"))
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Lỗi restore", str(e)))
                    self.after(0, lambda: status.set("Lỗi khi quét restore."))

            threading.Thread(target=worker, daemon=True).start()

        def copy_restore_dates():
            rows = restore_state.get("results", [])
            if not rows:
                status.set("Chưa có kết quả để copy.")
                return
            lines = []
            count = 0
            for r in rows:
                if r.get("kind") == "blank":
                    lines.append("")
                    continue
                date = r.get("date", "")
                lines.append(date)
                if date:
                    count += 1
            self.clipboard_clear()
            self.clipboard_append("\n".join(lines))
            status.set(f"Đã copy {count:,} ngày restore, giữ dòng cách.")

        def copy_restore_full():
            rows = restore_state.get("results", [])
            if not rows:
                status.set("Chưa có kết quả để copy.")
                return
            lines = []
            for r in rows:
                if r.get("kind") == "blank":
                    lines.append("")
                else:
                    lines.append(f"{r.get('key','')}\t{r.get('date','')}\t{r.get('file','')}")
            self.clipboard_clear()
            self.clipboard_append("\n".join(lines))
            status.set("Đã copy kết quả restore.")

        def clear_all_restore():
            input_box.delete("1.0", "end")
            tree.delete(*tree.get_children())
            restore_state["results"] = []
            progress["value"] = 0
            restore_percent.set("0%")
            status.set("Đã xóa dữ liệu restore.")

        def on_tree_click(event):
            try:
                item_id = tree.identify_row(event.y)
                col = tree.identify_column(event.x)
                if not item_id or col != "#3":
                    return
                values = tree.item(item_id, "values")
                if len(values) >= 3 and values[2]:
                    self.clipboard_clear()
                    self.clipboard_append(values[2])
                    status.set(f"Đã copy ngày restore: {values[2]}")
            except Exception:
                pass

        tree.bind("<ButtonRelease-1>", on_tree_click)

        btns = ttk.Frame(frame, style="Panel.TFrame", padding=8)
        btns.pack(fill="x", pady=(10, 0))

        r1 = ttk.Frame(btns, style="Panel.TFrame")
        r1.pack(fill="x")

        ttk.Label(r1, text="Nguồn file:", background=PANEL, foreground=MUTED, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        ttk.Button(r1, text="Thêm file", command=add_files, style="Dark.TButton", width=11).pack(side="left", padx=3)
        ttk.Button(r1, text="Thêm folder", command=add_folder, style="Dark.TButton", width=12).pack(side="left", padx=3)
        ttk.Button(r1, text="Xóa path trùng", command=remove_duplicate_paths, style="Purple.TButton", width=14).pack(side="left", padx=3)
        ttk.Button(r1, text="Clear path", command=clear_paths, style="Danger.TButton", width=10).pack(side="left", padx=3)

        r2 = ttk.Frame(btns, style="Panel.TFrame")
        r2.pack(fill="x", pady=(6, 0))

        ttk.Label(r2, text="Restore:", background=PANEL, foreground=MUTED, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        ttk.Button(r2, text="Tìm restore", command=run_restore, style="Green.TButton", width=12).pack(side="left", padx=3)
        ttk.Button(r2, text="Copy ngày", command=copy_restore_dates, style="Accent.TButton", width=12).pack(side="left", padx=3)
        ttk.Button(r2, text="Copy kết quả", command=copy_restore_full, style="Purple.TButton", width=12).pack(side="left", padx=3)
        ttk.Button(r2, text="Xóa", command=clear_all_restore, style="Danger.TButton", width=9).pack(side="left", padx=3)
        ttk.Button(r2, text="Quay lại Mail", command=self.close_restore_view, style="Dark.TButton", width=14).pack(side="right", padx=3)

        if initial_text:
            input_box.insert("1.0", initial_text)

    def close_card_view(self):
        if hasattr(self, "card_overlay") and self.card_overlay is not None:
            try:
                self.card_overlay.destroy()
            except Exception:
                pass
            self.card_overlay = None
            self.status_var.set("Đã quay lại màn hình Mail.")

    def open_card_tool(self, initial_text=None):
        if hasattr(self, "card_overlay") and self.card_overlay is not None:
            try:
                self.card_overlay.lift()
                return
            except Exception:
                self.card_overlay = None

        self.card_overlay = tk.Frame(self, bg=BG)
        self.card_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.card_overlay.lift()

        frame = ttk.Frame(self.card_overlay, style="Root.TFrame", padding=10)
        frame.pack(fill="both", expand=True)

        header = ttk.Frame(frame, style="Root.TFrame")
        header.pack(fill="x", pady=(0, 8))

        title_box = ttk.Frame(header, style="Root.TFrame")
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text="💳 Tool lọc thẻ hết hạn", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_box,
            text="Lọc thẻ • giữ đuôi dòng • tự đổi năm 2027 thành 27",
            style="Sub.TLabel"
        ).pack(anchor="w")

        ttk.Button(header, text="Quay lại Mail", command=self.close_card_view, style="Dark.TButton").pack(side="right", padx=3)

        options = ttk.Frame(frame, style="Panel.TFrame", padding=8)
        options.pack(fill="x", pady=(0, 8))

        ttk.Label(options, text="Ngày kiểm tra:", background=PANEL, foreground=MUTED).pack(side="left")
        check_date_var = tk.StringVar(value=datetime.date.today().isoformat())
        check_entry = tk.Entry(options, textvariable=check_date_var, width=12, bg=CARD, fg=TEXT, insertbackground=BLUE, relief="flat")
        check_entry.pack(side="left", padx=(5, 12))

        ttk.Label(options, text="Xóa trùng theo:", background=PANEL, foreground=MUTED).pack(side="left")
        dedupe_var = tk.StringVar(value="Số thẻ + hạn + đuôi")
        dedupe_box = ttk.Combobox(
            options,
            textvariable=dedupe_var,
            state="readonly",
            width=22,
            values=["Số thẻ + hạn + đuôi", "Nguyên dòng", "Chỉ số thẻ"]
        )
        dedupe_box.pack(side="left", padx=(5, 12))

        ttk.Label(options, text="Xuất:", background=PANEL, foreground=MUTED).pack(side="left")
        output_var = tk.StringVar(value="Giữ nguyên dòng")
        output_box = ttk.Combobox(
            options,
            textvariable=output_var,
            state="readonly",
            width=17,
            values=["Giữ nguyên dòng", "Ẩn số thẻ", "Tháng/năm + dòng"]
        )
        output_box.pack(side="left", padx=(5, 12))

        auto_dedupe_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options, text="Tự bỏ trùng", variable=auto_dedupe_var).pack(side="left")

        stats = tk.Frame(frame, bg=BG)
        stats.pack(fill="x", pady=(0, 8))

        stat_vars = {
            "total": tk.StringVar(value="Tổng\n0"),
            "valid": tk.StringVar(value="Còn hạn\n0"),
            "expired": tk.StringVar(value="Hết hạn\n0"),
            "duplicate": tk.StringVar(value="Trùng\n0"),
            "invalid": tk.StringVar(value="Lỗi\n0"),
        }

        stat_colors = {
            "total": BLUE,
            "valid": GREEN,
            "expired": RED,
            "duplicate": PURPLE,
            "invalid": YELLOW,
        }

        card_state = {"results": None, "tab": "valid"}

        def set_card_tab(tab):
            card_state["tab"] = tab
            render_card()

        for key, var in stat_vars.items():
            btn = tk.Button(
                stats,
                textvariable=var,
                command=lambda k=key: set_card_tab("all" if k == "total" else k),
                bg="#0b1220",
                fg=stat_colors[key],
                activebackground="#1e293b",
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                padx=10,
                pady=6,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2"
            )
            btn.pack(side="left", fill="x", expand=True, padx=3)

        body = ttk.Frame(frame, style="Root.TFrame")
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="Dữ liệu thẻ", style="Dark.TLabelframe")
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        right = ttk.LabelFrame(body, text="Kết quả", style="Dark.TLabelframe")
        right.pack(side="right", fill="both", expand=True, padx=(6, 0))

        input_box = tk.Text(
            left,
            wrap="none",
            bg=CARD,
            fg=TEXT,
            insertbackground=BLUE,
            selectbackground="#075985",
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Consolas", 10),
            padx=8,
            pady=8
        )
        input_box.pack(fill="both", expand=True, padx=8, pady=8)

        output_box_text = tk.Text(
            right,
            wrap="none",
            bg=CARD,
            fg=TEXT,
            insertbackground=BLUE,
            selectbackground="#075985",
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Consolas", 10),
            padx=8,
            pady=8
        )
        output_box_text.pack(fill="both", expand=True, padx=8, pady=8)

        bottom = ttk.Frame(frame, style="Root.TFrame")
        bottom.pack(fill="x", pady=(10, 0))

        card_status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(bottom, textvariable=card_status, style="Muted.TLabel").pack(side="right")

        def get_dedupe_mode():
            v = dedupe_var.get()
            if "Nguyên" in v:
                return "line"
            if "Chỉ" in v:
                return "card_only"
            return "card_exp_tail"

        def get_output_mode():
            v = output_var.get()
            if "Ẩn" in v:
                return "masked"
            if "Tháng" in v:
                return "expiry"
            return "original"

        def format_card_list(tab):
            res = card_state.get("results") or {}
            arr = res.get(tab, [])
            mode = get_output_mode()
            if tab == "all":
                return "\n".join([f"[{x.get('label','')}] {card_format_item(x, mode)}" for x in arr])
            return "\n".join([card_format_item(x, mode) for x in arr])

        def render_card():
            res = card_state.get("results")
            if not res:
                output_box_text.delete("1.0", "end")
                return

            stat_vars["total"].set(f"Tổng\n{res.get('total',0):,}")
            stat_vars["valid"].set(f"Còn hạn\n{len(res.get('valid',[])):,}")
            stat_vars["expired"].set(f"Hết hạn\n{len(res.get('expired',[])):,}")
            stat_vars["duplicate"].set(f"Trùng\n{len(res.get('duplicate',[])):,}")
            stat_vars["invalid"].set(f"Lỗi\n{len(res.get('invalid',[])):,}")

            tab = card_state.get("tab", "valid")
            text = format_card_list(tab)
            output_box_text.delete("1.0", "end")
            output_box_text.insert("1.0", text)
            card_status.set(f"Đang xem {tab}: {len(res.get(tab, [])):,} dòng")

        def run_filter():
            res = card_filter_lines(
                input_box.get("1.0", "end"),
                check_date_var.get().strip(),
                get_dedupe_mode(),
                auto_dedupe_var.get()
            )
            card_state["results"] = res
            render_card()
            card_status.set("100% | Đã lọc thẻ.")

        def remove_duplicate_cards():
            res = card_filter_lines(
                input_box.get("1.0", "end"),
                check_date_var.get().strip(),
                get_dedupe_mode(),
                True
            )
            input_box.delete("1.0", "end")
            input_box.insert("1.0", "\n".join([card_year_to_yy_line(x) for x in res.get("uniqueLines", [])]))
            card_state["results"] = res
            render_card()
            card_status.set(f"Đã xóa trùng, còn {len(res.get('uniqueLines', [])):,} dòng.")

        def copy_current():
            text = output_box_text.get("1.0", "end").strip("\n")
            self.clipboard_clear()
            self.clipboard_append(text)
            card_status.set("Đã copy mục đang xem.")

        def copy_valid():
            res = card_state.get("results") or {}
            text = "\n".join([card_format_item(x, get_output_mode()) for x in res.get("valid", [])])
            self.clipboard_clear()
            self.clipboard_append(text)
            card_status.set(f"Đã copy {len(res.get('valid', [])):,} thẻ còn hạn.")

        def copy_unique():
            res = card_state.get("results") or {}
            if not res:
                run_filter()
                res = card_state.get("results") or {}
            text = "\n".join([card_year_to_yy_line(x) for x in res.get("uniqueLines", [])])
            self.clipboard_clear()
            self.clipboard_append(text)
            card_status.set(f"Đã copy {len(res.get('uniqueLines', [])):,} dòng đã xóa trùng.")

        def clear_card():
            input_box.delete("1.0", "end")
            output_box_text.delete("1.0", "end")
            card_state["results"] = None
            for k, var in stat_vars.items():
                labels = {"total": "Tổng", "valid": "Còn hạn", "expired": "Hết hạn", "duplicate": "Trùng", "invalid": "Lỗi"}
                var.set(f"{labels[k]}\n0")
            card_status.set("Đã xóa.")

        btns = ttk.Frame(frame, style="Panel.TFrame", padding=8)
        btns.pack(fill="x", pady=(10, 0))

        ttk.Label(btns, text="Lọc:", background=PANEL, foreground=MUTED, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Lọc ngay", command=run_filter, style="Green.TButton", width=11).pack(side="left", padx=3)
        ttk.Button(btns, text="Xóa trùng", command=remove_duplicate_cards, style="Purple.TButton", width=11).pack(side="left", padx=3)

        ttk.Label(btns, text="Copy:", background=PANEL, foreground=MUTED, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(18, 6))
        ttk.Button(btns, text="Đang xem", command=copy_current, style="Dark.TButton", width=11).pack(side="left", padx=3)
        ttk.Button(btns, text="Còn hạn", command=copy_valid, style="Accent.TButton", width=11).pack(side="left", padx=3)
        ttk.Button(btns, text="Đã xóa trùng", command=copy_unique, style="Dark.TButton", width=13).pack(side="left", padx=3)

        ttk.Button(btns, text="Xóa", command=clear_card, style="Danger.TButton", width=9).pack(side="left", padx=(18, 3))
        ttk.Button(btns, text="Quay lại Mail", command=self.close_card_view, style="Dark.TButton", width=14).pack(side="right", padx=3)

        if initial_text:
            input_box.insert("1.0", initial_text)

    def close_2fa_view(self):
        if hasattr(self, "twofa_overlay") and self.twofa_overlay is not None:
            try:
                self.twofa_overlay.destroy()
            except Exception:
                pass
            self.twofa_overlay = None
            self.status_var.set("Đã quay lại màn hình Mail.")

    def open_2fa_tool(self, initial_text=None, auto_run=False):
        if hasattr(self, "twofa_overlay") and self.twofa_overlay is not None:
            try:
                self.twofa_overlay.lift()
                return
            except Exception:
                self.twofa_overlay = None

        self.twofa_overlay = tk.Frame(self, bg=BG)
        self.twofa_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.twofa_overlay.lift()

        frame = ttk.Frame(self.twofa_overlay, style="Root.TFrame", padding=10)
        frame.pack(fill="both", expand=True)

        header = ttk.Frame(frame, style="Root.TFrame")
        header.pack(fill="x", pady=(0, 8))

        title_box = ttk.Frame(header, style="Root.TFrame")
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text="🔐 Khánh Sky 2FA", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_box,
            text="Paste secret / otpauth / 2fa.live • lấy code 6 số • giữ dòng cách",
            style="Sub.TLabel"
        ).pack(anchor="w")

        ttk.Button(header, text="Quay lại Mail", command=self.close_2fa_view, style="Dark.TButton").pack(side="right", padx=3)

        guide = ttk.Frame(frame, style="Panel.TFrame", padding=8)
        guide.pack(fill="x", pady=(0, 8))
        ttk.Label(
            guide,
            text="Paste mỗi dòng một secret. Nhận cả otpauth://...?secret=... hoặc https://2fa.live/tok/SECRET. Bấm vào mã ở ô kết quả là tự copy.",
            background=PANEL,
            foreground=BLUE
        ).pack(anchor="w")

        top_2fa = ttk.Frame(frame, style="Root.TFrame")
        top_2fa.pack(fill="both", expand=True)

        left = ttk.LabelFrame(top_2fa, text="Secret 2FA", style="Dark.TLabelframe")
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        right = ttk.LabelFrame(top_2fa, text="Code 2FA", style="Dark.TLabelframe")
        right.pack(side="right", fill="both", expand=True, padx=(6, 0))

        input_box = tk.Text(
            left,
            wrap="none",
            bg=CARD,
            fg=TEXT,
            insertbackground=BLUE,
            selectbackground="#075985",
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Consolas", 10),
            padx=8,
            pady=8
        )
        input_box.pack(fill="both", expand=True, padx=8, pady=8)

        result_box = tk.Text(
            right,
            wrap="none",
            bg=CARD,
            fg=TEXT,
            insertbackground=BLUE,
            selectbackground="#075985",
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Consolas", 12, "bold"),
            padx=8,
            pady=8
        )
        result_box.pack(fill="both", expand=True, padx=8, pady=8)

        def copy_clicked_2fa_result(event):
            try:
                idx = result_box.index(f"@{event.x},{event.y}")
                line = result_box.get(f"{idx} linestart", f"{idx} lineend").strip()
                if not line or not re.fullmatch(r"\d{6}", line):
                    return
                self.clipboard_clear()
                self.clipboard_append(line)
                result_box.tag_remove("click_copy_line", "1.0", "end")
                result_box.tag_add("click_copy_line", f"{idx} linestart", f"{idx} lineend")
                result_box.tag_configure("click_copy_line", background="#075985", foreground="#ffffff")
                twofa_status.set(f"Đã copy 2FA: {line}")
            except Exception:
                pass

        result_box.bind("<ButtonRelease-1>", copy_clicked_2fa_result)
        result_box.configure(cursor="hand2")

        bottom = ttk.Frame(frame, style="Root.TFrame")
        bottom.pack(fill="x", pady=(10, 0))

        progress = ttk.Progressbar(bottom, mode="determinate")
        progress.pack(side="left", fill="x", expand=True, padx=(0, 8))

        twofa_percent = tk.StringVar(value="0%")
        ttk.Label(bottom, textvariable=twofa_percent, style="Sub.TLabel", width=5, anchor="center").pack(side="left", padx=(0, 8))

        twofa_status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(bottom, textvariable=twofa_status, style="Muted.TLabel").pack(side="right")

        def get_rows():
            return extract_2fa_rows(input_box.get("1.0", "end"))

        def run_2fa():
            rows = get_rows()
            valid = [r for r in rows if r.get("kind") == "2fa"]

            if not valid:
                messagebox.showwarning("Thiếu secret", "Bạn chưa paste secret 2FA.")
                return

            result_box.delete("1.0", "end")
            progress["maximum"] = max(len(valid), 1)
            progress["value"] = 0
            twofa_percent.set("0%")

            out = []
            done = 0
            for row in rows:
                if row.get("kind") == "blank":
                    out.append("")
                    continue

                code_2fa = calc_totp(row.get("secret", ""))
                out.append(code_2fa)
                done += 1
                progress["value"] = done
                twofa_percent.set(f"{int((done / max(len(valid), 1)) * 100)}%")

            text_out = "\n".join(out)
            result_box.insert("1.0", text_out)
            left_time = 30 - (int(time.time()) % 30)
            twofa_percent.set("100%")
            twofa_status.set(f"100% | Đã lấy {len(valid):,} code | còn {left_time}s đổi mã.")

        def copy_all():
            data = result_box.get("1.0", "end").strip("\n")
            self.clipboard_clear()
            self.clipboard_append(data)
            twofa_status.set("Đã copy 2FA.")

        def copy_clean():
            lines = []
            count = 0
            for line in result_box.get("1.0", "end").splitlines():
                s = line.strip()
                if re.fullmatch(r"\d{6}", s):
                    lines.append(s)
                    count += 1
                else:
                    lines.append("")
            self.clipboard_clear()
            self.clipboard_append("\n".join(lines))
            twofa_status.set(f"Đã copy {count:,} code 2FA sạch và giữ dòng cách.")

        def clear_2fa():
            input_box.delete("1.0", "end")
            result_box.delete("1.0", "end")
            progress["value"] = 0
            twofa_percent.set("0%")
            twofa_status.set("Đã xóa.")

        btns = ttk.Frame(frame, style="Panel.TFrame", padding=8)
        btns.pack(fill="x", pady=(10, 0))

        twofa_btn_row1 = ttk.Frame(btns, style="Panel.TFrame")
        twofa_btn_row1.pack(fill="x")

        ttk.Label(
            twofa_btn_row1,
            text="Lấy dữ liệu:",
            background=PANEL,
            foreground=MUTED,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 6))
        ttk.Button(twofa_btn_row1, text="Lấy 2FA", command=run_2fa, style="Green.TButton", width=12).pack(side="left", padx=3)

        ttk.Label(
            twofa_btn_row1,
            text="Copy:",
            background=PANEL,
            foreground=MUTED,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(18, 6))
        ttk.Button(twofa_btn_row1, text="Copy 2FA", command=copy_all, style="Accent.TButton", width=12).pack(side="left", padx=3)
        ttk.Button(twofa_btn_row1, text="2FA sạch", command=copy_clean, style="Purple.TButton", width=12).pack(side="left", padx=3)

        twofa_btn_row2 = ttk.Frame(btns, style="Panel.TFrame")
        twofa_btn_row2.pack(fill="x", pady=(6, 0))
        ttk.Label(
            twofa_btn_row2,
            text="Tác vụ:",
            background=PANEL,
            foreground=MUTED,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 6))
        ttk.Button(twofa_btn_row2, text="Xóa", command=clear_2fa, style="Danger.TButton", width=10).pack(side="left", padx=3)
        ttk.Button(twofa_btn_row2, text="Quay lại Mail", command=self.close_2fa_view, style="Dark.TButton", width=14).pack(side="right", padx=3)

        if initial_text:
            input_box.insert("1.0", initial_text)
            if auto_run:
                self.after(250, run_2fa)

    def close_sms_view(self):
        if hasattr(self, "sms_overlay") and self.sms_overlay is not None:
            try:
                self.sms_overlay.destroy()
            except Exception:
                pass
            self.sms_overlay = None
            self.status_var.set("Đã quay lại màn hình Mail.")

    def open_sms_tool(self, initial_text=None, auto_action=None):
        # Không mở popup nữa. Mở giao diện SMS ngay trong app bằng lớp phủ toàn màn hình.
        if hasattr(self, "sms_overlay") and self.sms_overlay is not None:
            try:
                self.sms_overlay.lift()
                return
            except Exception:
                self.sms_overlay = None

        self.sms_overlay = tk.Frame(self, bg=BG)
        self.sms_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.sms_overlay.lift()

        frame = ttk.Frame(self.sms_overlay, style="Root.TFrame", padding=10)
        frame.pack(fill="both", expand=True)

        header = ttk.Frame(frame, style="Root.TFrame")
        header.pack(fill="x", pady=(0, 8))

        title_box = ttk.Frame(header, style="Root.TFrame")
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text="⚡ Khánh Sky SMS", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_box,
            text="Lấy code / date ngay trong app • không popup • giữ dòng cách",
            style="Sub.TLabel"
        ).pack(anchor="w")

        ttk.Button(header, text="Quay lại Mail", command=self.close_sms_view, style="Dark.TButton").pack(side="right", padx=3)

        guide = ttk.Frame(frame, style="Panel.TFrame", padding=8)
        guide.pack(fill="x", pady=(0, 8))
        ttk.Label(
            guide,
            text="Paste link dạng https://sms222.us?token=... hoặc https://sms222.us/?token=... mỗi dòng một link. Bấm vào mã/date ở ô kết quả là tự copy.",
            background=PANEL,
            foreground=BLUE
        ).pack(anchor="w")

        top_sms = ttk.Frame(frame, style="Root.TFrame")
        top_sms.pack(fill="both", expand=True)

        left = ttk.LabelFrame(top_sms, text="Link SMS", style="Dark.TLabelframe")
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        right = ttk.LabelFrame(top_sms, text="Kết quả Code / Date", style="Dark.TLabelframe")
        right.pack(side="right", fill="both", expand=True, padx=(6, 0))

        sms_input = tk.Text(
            left,
            wrap="none",
            bg=CARD,
            fg=TEXT,
            insertbackground=BLUE,
            selectbackground="#075985",
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Consolas", 10),
            padx=8,
            pady=8
        )
        sms_input.pack(fill="both", expand=True, padx=8, pady=8)

        sms_result = tk.Text(
            right,
            wrap="none",
            bg=CARD,
            fg=TEXT,
            insertbackground=BLUE,
            selectbackground="#075985",
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Consolas", 10),
            padx=8,
            pady=8
        )
        sms_result.pack(fill="both", expand=True, padx=8, pady=8)

        def copy_clicked_sms_result(event):
            try:
                idx = sms_result.index(f"@{event.x},{event.y}")
                line = sms_result.get(f"{idx} linestart", f"{idx} lineend").strip()
                if not line or line.startswith("lỗi") or line in {"không có mã", "không có date"}:
                    return
                self.clipboard_clear()
                self.clipboard_append(line)
                sms_result.tag_remove("click_copy_line", "1.0", "end")
                sms_result.tag_add("click_copy_line", f"{idx} linestart", f"{idx} lineend")
                sms_result.tag_configure("click_copy_line", background="#075985", foreground="#ffffff")
                sms_status.set(f"Đã copy: {line}")
            except Exception:
                pass

        sms_result.bind("<ButtonRelease-1>", copy_clicked_sms_result)
        sms_result.configure(cursor="hand2")

        bottom = ttk.Frame(frame, style="Root.TFrame")
        bottom.pack(fill="x", pady=(10, 0))

        progress = ttk.Progressbar(bottom, mode="determinate")
        progress.pack(side="left", fill="x", expand=True, padx=(0, 8))

        sms_percent = tk.StringVar(value="0%")
        ttk.Label(bottom, textvariable=sms_percent, style="Sub.TLabel", width=5, anchor="center").pack(side="left", padx=(0, 8))

        sms_status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(bottom, textvariable=sms_status, style="Muted.TLabel").pack(side="right")

        def get_rows():
            return extract_sms_links(sms_input.get("1.0", "end"))

        def run_sms_action(action_name, fetch_func, missing_label):
            rows = get_rows()
            sms_rows = [r for r in rows if r.get("kind") == "sms"]
            if not sms_rows:
                messagebox.showwarning("Thiếu link", "Không nhận ra link SMS222. App nhận cả dạng https://sms222.us?token=... và https://sms222.us/?token=...")
                return

            sms_result.delete("1.0", "end")
            progress["maximum"] = max(len(sms_rows), 1)
            progress["value"] = 0
            sms_percent.set("0%")
            sms_status.set(f"0% | Đang {action_name} {len(sms_rows):,} link...")

            def worker():
                done = 0

                def fetch_one(row):
                    if row.get("kind") != "sms":
                        return ""
                    result = fetch_func(row.get("link", ""))
                    return result or missing_label

                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                    future_map = {}
                    for idx, row in enumerate(rows):
                        if row.get("kind") == "sms":
                            future_map[ex.submit(fetch_one, row)] = idx

                    result_by_index = {}
                    for fut in concurrent.futures.as_completed(future_map):
                        idx = future_map[fut]
                        try:
                            result_by_index[idx] = fut.result()
                        except Exception as e:
                            result_by_index[idx] = "lỗi: " + str(e)[:80]

                        done += 1
                        self.after(0, lambda d=done: progress.configure(value=d))
                        self.after(0, lambda d=done: sms_percent.set(f"{int((d / max(len(sms_rows), 1)) * 100)}%"))
                        self.after(0, lambda d=done: sms_status.set(f"{int((d / max(len(sms_rows), 1)) * 100)}% | Đang {action_name} {d:,}/{len(sms_rows):,} link..."))

                results = []
                for idx, row in enumerate(rows):
                    if row.get("kind") == "blank":
                        results.append("")
                    else:
                        results.append(result_by_index.get(idx, missing_label))

                text = "\n".join(results)
                self.after(0, lambda: sms_result.delete("1.0", "end"))
                self.after(0, lambda: sms_result.insert("1.0", text))
                self.after(0, lambda: sms_percent.set("100%"))
                self.after(0, lambda: sms_status.set(f"100% | Xong {action_name} {len(sms_rows):,} link."))

            threading.Thread(target=worker, daemon=True).start()

        def run_date_check():
            run_sms_action("check date", fetch_sms_date, "không có date")

        def run_sms_check():
            run_sms_action("lấy code", fetch_sms_code, "không có mã")

        def copy_codes():
            data = sms_result.get("1.0", "end").strip("\n")
            self.clipboard_clear()
            self.clipboard_append(data)
            sms_status.set("Đã copy code/date.")

        def copy_only_codes_clean():
            lines = []
            count = 0
            for line in sms_result.get("1.0", "end").splitlines():
                s = line.strip()
                if not s or s.startswith("lỗi") or s == "không có mã":
                    lines.append("")
                    continue
                lines.append(s)
                count += 1
            self.clipboard_clear()
            self.clipboard_append("\n".join(lines))
            sms_status.set(f"Đã copy {count:,} code sạch và giữ dòng cách.")

        def copy_only_dates_clean():
            lines = []
            count = 0
            for line in sms_result.get("1.0", "end").splitlines():
                s = line.strip()
                if not s or s.startswith("lỗi") or s == "không có date":
                    lines.append("")
                    continue
                if re.fullmatch(r"\d{2}/\d{2}/\d{4}", s):
                    lines.append(s)
                    count += 1
                else:
                    lines.append("")
            self.clipboard_clear()
            self.clipboard_append("\n".join(lines))
            sms_status.set(f"Đã copy {count:,} date sạch và giữ dòng cách.")

        def clear_sms():
            sms_input.delete("1.0", "end")
            sms_result.delete("1.0", "end")
            progress["value"] = 0
            sms_percent.set("0%")
            sms_status.set("Đã xóa.")

        btns = ttk.Frame(frame, style="Panel.TFrame", padding=8)
        btns.pack(fill="x", pady=(10, 0))

        sms_btn_row1 = ttk.Frame(btns, style="Panel.TFrame")
        sms_btn_row1.pack(fill="x")

        ttk.Label(
            sms_btn_row1,
            text="Lấy dữ liệu:",
            background=PANEL,
            foreground=MUTED,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 6))
        ttk.Button(sms_btn_row1, text="Lấy Code", command=run_sms_check, style="Green.TButton", width=12).pack(side="left", padx=3)
        ttk.Button(sms_btn_row1, text="Lấy Date", command=run_date_check, style="Accent.TButton", width=12).pack(side="left", padx=3)

        ttk.Label(
            sms_btn_row1,
            text="Copy:",
            background=PANEL,
            foreground=MUTED,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(18, 6))
        ttk.Button(sms_btn_row1, text="Đang hiện", command=copy_codes, style="Dark.TButton", width=12).pack(side="left", padx=3)
        ttk.Button(sms_btn_row1, text="Code sạch", command=copy_only_codes_clean, style="Purple.TButton", width=12).pack(side="left", padx=3)
        ttk.Button(sms_btn_row1, text="Date sạch", command=copy_only_dates_clean, style="Purple.TButton", width=12).pack(side="left", padx=3)

        sms_btn_row2 = ttk.Frame(btns, style="Panel.TFrame")
        sms_btn_row2.pack(fill="x", pady=(6, 0))
        ttk.Label(
            sms_btn_row2,
            text="Tác vụ:",
            background=PANEL,
            foreground=MUTED,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 6))
        ttk.Button(sms_btn_row2, text="Xóa", command=clear_sms, style="Danger.TButton", width=10).pack(side="left", padx=3)
        ttk.Button(sms_btn_row2, text="Quay lại Mail", command=self.close_sms_view, style="Dark.TButton", width=14).pack(side="right", padx=3)

        if initial_text:
            sms_input.insert("1.0", initial_text)
            if auto_action == "code":
                self.after(250, run_sms_check)
            elif auto_action == "date":
                self.after(250, run_date_check)

    def update_status_dashboard(self):
        counts = {
            "LIVE": 0,
            "VERIFYED": 0,
            "DISABLED": 0,
            "NOTEXISTS": 0,
            "WRONG": 0,
            "UNKNOW": 0,
            "ALL": 0,
        }

        for r in self.results:
            if r.get("kind") != "email":
                continue

            status = normalize_status(r.get("status", "UNKNOW"))
            counts["ALL"] += 1

            if status == "LIVE":
                counts["LIVE"] += 1
            elif status in {"VERIFYED", "VERIFY_PHONE"}:
                counts["VERIFYED"] += 1
            elif status == "DISABLED":
                counts["DISABLED"] += 1
            elif status == "NOTEXISTS":
                counts["NOTEXISTS"] += 1
            elif status in {"WRONG", "DIE"}:
                counts["WRONG"] += 1
            else:
                counts["UNKNOW"] += 1

        labels = {
            "LIVE": "LIVE",
            "VERIFYED": "VERIFY",
            "DISABLED": "DISABLED",
            "NOTEXISTS": "NOT EXIST",
            "WRONG": "WRONG/DIE",
            "UNKNOW": "UNKNOWN",
            "ALL": "ALL",
        }

        for key, var in getattr(self, "status_count_vars", {}).items():
            var.set(f"{labels.get(key, key)}\n{counts.get(key, 0):,}")

    def get_emails_by_dashboard_status(self, status_key):
        emails = []

        for r in self.results:
            if r.get("kind") != "email":
                continue

            email = str(r.get("email", "")).strip()
            status = normalize_status(r.get("status", "UNKNOW"))

            if status_key == "ALL":
                emails.append(email)
            elif status_key == "LIVE" and status == "LIVE":
                emails.append(email)
            elif status_key == "VERIFYED" and status in {"VERIFYED", "VERIFY_PHONE"}:
                emails.append(email)
            elif status_key == "DISABLED" and status == "DISABLED":
                emails.append(email)
            elif status_key == "NOTEXISTS" and status == "NOTEXISTS":
                emails.append(email)
            elif status_key == "WRONG" and status in {"WRONG", "DIE"}:
                emails.append(email)
            elif status_key == "UNKNOW" and status == "UNKNOW":
                emails.append(email)

        return emails

    def show_status_emails(self, status_key):
        emails = self.get_emails_by_dashboard_status(status_key)

        labels = {
            "LIVE": "LIVE",
            "VERIFYED": "VERIFY / VERIFY_PHONE",
            "DISABLED": "DISABLED",
            "NOTEXISTS": "NOT EXIST",
            "WRONG": "WRONG / DIE",
            "UNKNOW": "UNKNOWN",
            "ALL": "ALL",
        }
        title = labels.get(status_key, status_key)

        win = tk.Toplevel(self)
        win.title(f"{title} - {len(emails):,} mail")
        win.geometry("620x520")
        win.configure(bg=BG)
        win.transient(self)

        frame = ttk.Frame(win, style="Root.TFrame", padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=f"{title}: {len(emails):,} mail", style="Title.TLabel").pack(anchor="w", pady=(0, 8))

        text_box = tk.Text(
            frame,
            wrap="none",
            bg=CARD,
            fg=TEXT,
            insertbackground=BLUE,
            selectbackground="#075985",
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Consolas", 10),
            padx=8,
            pady=8
        )
        text_box.pack(side="top", fill="both", expand=True)
        text_box.insert("1.0", "\n".join(emails))

        btns = ttk.Frame(frame, style="Root.TFrame")
        btns.pack(fill="x", pady=(10, 0))

        def copy_list():
            self.clipboard_clear()
            self.clipboard_append("\n".join(emails))
            self.status_var.set(f"Đã copy {len(emails):,} mail {title}.")
            win.destroy()

        ttk.Button(btns, text="Copy danh sách này", command=copy_list, style="Green.TButton").pack(side="right")
        ttk.Button(btns, text="Đóng", command=win.destroy, style="Dark.TButton").pack(side="right", padx=(0, 8))

    def on_tree_click(self, event):
        # Bấm vào cột Status của một dòng thì hiện mail của cùng tình trạng đó.
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        col = self.tree.identify_column(event.x)
        if col != "#3":
            return

        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        values = self.tree.item(item_id, "values")
        if len(values) < 3:
            return

        status = normalize_status(values[2])
        if status in {"VERIFYED", "VERIFY_PHONE"}:
            key = "VERIFYED"
        elif status in {"WRONG", "DIE"}:
            key = "WRONG"
        elif status in {"LIVE", "DISABLED", "NOTEXISTS", "UNKNOW"}:
            key = status
        else:
            key = "UNKNOW"

        self.show_status_emails(key)

    def toggle_input_height(self):
        try:
            if getattr(self, "input_compact", False):
                self.input_text.configure(height=6)
                self.input_compact = False
                self.save_ui_config()
                self.status_var.set("Đã mở rộng ô nhập.")
            else:
                self.input_text.configure(height=3)
                self.input_compact = True
                self.save_ui_config()
                self.status_var.set("Đã thu gọn ô nhập, bảng kết quả rộng hơn.")
        except Exception:
            pass

    def open_api_dialog(self):
        win = tk.Toplevel(self)
        win.title("API settings")
        win.geometry("660x320")
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()

        frame = ttk.Frame(win, style="Root.TFrame", padding=14)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="API Settings", style="Title.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

        vars_map = {}
        providers = self.cfg.setdefault("providers", {})
        for i, key in enumerate(PROVIDER_ORDER, start=1):
            p = providers.setdefault(key, PROVIDERS[key].copy())
            enabled = tk.BooleanVar(value=bool(p.get("enabled", True)))
            api = tk.StringVar(value=str(p.get("api_key", "")))

            ttk.Checkbutton(frame, variable=enabled).grid(row=i, column=0, sticky="w", pady=5)
            ttk.Label(frame, text=p.get("name", key), width=16, background=BG, foreground=TEXT).grid(row=i, column=1, sticky="w", pady=5)

            ent = tk.Entry(
                frame,
                textvariable=api,
                width=46,
                show="*",
                bg=CARD,
                fg=TEXT,
                insertbackground=BLUE,
                relief="flat",
                bd=0
            )
            ent.grid(row=i, column=2, sticky="we", pady=5, ipady=5)

            if key == "gonvl":
                ent.configure(state="disabled", disabledbackground="#182235", disabledforeground=MUTED)
                ttk.Label(frame, text="Không cần key | 10/lô", background=BG, foreground=MUTED).grid(row=i, column=3, sticky="w", padx=8)
            vars_map[key] = (enabled, api)

        frame.columnconfigure(2, weight=1)

        ttk.Label(
            frame,
            text="Gonvl vẫn check 10 mail/lô, Turbo chạy song song nhiều lô để nhanh hơn.",
            background=BG,
            foreground=BLUE
        ).grid(row=8, column=0, columnspan=4, sticky="w", pady=(16, 0))

        def save():
            for key, (enabled, api) in vars_map.items():
                providers.setdefault(key, PROVIDERS[key].copy())
                providers[key]["enabled"] = bool(enabled.get())
                if key != "gonvl":
                    providers[key]["api_key"] = api.get().strip()
                else:
                    providers[key]["limit"] = 10
                    providers[key]["delay"] = 0.05
                    providers[key]["retry"] = 2
                    providers[key]["workers"] = 3
            save_config(self.cfg)
            win.destroy()
            self.status_var.set("Đã lưu API.")

        btns = ttk.Frame(frame, style="Root.TFrame")
        btns.grid(row=10, column=0, columnspan=4, sticky="e", pady=(18, 0))
        ttk.Button(btns, text="Lưu", command=save, style="Green.TButton").pack(side="right")
        ttk.Button(btns, text="Đóng", command=win.destroy, style="Dark.TButton").pack(side="right", padx=(0, 8))

    def get_rows(self):
        return parse_input_rows(self.input_text.get("1.0", "end"))

    def remove_duplicate_input(self):
        rows = self.get_rows()
        before = len(rows_to_email_list(rows))
        new_rows = remove_duplicate_rows_keep_blank(rows)
        after = len(rows_to_email_list(new_rows))
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", rows_to_input_text(new_rows))
        self.status_var.set(f"Xóa trùng: {before:,} → {after:,}")

    def clear_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def set_results(self, results):
        self.results = results
        self.clear_tree()
        stt = 1
        for row in results:
            if row.get("kind") != "email":
                if self.keep_blank_var.get():
                    self.tree.insert("", "end", values=("", "", "", ""), tags=("BLANK",))
                continue

            status = row.get("status", "")
            self.tree.insert(
                "",
                "end",
                values=(stt, row.get("email", ""), display_status(status), row.get("source", "")),
                tags=(status,)
            )
            stt += 1

        self.update_status_dashboard()

    def clear_all(self):
        if self.running:
            return
        self.input_text.delete("1.0", "end")
        self.results = []
        self.clear_tree()
        self.progress["value"] = 0
        self.set_percent(0, 100)
        self.update_status_dashboard()
        self.status_var.set("Đã xóa.")


    def get_turbo_workers(self):
        text = getattr(self, "speed_var", tk.StringVar(value="Nhanh x3")).get()
        if "x1" in text:
            return 1
        if "x5" in text:
            return 5
        if "x8" in text:
            return 8
        return 3

    def selected_provider_keys(self):
        mode = self.mode_var.get()
        providers = self.cfg.get("providers", {})

        enabled = []
        for key in PROVIDER_ORDER:
            p = providers.get(key, {})
            if not p.get("enabled", True):
                continue
            if key == "gonvl" or str(p.get("api_key", "")).strip():
                enabled.append(key)

        if mode == "Gonvl.pro":
            return ["gonvl"]
        if mode == "EmailScan.in":
            return ["emailscan"]
        if mode == "Checkmail.live":
            return ["checkmail_live"]
        if mode == "Chạy tất cả":
            return enabled
        return [k for k in PROVIDER_ORDER if k in enabled]

    def start_check(self):
        if self.running:
            return

        self.save_ui_config()
        self.cfg = load_config()

        rows = self.get_rows()
        emails = rows_to_email_list(rows)
        if not emails:
            messagebox.showwarning("Thiếu email", "Bạn chưa dán email.")
            return

        email_unique = unique_keep_order(emails)
        provider_keys = self.selected_provider_keys()

        if not provider_keys:
            messagebox.showwarning("Thiếu API", "Chưa bật provider hoặc thiếu API key.")
            return

        self.results = []
        self.clear_tree()
        self.running = True
        self.check_btn.configure(state="disabled")
        if hasattr(self, "retry_btn"):
            self.retry_btn.configure(state="disabled")
        self.progress["maximum"] = max(len(email_unique), 1)
        self.progress["value"] = 0
        self.set_percent(0, len(email_unique))
        speed_workers = self.get_turbo_workers()
        self.batch_label.configure(text=f"Turbo: 10 mail/lô × {speed_workers} luồng")
        self.status_var.set(f"Đang check {len(emails):,} email | Turbo {speed_workers} luồng...")

        threading.Thread(target=self.worker, args=(rows, email_unique, provider_keys, speed_workers), daemon=True).start()


    def retry_unknown(self):
        if self.running:
            return

        if not self.results:
            messagebox.showinfo("Chưa có kết quả", "Chưa có kết quả để retry.")
            return

        unknown_emails = []
        for r in self.results:
            if r.get("kind") == "email" and normalize_status(r.get("status", "")) in {"", "UNKNOW"}:
                email = str(r.get("email", "")).strip()
                if email:
                    unknown_emails.append(email)

        unknown_emails = unique_keep_order(unknown_emails)

        if not unknown_emails:
            messagebox.showinfo("Không có UNKNOWN", "Không còn mail UNKNOWN để retry.")
            return

        self.save_ui_config()
        self.cfg = load_config()
        provider_keys = self.selected_provider_keys()
        if not provider_keys:
            messagebox.showwarning("Thiếu API", "Chưa bật provider hoặc thiếu API key.")
            return

        self.running = True
        self.check_btn.configure(state="disabled")
        if hasattr(self, "retry_btn"):
            self.retry_btn.configure(state="disabled")

        self.progress["maximum"] = max(len(unknown_emails), 1)
        self.progress["value"] = 0
        self.set_percent(0, len(unknown_emails))
        speed_workers = self.get_turbo_workers()
        self.batch_label.configure(text=f"Retry UNKNOWN × {speed_workers} luồng")
        self.status_var.set(f"Đang retry {len(unknown_emails):,} UNKNOWN...")

        threading.Thread(
            target=self.retry_unknown_worker,
            args=(unknown_emails, provider_keys, speed_workers),
            daemon=True
        ).start()

    def retry_unknown_worker(self, unknown_emails, provider_keys, speed_workers):
        try:
            providers = self.cfg.get("providers", {})
            combined = {}
            sources = {}
            errors = []
            run_all = self.mode_var.get() == "Chạy tất cả"

            for key in provider_keys:
                p = dict(providers.get(key, PROVIDERS[key]))
                if key == "gonvl":
                    p["workers"] = speed_workers
                    p["limit"] = 10

                try:
                    self.progress_cb(0, len(unknown_emails), f"Retry bằng {p['name']}...")
                    result_map = check_provider(p, unknown_emails, self.progress_cb)

                    for email_key, status in result_map.items():
                        status = normalize_status(status)
                        if run_all:
                            best = choose_best_status(combined.get(email_key, "UNKNOW"), status)
                            combined[email_key] = best
                            if best == status:
                                sources[email_key] = p["name"]
                        else:
                            combined[email_key] = status
                            sources[email_key] = p["name"]

                    if not run_all:
                        break
                except Exception as e:
                    errors.append(f"{p.get('name', key)}: {e}")
                    if not run_all:
                        continue

            new_results = []
            changed = 0
            for r in self.results:
                if r.get("kind") != "email":
                    new_results.append(dict(r))
                    continue

                nr = dict(r)
                k = nr.get("email", "").lower()
                new_status = normalize_status(combined.get(k, ""))
                if new_status and new_status != "UNKNOW":
                    old_status = normalize_status(nr.get("status", "UNKNOW"))
                    best = choose_best_status(old_status, new_status)
                    if best != old_status:
                        nr["status"] = best
                        nr["source"] = sources.get(k, nr.get("source", ""))
                        changed += 1
                    elif old_status == "UNKNOW":
                        nr["status"] = new_status
                        nr["source"] = sources.get(k, nr.get("source", ""))
                new_results.append(nr)

            self.after(0, self.finish_retry_unknown, new_results, changed, len(unknown_emails), errors)
        except Exception as e:
            self.after(0, self.finish_error, str(e))

    def finish_retry_unknown(self, results, changed, total_unknown, errors):
        self.running = False
        self.check_btn.configure(state="normal")
        if hasattr(self, "retry_btn"):
            self.retry_btn.configure(state="normal")
        self.progress["value"] = self.progress["maximum"]
        self.set_percent(100, 100)
        self.set_results(results)

        msg = f"Retry xong {total_unknown:,} UNKNOWN | cập nhật {changed:,} mail"
        if errors:
            msg += f" | lỗi {len(errors)}"
        self.status_var.set(msg + "")


    def calc_percent(self, done, total):
        try:
            total = int(total)
            done = int(done)
            if total <= 0:
                return 0
            pct = int((done / total) * 100)
            return max(0, min(100, pct))
        except Exception:
            return 0

    def set_percent(self, done, total):
        pct = self.calc_percent(done, total)
        try:
            self.percent_var.set(f"{pct}%")
        except Exception:
            pass
        try:
            self.top_percent_var.set(f"{pct}%")
        except Exception:
            pass
        return pct

    def progress_cb(self, done, total, message):
        self.after(0, self._update_progress, done, total, message)

    def _update_progress(self, done, total, message):
        self.progress["maximum"] = max(total, 1)
        self.progress["value"] = min(done, total)
        pct = self.set_percent(done, total)
        if "%" not in str(message):
            message = f"{pct}% | {message}"
        self.status_var.set(message)

    def worker(self, rows, email_unique, provider_keys, speed_workers):
        try:
            providers = self.cfg.get("providers", {})
            combined = {}
            sources = {}
            errors = []
            run_all = self.mode_var.get() == "Chạy tất cả"

            for key in provider_keys:
                p = dict(providers.get(key, PROVIDERS[key]))
                if key == "gonvl":
                    p["workers"] = speed_workers
                    p["limit"] = 10
                try:
                    self.progress_cb(0, len(email_unique), f"Đang chạy {p['name']}...")
                    result_map = check_provider(p, email_unique, self.progress_cb)

                    for email_key, status in result_map.items():
                        status = normalize_status(status)
                        if run_all:
                            best = choose_best_status(combined.get(email_key, "UNKNOW"), status)
                            combined[email_key] = best
                            if best == status:
                                sources[email_key] = p["name"]
                        else:
                            combined[email_key] = status
                            sources[email_key] = p["name"]

                    if not run_all:
                        break
                except Exception as e:
                    errors.append(f"{p.get('name', key)}: {e}")
                    if not run_all:
                        continue

            if not combined and errors and "gonvl" not in provider_keys:
                raise RuntimeError("\n".join(errors))

            results = []
            for row in rows:
                if row.get("kind") != "email":
                    results.append({"kind": "blank", "email": "", "status": "", "source": ""})
                    continue

                email = row["email"]
                k = email.lower()
                results.append({
                    "kind": "email",
                    "email": email,
                    "status": normalize_status(combined.get(k, "UNKNOW")),
                    "source": sources.get(k, "")
                })

            self.after(0, self.finish_success, results, errors)
        except Exception as e:
            self.after(0, self.finish_error, str(e))

    def finish_success(self, results, errors):
        self.running = False
        self.check_btn.configure(state="normal")
        if hasattr(self, "retry_btn"):
            self.retry_btn.configure(state="normal")
        self.progress["value"] = self.progress["maximum"]
        self.set_percent(100, 100)
        self.set_results(results)

        counts = {}
        total = 0
        for r in results:
            if r.get("kind") == "email":
                total += 1
                counts[r["status"]] = counts.get(r["status"], 0) + 1

        msg = (
            f"Xong {total:,} | LIVE {counts.get('LIVE',0):,} | VERIFY {counts.get('VERIFYED',0)+counts.get('VERIFY_PHONE',0):,} "
            f"| DIS {counts.get('DISABLED',0):,} | NOT {counts.get('NOTEXISTS',0):,} | WRONG {counts.get('WRONG',0):,} | UNK {counts.get('UNKNOW',0):,}"
        )
        if errors:
            msg += f" | lỗi {len(errors)}"
        self.status_var.set(msg + "")

    def finish_error(self, error):
        self.running = False
        self.check_btn.configure(state="normal")
        if hasattr(self, "retry_btn"):
            self.retry_btn.configure(state="normal")
        self.set_percent(0, 100)
        self.status_var.set("Lỗi.")
        messagebox.showerror("Lỗi API", error)

    def copy_by_status(self, statuses):
        statuses = {normalize_status(s) for s in statuses}
        lines = []
        copied = 0

        for r in self.results:
            if r.get("kind") != "email":
                if self.keep_blank_var.get():
                    lines.append("")
                continue

            if normalize_status(r.get("status", "")) in statuses:
                lines.append(r.get("email", ""))
                copied += 1
            elif self.keep_blank_var.get():
                lines.append("")

        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.status_var.set(f"Đã copy {copied:,} mail.")

    def copy_all_results(self):
        lines = []
        stt = 1
        for r in self.results:
            if r.get("kind") != "email":
                if self.keep_blank_var.get():
                    lines.append("")
                continue
            lines.append(f"{stt}\t{r.get('email','')}\t{display_status(r.get('status',''))}\t{r.get('source','')}")
            stt += 1
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.status_var.set("Đã copy tất cả.")



    def copy_status_only(self):
        lines = []
        copied = 0

        for r in self.results:
            if r.get("kind") != "email":
                if self.keep_blank_var.get():
                    lines.append("")
                continue

            status = display_status(r.get("status", ""))
            if status:
                lines.append(status)
                copied += 1
            elif self.keep_blank_var.get():
                lines.append("")

        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.status_var.set(f"Đã copy {copied:,} status.")

    def copy_selected_status(self):
        selected = self.tree.selection()
        statuses = []

        for item_id in selected:
            values = self.tree.item(item_id, "values")
            if len(values) >= 3:
                status = display_status(values[2])
                if status:
                    statuses.append(status)

        self.clipboard_clear()
        self.clipboard_append("\n".join(statuses))
        self.status_var.set(f"Đã copy {len(statuses):,} status đang chọn.")

    def copy_selected_emails(self):
        selected = self.tree.selection()
        emails = []

        for item_id in selected:
            values = self.tree.item(item_id, "values")
            if len(values) >= 2:
                email = str(values[1]).strip()
                if email:
                    emails.append(email)

        self.clipboard_clear()
        self.clipboard_append("\n".join(emails))
        self.status_var.set(f"Đã copy {len(emails):,} mail đang chọn.")

    def export_txt(self):
        if not self.results:
            messagebox.showinfo("Chưa có kết quả", "Chưa có kết quả để xuất.")
            return
        path = filedialog.asksaveasfilename(title="Lưu kết quả", defaultextension=".txt", filetypes=[("Text file", "*.txt")])
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            stt = 1
            for r in self.results:
                if r.get("kind") != "email":
                    if self.keep_blank_var.get():
                        f.write("\n")
                    continue
                f.write(f"{stt}\t{r.get('email','')}\t{display_status(r.get('status',''))}\t{r.get('source','')}\n")
                stt += 1
        self.status_var.set("Đã xuất TXT.")


if __name__ == "__main__":
    app = App()
    app.mainloop()
