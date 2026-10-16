# app/storage.py
# Persistence layer for campaign days — one JSON file per campaign day in data/.

import copy
import json
import logging
import os
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from datetime import date, datetime

ROOT = Path(__file__).resolve().parents[1]

logger = logging.getLogger(__name__)

# --- Channel infrastructure --------------------------------------------------
# Each channel maps to a base directory; all per-channel subfolders (data,
# config, macros, sql_templates, etc.) live under it.
CHANNELS = ("push", "rcs")
_DEFAULT_CHANNEL = "push"

_CHANNEL_BASES = {
    "push": ROOT / "push",
    "rcs": ROOT / "rcs",
}

# Thread-local because Streamlit runs every browser session on its own thread in one shared process.
_local = threading.local()

# Rotating pre-overwrite backups per campaign, and soft-delete trash.
BACKUP_RETENTION = 20


def set_active_channel(channel: str) -> None:
    if channel in CHANNELS:
        _local.channel = channel


def get_active_channel() -> str:
    return getattr(_local, "channel", _DEFAULT_CHANNEL)


def channel_dir(subfolder: str) -> Path:
    return _CHANNEL_BASES[get_active_channel()] / subfolder


def _data_dir() -> Path:
    return channel_dir("data")


STATUSES = ["Draft", "Pending Assets", "In Progress", "Ready", "Submitted", "Exported", "Campaign Launched"]


def _ensure_data_dir():
    _data_dir().mkdir(parents=True, exist_ok=True)


def _trash_dir() -> Path:
    d = _data_dir() / "_trash"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _backup_dir(campaign_id: str) -> Path:
    d = _data_dir() / "_backups" / campaign_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _prune_backups(campaign_id: str, keep: int | None = None) -> None:
    if keep is None:
        keep = BACKUP_RETENTION
    d = _data_dir() / "_backups" / campaign_id
    if not d.exists():
        return
    files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError as exc:
            logger.warning("failed to prune backup %s: %s", old, exc)


def _campaign_path(campaign_id: str) -> Path:
    return _data_dir() / f"{campaign_id}.json"


def new_campaign_id() -> str:
    """Generate a short unique ID for a new campaign day."""
    return uuid.uuid4().hex[:12]


CAMPAIGN_SCHEMA_VERSION = 1


def migrate_campaign(campaign: dict) -> dict:
    """Normalize an on-disk campaign dict to the current schema (idempotent).

    Centralizes the backfills that previously ran only in ui._load_into_session,
    so every entry point (tests, direct SQL build, analytics) sees the same shape.
    Mutates and returns ``campaign``.
    """
    if not campaign:
        return campaign
    campaign.setdefault("schema_version", CAMPAIGN_SCHEMA_VERSION)
    for r in campaign.get("rows", []) or []:
        if not isinstance(r, dict):
            continue
        if "_row_id" not in r:
            r["_row_id"] = uuid.uuid4().hex[:8]
        for sr in r.get("sub_rows", []) or []:
            if isinstance(sr, dict) and "_row_id" not in sr:
                sr["_row_id"] = uuid.uuid4().hex[:8]
    return campaign


def save_campaign(campaign: dict) -> None:
    """Persist a campaign day dict to disk. Keeps a rotating pre-overwrite backup under data/_backups/<id>/."""
    _ensure_data_dir()
    cid = campaign["id"]
    p = _campaign_path(cid)
    if p.exists():
        try:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            (_backup_dir(cid) / f"{stamp}.json").write_bytes(p.read_bytes())
            _prune_backups(cid)
        except OSError as exc:
            # a backup failure must never block the save
            logger.warning("backup for campaign %s failed: %s", cid, exc)
    campaign["updated_at"] = datetime.now().isoformat()
    _atomic_write_text(p, json.dumps(campaign, indent=2, default=str))


def _atomic_write_text(path: Path, text: str, attempts: int = 5) -> None:
    """Write via temp file + os.replace so a crash never leaves a truncated JSON behind."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        for i in range(attempts):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                # Windows: target briefly locked by a concurrent reader or AV scanner
                if i == attempts - 1:
                    raise
                time.sleep(0.05 * (i + 1))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_campaign(campaign_id: str) -> dict | None:
    """Load a single campaign day by ID. Returns None if not found."""
    p = _campaign_path(campaign_id)
    if not p.exists():
        return None
    return migrate_campaign(copy.deepcopy(_read_json_cached(str(p), p.stat().st_mtime_ns)))


def list_campaigns() -> list[dict]:
    """Return all saved campaign days sorted by send_date descending.

    Uses a per-path (path, mtime_ns) cache so unchanged files are not reparsed on
    every Streamlit rerun. Returns deep copies so callers can mutate freely.
    """
    _ensure_data_dir()
    campaigns = []
    for p in _data_dir().glob("*.json"):
        try:
            data = _read_json_cached(str(p), p.stat().st_mtime_ns)
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            logger.warning("skipping unreadable campaign file %s: %s", p, exc)
            continue
        campaigns.append(migrate_campaign(copy.deepcopy(data)))
    campaigns.sort(key=lambda c: c.get("send_date", ""), reverse=True)
    return campaigns


_CAMPAIGN_READ_CACHE: dict[tuple[str, int], dict] = {}
_CAMPAIGN_READ_CACHE_MAX = 512


def _read_json_cached(path_str: str, mtime_ns: int) -> dict:
    """Parse a JSON file once per (path, mtime_ns). Shared across sessions."""
    key = (path_str, mtime_ns)
    cached = _CAMPAIGN_READ_CACHE.get(key)
    if cached is not None:
        return cached
    data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    # Evict older entries for this same path so the cache does not grow unbounded.
    for k in [k for k in _CAMPAIGN_READ_CACHE if k[0] == path_str and k != key]:
        _CAMPAIGN_READ_CACHE.pop(k, None)
    if len(_CAMPAIGN_READ_CACHE) >= _CAMPAIGN_READ_CACHE_MAX:
        # Drop an arbitrary entry; FIFO-ish is fine at this scale.
        _CAMPAIGN_READ_CACHE.pop(next(iter(_CAMPAIGN_READ_CACHE)), None)
    _CAMPAIGN_READ_CACHE[key] = data
    return data


def delete_campaign(campaign_id: str) -> bool:
    """Soft-delete: move the campaign JSON to data/_trash/ instead of unlinking.

    Restore by copying `_trash/<id>_<timestamp>.json` back to `data/<id>.json`.
    """
    p = _campaign_path(campaign_id)
    if not p.exists():
        return False
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = _trash_dir() / f"{campaign_id}_{stamp}.json"
    try:
        p.rename(dest)
    except OSError:
        # cross-volume rename or transient lock — fall back to copy + unlink
        shutil.copy2(p, dest)
        p.unlink()
    return True


def create_campaign(wk_id: str = "", send_date: str = "", send_day: str = "") -> dict:
    """Create a fresh campaign day dict with defaults."""
    cid = new_campaign_id()
    now = datetime.now().isoformat()
    return {
        "id": cid,
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "wk_id": wk_id,
        "send_date": send_date or str(date.today()),
        "send_day": send_day,
        "status": "Draft",
        "rows": [],
        "audit": [],
        "status_history": [{"status": "Draft", "ts": now}],
        "activity_log": [{"action": "Created", "ts": now}],
        "targeting_notes": "",
        "created_at": now,
        "updated_at": now,
    }


def duplicate_campaign(source_id: str) -> dict | None:
    """Clone an existing campaign day into a new one (Draft status, new ID)."""
    source = load_campaign(source_id)
    if not source:
        return None
    cid = new_campaign_id()
    now = datetime.now().isoformat()
    clone = copy.deepcopy(source)
    clone["id"] = cid
    clone["status"] = "Draft"
    clone["audit"] = []
    clone["status_history"] = [{"status": "Draft", "ts": now}]
    clone["activity_log"] = [{"action": "Created (cloned)", "ts": now}]
    clone["created_at"] = now
    clone["updated_at"] = now
    save_campaign(clone)
    return clone
