# app/ui.py
# Streamlit app: dashboard of campaign days + detail editor.
# Two-view single-page layout: Dashboard ↔ Campaign Detail.

import streamlit as st
import pandas as pd
import yaml, sys, os
from pathlib import Path
from datetime import date, datetime
from zoneinfo import ZoneInfo as _ZoneInfo

# Ensure app/ is on the import path when run from project root
sys.path.insert(0, os.path.dirname(__file__))

import copy as _copy
import re as _re
import json as _json
import hashlib as _hashlib
import uuid as _uuid
import time as _time
import textwrap as _textwrap
from functools import lru_cache


_PACE_GLOBAL_CSS_PATH = Path(__file__).parent / "static" / "pace_global.html"


@st.cache_resource
def _load_pace_global_css() -> str:
    """Return the global CSS/JS block injected once per app load.

    Lives in app/static/pace_global.html so editors syntax-highlight it and we
    stop carrying ~620 lines of CSS inside main().
    """
    try:
        # utf-8-sig strips a BOM; an indented or BOM-prefixed block renders as a Markdown code block.
        raw = _PACE_GLOBAL_CSS_PATH.read_text(encoding="utf-8-sig")
        return _textwrap.dedent(raw).strip()
    except OSError:
        return ""

def _new_row_id() -> str:
    """Return a short unique ID for a new row (stable across sorts/reorders)."""
    return _uuid.uuid4().hex[:8]


# ── Handling Time Tracking ─────────────────────────────────
_HT_MAX_IDLE = 300  # 5 minutes — cap between interactions
import math as _math


def _round_handling_time_total(hours: float) -> float:
    """Round a campaign-day *total* handling-time UP to the nearest 0.25 hrs (15 min).

    Applied only to the summed total across all rows in a campaign day,
    NOT to individual per-row values.  Minimum is 0.25 hrs (15 min)
    whenever the raw total is > 0.
    """
    if hours <= 0:
        return 0.0
    return max(0.25, _math.ceil(hours * 4) / 4)


def _format_handling_time(hours: float) -> str:
    """Format raw per-row handling-time as '0.12 hrs (7 min)'."""
    total_min = round(hours * 60)
    return f"{hours:.2f} hrs ({total_min} min)"


def _accumulate_handling_time():
    """Attribute elapsed time to the last-active row.

    Called at the top of render_detail() on every rerun.  Compares
    the current wall-clock to the previously recorded timestamp and
    adds the delta (capped at _HT_MAX_IDLE seconds) to the active
    row's ``handling_time`` field.

    Skipped entirely when the campaign status is "Campaign Launched".
    """
    now = _time.time()
    # Do not accumulate time for launched campaigns
    if st.session_state.get("campaign_status") == "Campaign Launched":
        st.session_state["_ht_last_time"] = now
        return
    prev = st.session_state.get("_ht_last_time")
    active_rid = st.session_state.get("_ht_active_rid")
    if prev is not None and active_rid is not None:
        elapsed = now - prev
        if 0 < elapsed < _HT_MAX_IDLE:
            for r in st.session_state.get("rows", []):
                if r.get("_row_id") == active_rid:
                    r["handling_time"] = r.get("handling_time", 0.0) + (elapsed / 3600)
                    break
    st.session_state["_ht_last_time"] = now


def _mark_row_active(rid: str):
    """Set *rid* as the currently-active row for time tracking."""
    st.session_state["_ht_active_rid"] = rid

def _get_active_session_count() -> int | None:
    """Return the number of active Streamlit sessions, or None if unavailable."""
    try:
        from streamlit.runtime import get_instance
        runtime = get_instance()
        return len(runtime._session_mgr.list_active_sessions())
    except Exception:
        return None
from renderer import create_jinja_env, create_permissive_env
from compose import render_campaign_insert, _escape_sql_strings, _expand_offer_ids, _expand_extra_themes, _load_offer_type_template, _override_canonicalcampaignid
from storage import (
    list_campaigns, load_campaign, save_campaign,
    channel_dir, set_active_channel,
)

# =============== Config ==================
ROOT = Path(__file__).resolve().parents[1]

# users.yaml is the ONLY config file shared across all channels — dev passphrase auth.
SHARED_USERS_YAML = ROOT / "config" / "users.yaml"

# Per-channel path helpers — resolve via storage.channel_dir at call time.
# Every subfolder lives under push/ or rcs/ per storage._CHANNEL_BASES.
def _config_dir() -> Path:            return channel_dir("config")
def _out_dir() -> Path:               return channel_dir("exports")
def _sql_templates_dir() -> Path:     return channel_dir("sql_templates")
def _csv_dir() -> Path:               return channel_dir("exports")
def _sql_exports_dir() -> Path:       return channel_dir("sql_exports")
def _offer_types_dir() -> Path:       return channel_dir("macros") / "offer_types"


# Per-channel offer types shown in row-form dropdowns.
_OFFER_TYPES_BY_CHANNEL = {
    "push": ["", "PERSONALIZED DEAL", "STORE COUPON", "PUSHSECTION"],
    "rcs":  ["", "CHOICE", "CARD", "CAROUSEL"],
}

# Per-channel export filename prefixes (SQL + CSV grid).
_EXPORT_PREFIX_BY_CHANNEL = {"push": "PUSH", "rcs": "RCS"}


def _current_channel() -> str:
    """Read the active channel from Streamlit session state; defaults to 'push'."""
    return st.session_state.get("channel") or "push"


def _channel_offer_types() -> list[str]:
    return _OFFER_TYPES_BY_CHANNEL.get(_current_channel(), _OFFER_TYPES_BY_CHANNEL["push"])


def _channel_export_prefix() -> str:
    return _EXPORT_PREFIX_BY_CHANNEL.get(_current_channel(), "PUSH")


def _offer_field_name() -> str:
    """Row-dict key for the offer-type value (PUSH: offer_type, RCS: channelsubtype)."""
    return "channelsubtype" if _current_channel() == "rcs" else "offer_type"


def _offer_field_label() -> str:
    """Human-facing dropdown label (RCS matches the SQL column name)."""
    return "CHANNEL_SUB_TYPE" if _current_channel() == "rcs" else "Offer Type"


def _row_offer_value(row: dict) -> str:
    """Read a row's offer-type value, falling back to the legacy key if needed."""
    return (row.get(_offer_field_name()) or row.get("offer_type") or row.get("channelsubtype") or "")


def _offer_template_fingerprint() -> str:
    """Return a hash of all offer-type template files so we can detect on-disk changes."""
    h = _hashlib.sha256()
    for p in sorted(_offer_types_dir().glob("*.sql.j2")):
        h.update(p.name.encode())
        h.update(str(p.stat().st_mtime_ns).encode())
    return h.hexdigest()[:16]


def _invalidate_sql_on_template_change():
    """Clear cached generated_sql if offer-type templates changed since last generation."""
    fp = _offer_template_fingerprint()
    if st.session_state.get("_offer_tpl_fp") and st.session_state["_offer_tpl_fp"] != fp:
        st.session_state.pop("generated_sql", None)
        _load_offer_type_template.cache_clear()
    st.session_state["_offer_tpl_fp"] = fp

# Status colors for the dashboard (matches Monday.com feel)
STATUS_COLORS = {
    "Draft": "#787878",       # grey
    "Pending Assets": "#e2445c",  # red
    "In Progress": "#fdab3d", # orange
    "Ready": "#00c875",       # green
    "Submitted": "#579bfc",   # blue
    "Exported": "#a25ddc",    # purple
    "Campaign Launched": "#037f4c",  # dark green
}

@st.cache_resource
def jinja_env():
    return create_jinja_env()

def load_tables(send_day: str = ""):
    """Load table paths from config/tables.yaml.

    If *send_day* is provided (e.g. ``SATURDAY``), the 3-letter uppercase
    abbreviation is appended to ``push_allocation``, ``push_allocation_final``,
    ``push_priority``, and ``push_priority_full``
    (e.g. ``…PUSH_Allocation_SAT``, ``…push_priority_SAT``).
    """
    try:
        with open(_config_dir() / "tables.yaml", "r") as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        st.error("config/tables.yaml not found. See the Configuration Reference in push/docs/user-manual.md.")
        st.stop()
    ds = cfg.get("datasets", {}).get(cfg.get("env", "prod"), {})
    required_keys = (
        "push_allocation", "push_priority", "push_priority_full",
        "push_allocation_final", "push_allocation_final_archive",
        "eligible_push_audience", "redemption_events",
    )
    missing = [k for k in required_keys if k not in ds]
    if missing:
        st.error(f"Missing keys in tables.yaml: {missing}. See Section 6.")
        st.stop()
    # Append day-of-week suffix to allocation and priority tables
    if send_day:
        suffix = f"_{send_day[:3].upper()}"
        ds = dict(ds)  # avoid mutating cached YAML
        ds["push_allocation"] = ds["push_allocation"] + suffix
        ds["push_allocation_final"] = ds["push_allocation_final"] + suffix
        ds["push_priority"] = ds["push_priority"] + suffix
        ds["push_priority_full"] = ds["push_priority_full"] + suffix
    return ds


def _load_rcs_tables_cfg() -> dict:
    """Load rcs/config/tables.yaml as a full dict (with 'tables' + 'runtime' keys).
    Raises st.error + st.stop if missing so the caller never sees an empty dict.
    """
    try:
        with open(_config_dir() / "tables.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        st.error("rcs/config/tables.yaml not found.")
        st.stop()

# =============== Column Definitions ==================
REQUIRED_COLUMNS = [
    "campaign_name", "title", "message",
]
# Theme is required but rendered in its own section (Theme Variants)
THEME_FIELD = "theme"
def _load_optional_columns_cfg() -> list:
    """Load optional_columns.yaml. Returns list of column defs.

    Silently returns [] if the file doesn't exist yet — happens transiently on
    channel switch and for RCS before its config is authored in Phase 3.
    """
    _cfg = _config_dir() / "optional_columns.yaml"
    if not _cfg.exists():
        return []
    try:
        mtime_ns = _cfg.stat().st_mtime_ns
    except OSError:
        return []
    return list(_optional_columns_from(str(_cfg), mtime_ns))


@lru_cache(maxsize=8)
def _optional_columns_from(path_str: str, mtime_ns: int) -> tuple:
    """Parse optional_columns.yaml once per (path, mtime). Returns a tuple so lru_cache can hash it."""
    import yaml as _yaml_oc
    with open(path_str, "r", encoding="utf-8") as _f:
        _data = _yaml_oc.safe_load(_f) or {}
    return tuple(_data.get("optional_columns", []) or [])


# Back-compat for callers that previously did ``_load_optional_columns_cfg.cache_clear()``.
_load_optional_columns_cfg.cache_clear = _optional_columns_from.cache_clear  # type: ignore[attr-defined]


def _optional_columns() -> list:
    """Names of optional columns visible in the UI for the currently active channel."""
    return [c["name"] for c in _load_optional_columns_cfg() if c.get("ui_visible", True)]


def _all_columns() -> list:
    """All row-dict column names for the currently active channel."""
    return REQUIRED_COLUMNS + [THEME_FIELD] + _optional_columns() + JOIN_COLUMNS + TARGETING_COLUMNS


TARGETING_COLUMNS = [
    "division_ids", "division_mode",
    "banners", "banner_mode",
    "store_ids", "store_mode",
]
JOIN_COLUMNS = ["offer_type", "offer_id"]

# CRF Converter — fixed mapping from CRF sheet headers (as received) → PACE row field names.
# Header lookup is case-insensitive and whitespace-insensitive; see _crf_normalize_header().
_CRF_COLUMN_MAP: dict[str, str] = {
    "campaign name":       "campaign_name",
    "theme name":          "theme",
    "priority":            "priority",
    "row type":            "row_type",
    "type":                "offer_type",
    "offer id":            "offer_id",
    "store id":            "store_ids",
    "push section":        "pushsection",
    "targeting":           "targeting_notes",
    "rich push image url": "media_url",
    "rich push image":     "media_url",
    "title/headline":      "title",
    "copy/message":        "message",
    "notes":               "CANONICALCAMPAIGNID",
}
# CRF headers intentionally dropped during conversion.
_CRF_IGNORE_COLS: set[str] = {"date", "day", "monday"}
# Placeholder detection — a cell (in title/message/media_url/pushsection) is treated as
# a "theme-name placeholder" when its trimmed value matches a canonical PACE theme string
# (contains "pn_wkNN_YYYY_Day" and no whitespace).
_CRF_PLACEHOLDER_RE = _re.compile(r"^\S*pn_wk\d{1,2}_\d{4}_[A-Za-z]+$", _re.IGNORECASE)
# Canonical offer-ID format (e.g. "71980463-D"): digits, dash, single letter. Sentences/notes are ignored.
_CRF_OFFER_ID_RE = _re.compile(r"^\d+-[A-Za-z]$")
# CRF Type values that mean "Rich Push" rather than a real PACE offer_type.
_CRF_RICH_PUSH_TYPE_VALUES: set[str] = {"rich push", "rich push image", "richpush", "rich-push"}
# Valid PACE offer_type values. CRF Type cells that don't match one of these
# (e.g. "Push", "SMS") are blanked so downstream pushsection promotion can fire.
_CRF_VALID_OFFER_TYPES: set[str] = {"personalized deal", "store coupon", "pushsection"}
# Fields excluded from CRF Push Section deep-link forwarding — media_url and pushsection are
# handled by the main classifier; the rest are hidden schema-managed fields.
_CRF_EXTRAS_EXCLUDE: set[str] = {"media_url", "pushsection", "media_type", "pushlinks", "update_dt"}
# Straight + smart quote characters commonly wrapping CRF cell values that must be stripped on import.
_CRF_QUOTE_CHARS: str = "\"'\u201c\u201d\u2018\u2019\u201e\u201f\u2033\u2036\u00ab\u00bb"


def _crf_clean_cell(v: str) -> str:
    """Strip whitespace and any surrounding straight/smart quotation marks.

    Only strips an outer quote when BOTH ends carry one so we never eat a lone
    trailing `"` that belongs to an inner value like `screentitle="Hatch_Chiles"`.
    Repeats until stable so nested wrappings like `" "hello" "` collapse cleanly.
    """
    if not v:
        return v
    prev = None
    while prev != v:
        prev = v
        v = v.strip()
        if len(v) >= 2 and v[0] in _CRF_QUOTE_CHARS and v[-1] in _CRF_QUOTE_CHARS:
            v = v[1:-1].strip()
    return v


def _get_crf_deep_link_extras() -> tuple[str, ...]:
    # Read YAML fresh so columns added via the schema editor take effect without app restart.
    return tuple(
        c["name"] for c in _load_optional_columns_cfg()
        if c.get("name") and c["name"] not in _CRF_EXTRAS_EXCLUDE and c.get("ui_visible", True)
    )


def _crf_sanitize_offer_id(val: str) -> tuple[str, str]:
    """Keep only tokens matching NNN-X; return (cleaned_csv, dropped_csv)."""
    v = (val or "").strip()
    if not v:
        return "", ""
    tokens = [t.strip() for t in v.split(",") if t.strip()]
    kept = [t.upper() for t in tokens if _CRF_OFFER_ID_RE.match(t)]
    dropped = [t for t in tokens if not _CRF_OFFER_ID_RE.match(t)]
    return ", ".join(kept), ", ".join(dropped)


def _parse_key_value_block(text: str) -> tuple[dict[str, str], list[str]]:
    """Tolerant `key=value` block parser shared by the CRF converter and the in-form paste widgets.

    Handles multi-line pastes and flattened variants: semicolon/pipe/tab/NBSP/comma
    separators and single-line "soft-wrap" pastes where entries are separated only by
    plain spaces before the next `word=` token. Values wrapped in straight or smart
    quotes are unwrapped. Returns ``(parsed_fields, unrecognised_key_names)``.
    """
    v = str(text or "").strip()
    if not v or "=" not in v:
        return {}, []
    normalized = _re.sub(r"[;|]+", "\n", v)
    normalized = _re.sub(r"[ \t\u00a0]+(?=\S*=)", "\n", normalized)
    parsed: dict[str, str] = {}
    unknown: list[str] = []
    _aliases = _get_paste_field_aliases()
    for line in normalized.splitlines():
        line = line.strip().strip(",").strip()
        if not line or "=" not in line:
            continue
        k, _, rest = line.partition("=")
        # Normalise so "Screen Title", "screen_title", "SCREEN-TITLE" all match "screentitle".
        k_norm = "".join(c for c in k.strip().lower() if c.isalnum())
        rest = rest.strip().strip(",").strip()
        if len(rest) >= 2 and rest[0] in _CRF_QUOTE_CHARS and rest[-1] in _CRF_QUOTE_CHARS:
            rest = rest[1:-1].strip()
        elif rest and (rest[0] in _CRF_QUOTE_CHARS or rest[-1] in _CRF_QUOTE_CHARS):
            rest = rest.strip(_CRF_QUOTE_CHARS).strip()
        if not rest:
            continue
        if k_norm in _aliases:
            parsed[_aliases[k_norm]] = rest
        elif k_norm:
            unknown.append(k.strip())
    return parsed, unknown


def _crf_expand_pushsection_cell(val: str) -> tuple[dict[str, str], list[str]]:
    """Parse a CRF Push Section cell using the shared key=value parser.

    If no recognised entries are found, treat the whole cell as a plain ``pushsection``
    value (CRF-specific fallback — the in-form paste widget instead shows a warning).
    """
    v = str(val or "").strip()
    if not v:
        return {}, []
    if "=" not in v:
        return {"pushsection": v}, []
    parsed, unknown = _parse_key_value_block(v)
    return (parsed, unknown) if parsed else ({"pushsection": v}, unknown)

# Legacy short-form aliases that don't appear in optional_columns.yaml as field names
# but are common in deep-link source files.
_MANUAL_PASTE_ALIASES: dict[str, str] = {
    "q":          "param_q",
    "productid":  "product",
    "categoryid": "category",
}


def _get_paste_field_map() -> dict[str, str]:
    # Read YAML fresh so columns added via the schema editor take effect without app restart.
    m = {c["name"]: c["name"] for c in _load_optional_columns_cfg() if c.get("name")}
    m.update(_MANUAL_PASTE_ALIASES)
    return m


def _get_paste_field_aliases() -> dict[str, str]:
    # Accepts "Screen Title", "screen_title", "SCREEN-TITLE", "screenTitle", etc.
    return {
        "".join(c for c in k.lower() if c.isalnum()): v
        for k, v in _get_paste_field_map().items()
    }

def _derive_send_day(send_date_str: str) -> str:
    try:
        return datetime.strptime(send_date_str, "%Y-%m-%d").strftime("%A").upper()
    except (ValueError, TypeError):
        return ""

ROLES = {"User": "user", "Developer": "developer"}

_APOSTROPHE_RE = _re.compile(r"[\u2018\u2019']")
_BANNER_PLACEHOLDER_RE = _re.compile(r"\[banner\]", _re.IGNORECASE)
_MULTI_SPACE_RE = _re.compile(r" {2,}")
_SPACE_BEFORE_PUNCT_RE = _re.compile(r" +(?=[.,!?;:])")

def _check_content_warnings(rows: list) -> list[str]:
    """Return advisory warnings when title/message contain apostrophes, [Banner], or extra whitespace."""
    warnings: list[str] = []
    for i, r in enumerate(rows):
        vlabel = r.get("_vlabel", f"Row {i+1}")
        label = r.get("campaign_name") or "(empty)"
        is_sql = bool(r.get("custom_sql"))
        field_issues: list[str] = []
        for field in ("title", "message"):
            val = r.get(field) or ""
            if not val:
                continue
            issues: list[str] = []
            if val != val.strip():
                issues.append(
                    "has leading or trailing spaces — remove them before submitting"
                )
            if _MULTI_SPACE_RE.search(val):
                issues.append(
                    "has consecutive extra spaces inside the text — clean them up before submitting"
                )
            if _SPACE_BEFORE_PUNCT_RE.search(val):
                issues.append(
                    "has a space before punctuation (e.g. ` .` instead of `.`) — remove the extra space"
                )
            val_stripped = val.strip()
            if _APOSTROPHE_RE.search(val_stripped):
                if is_sql:
                    issues.append(
                        "Apostrophe (`'`) detected — verify the SQL template escapes it "
                        "with `replace(\"'\", \"\\'\")` or use `\\` manually. "
                        "Form rows handle this automatically; SQL template rows may not."
                    )
            if _BANNER_PLACEHOLDER_RE.search(val_stripped):
                issues.append(
                    "contains '[Banner]' — looks like an unreplaced placeholder "
                    "— replace it with `|| marketing_banner ||` in the SQL template and remove the placeholder from the title/message"
                )
            for issue in issues:
                field_issues.append(f"  - **{field}**: {issue}")
        if field_issues:
            warnings.append(
                f"{vlabel} — **{label}**:\n" + "\n".join(field_issues)
            )
    return warnings

def _check_param_q_warnings(rows: list) -> list[str]:
    """Return advisory warnings when param_q contains underscores or screentitle contains dashes."""
    warnings: list[str] = []
    for i, r in enumerate(rows):
        vlabel = r.get("_vlabel", f"Row {i+1}")
        label = r.get("campaign_name") or "(empty)"
        pq = (r.get("param_q") or "").strip()
        if pq and "_" in pq:
            warnings.append(
                f"{vlabel} — **{label}**: `param_q` contains underscore (`_`) — "
                f"this field should not have underscores."
            )
        st_val = (r.get("screentitle") or "").strip()
        if st_val and "-" in st_val:
            warnings.append(
                f"{vlabel} — **{label}**: `screentitle` contains dash (`-`) — "
                f"this field should not have dashes."
            )
    return warnings

# Day-name abbreviation mapping for theme mismatch checks
_DAY_ABBREVS = {
    "MONDAY": ["mon", "monday"],
    "TUESDAY": ["tue", "tuesday"],
    "WEDNESDAY": ["wed", "wednesday"],
    "THURSDAY": ["thu", "thursday"],
    "FRIDAY": ["fri", "friday"],
    "SATURDAY": ["sat", "saturday"],
    "SUNDAY": ["sun", "sunday"],
}

# Regex to extract the pn_wkNN_YYYY_Day tracking token from a theme string
# e.g. "ecom-plat_wk28-Generic-V2-pn_wk28_2026_Wed" → groups: ("28", "2026", "Wed")
_PN_TOKEN_RE = _re.compile(r"pn_wk(\d{1,2})_(\d{4})_([A-Za-z]+)", _re.IGNORECASE)

# New PUSH theme convention: theme must end with "_YYYY-MM-DD" matching Send Date
# e.g. "loy-fs-offer-recur_Free_Solo_2026-09-18"
_SEND_DATE_SUFFIX_RE = _re.compile(r"_(\d{4}-\d{2}-\d{2})$")


def _check_theme_send_date_suffix(rows: list, send_date: str) -> list[str]:
    """Warn when a PUSH row's theme is missing or has a wrong `_YYYY-MM-DD` suffix.

    The current PUSH theme format is `ThemeName_YYYY-MM-DD` (e.g.
    `loy-fs-offer-recur_Free_Solo_2026-09-18`). The trailing date must
    match the campaign's Send Date exactly.
    """
    warnings: list[str] = []
    expected = (send_date or "").strip()
    if not expected:
        return warnings
    for i, r in enumerate(rows):
        theme = (r.get("theme") or "").strip()
        if not theme:
            continue
        vlabel = r.get("_vlabel", f"Row {i+1}")
        label = r.get("campaign_name") or "(empty)"
        m = _SEND_DATE_SUFFIX_RE.search(theme)
        if not m:
            warnings.append(
                f"{vlabel} — **{label}** (theme: `{theme}`): "
                f"theme is missing the `_YYYY-MM-DD` send-date suffix — "
                f"expected suffix `_{expected}` (e.g. `ThemeName_{expected}`)"
            )
            continue
        found = m.group(1)
        if found != expected:
            warnings.append(
                f"{vlabel} — **{label}** (theme: `{theme}`): "
                f"theme send-date suffix is **_{found}** but campaign Send Date is **{expected}** "
                f"— possible copy-paste from a different day"
            )
    return warnings


def _check_theme_mismatch(rows: list, wk_id: str, send_day: str) -> list[str]:
    """Warn when a row's theme has a wrong or missing pn_wkNN_YYYY_Day tracking token.

    Checks are scoped exclusively to the pn_wk<wk>_<year>_<day> segment —
    other numeric or day strings elsewhere in the theme are ignored.
    """
    warnings: list[str] = []
    wk_id_raw = (wk_id or "").strip()
    send_day_upper = (send_day or "").strip().upper()
    # Expected values derived from campaign header fields
    expected_wk_num = wk_id_raw[-2:].lstrip("0") if len(wk_id_raw) >= 2 else ""
    expected_year = wk_id_raw[:4] if len(wk_id_raw) >= 4 and wk_id_raw[:4].isdigit() else ""
    day_tokens = _DAY_ABBREVS.get(send_day_upper, [])  # e.g. ["wed", "wednesday"]
    if not expected_wk_num and not expected_year and not day_tokens:
        return warnings
    for i, r in enumerate(rows):
        theme = (r.get("theme") or "").strip()
        if not theme:
            continue
        vlabel = r.get("_vlabel", f"Row {i+1}")
        label = r.get("campaign_name") or "(empty)"
        issues: list[str] = []
        m = _PN_TOKEN_RE.search(theme)
        if not m:
            issues.append(
                f"theme is missing the `pn_wkNN_YYYY_Day` tracking token "
                f"— expected something like `pn_wk{expected_wk_num}_{expected_year}_{send_day_upper.capitalize()}`"
            )
        else:
            found_wk = m.group(1).lstrip("0")  # strip leading zeros for comparison
            found_year = m.group(2)
            found_day = m.group(3).lower()
            if expected_wk_num and found_wk != expected_wk_num:
                issues.append(
                    f"`pn_wk` token shows week **{found_wk}** but campaign Week ID is **{wk_id_raw}** "
                    f"(expected wk{expected_wk_num}) — possible copy-paste from a different week"
                )
            if expected_year and found_year != expected_year:
                issues.append(
                    f"`pn_wk` token contains year **{found_year}** but campaign year is **{expected_year}** "
                    f"— possible copy-paste from a prior year"
                )
            if day_tokens and found_day not in day_tokens:
                display_day = send_day_upper.capitalize()
                abbrev = day_tokens[0].capitalize()
                issues.append(
                    f"`pn_wk` token shows day **{m.group(3)}** but campaign send day is **{display_day}** "
                    f"(expected `{abbrev}`) — verify the day is correct"
                )
        if issues:
            warnings.append(
                f"{vlabel} — **{label}** (theme: `{theme}`):\n"
                + "\n".join(f"  - {iss}" for iss in issues)
            )
    return warnings


def _load_dev_passphrase_hash() -> str:
    """Read the SHA-256 developer passphrase hash (env var override, else config/users.yaml)."""
    env_hash = os.environ.get("PACE_DEV_PASSPHRASE_SHA256", "").strip()
    if env_hash:
        return env_hash.lower()
    users_path = SHARED_USERS_YAML
    try:
        import yaml
        with open(users_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return str(data.get("developer_passphrase_sha256", "")).strip()
    except Exception:
        return ""

# Set True to re-enable the landing page and PUSH/RCS channel switcher.
_RCS_ENABLED = False


def init_state():
    st.session_state.setdefault("channel", None)  # None = show landing; "push" or "rcs" = enter channel
    st.session_state.setdefault("view", "landing")  # "landing", "dashboard", "detail", "analytics", "script_editor", "crf_converter"
    st.session_state.setdefault("active_campaign_id", None)
    st.session_state.setdefault("role", "user")
    st.session_state.setdefault("dev_unlocked", False)
    if not _RCS_ENABLED:
        st.session_state.channel = "push"
        if st.session_state.view == "landing":
            st.session_state.view = "dashboard"
    # Sync storage's active channel with session state so path helpers resolve correctly.
    if st.session_state.get("channel"):
        set_active_channel(st.session_state["channel"])


def _is_developer() -> bool:
    return st.session_state.get("role") == "developer"

# Statuses where Users cannot modify the campaign (read-only until a Developer unlocks)
_LOCKED_FOR_USER = {"Submitted", "Exported", "Campaign Launched"}

def _is_user_locked() -> bool:
    """True when the current user is in User role and the campaign is in a post-submit status."""
    if _is_developer():
        return False
    return st.session_state.get("campaign_status", "Draft") in _LOCKED_FOR_USER

def _btn_color(color: str):
    """Inject an invisible CSS marker before the next st.button to color it."""
    st.markdown(f'<span class="btn-{color}"></span>', unsafe_allow_html=True)

def _clear_row_widget_state():
    """Schedule widget state clearing for the NEXT render cycle.

    Streamlit restores deleted keys if widgets already rendered in the current
    cycle, so we set a flag and perform the actual deletion at the top of the
    next render — before any per-row widgets are created.
    """
    st.session_state["_pending_widget_clear"] = True


def _apply_pending_widget_clear():
    """If a clear was scheduled, delete all frm_*/sql_preview_* keys now (before widgets render)."""
    if st.session_state.pop("_pending_widget_clear", False):
        for key in list(st.session_state.keys()):
            if isinstance(key, str) and (
                key.startswith("frm_") or key.startswith("sql_preview_")
                or key.startswith("_last_default_")
            ):
                del st.session_state[key]
        st.session_state["sql_overrides"] = {}
    # Apply pending paste-field overrides to widget keys (before widgets instantiate)
    _paste_overrides = st.session_state.pop("_pending_paste_overrides", None)
    if _paste_overrides:
        for wkey, wval in _paste_overrides.items():
            st.session_state[wkey] = wval


_STORE_PASTE_SPLIT_RE = _re.compile(r"[\s,;]+")
_STORE_PASTE_NUMERIC_RE = _re.compile(r"^\d+$")


def _parse_store_paste(raw: str) -> tuple[list[str], list[str]]:
    """Parse a multi-line/multi-column paste of store IDs into a validated list.

    Splits on any whitespace (newlines, tabs, spaces), commas, and semicolons so
    accidental multi-column Excel copies are tolerated. Each fragment must match
    ^\\d+$ to be accepted — no fragment is ever concatenated or modified, so
    two distinct store IDs can never merge.

    Duplicates are preserved (input count == output count for valid tokens); a
    duplicate summary is surfaced as an advisory warning for visibility.

    Returns (valid_ids, warnings) where valid_ids preserves input order, and
    warnings is a list of user-facing advisory strings.
    """
    warnings: list[str] = []
    if not raw or not raw.strip():
        return [], warnings
    tokens = [t for t in _STORE_PASTE_SPLIT_RE.split(raw) if t]
    valid: list[str] = []
    rejected: list[str] = []
    for tok in tokens:
        if _STORE_PASTE_NUMERIC_RE.match(tok):
            valid.append(tok)
        else:
            rejected.append(tok)
    if rejected:
        sample = ", ".join(f"`{r}`" for r in rejected[:5])
        more = f" (+{len(rejected) - 5} more)" if len(rejected) > 5 else ""
        warnings.append(f"Ignored {len(rejected)} non-numeric token(s): {sample}{more}")
    dup_count = len(valid) - len(set(valid))
    if dup_count:
        from collections import Counter as _Counter
        dup_ids = [sid for sid, n in _Counter(valid).items() if n > 1]
        sample = ", ".join(f"`{d}`" for d in dup_ids[:5])
        more = f" (+{len(dup_ids) - 5} more)" if len(dup_ids) > 5 else ""
        warnings.append(f"{dup_count} duplicate store ID(s) preserved across {len(dup_ids)} value(s): {sample}{more}")
    return valid, warnings


@st.cache_data(ttl=300)
def _load_valid_banners() -> set:
    """Load valid banner names from reference_data/banners.txt (one per line, lowercase)."""
    p = ROOT / "reference_data" / "banners.txt"
    if not p.exists():
        return set()
    return {line.strip().lower() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()}

@st.cache_data(ttl=300)
def _load_banner_options() -> list[str]:
    """Load sorted banner names from reference_data/banners.txt for multiselect dropdown."""
    p = ROOT / "reference_data" / "banners.txt"
    if not p.exists():
        return []
    return sorted({line.strip().lower() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()})

@st.cache_data(ttl=300)
def _load_division_options() -> list[str]:
    """Load division options from reference_data/divisions.txt for multiselect dropdown.

    File format: one entry per line as 'ID - Name' (e.g. '29 - Northwind Plains').
    Returns sorted list of 'ID - Name' display strings.
    """
    p = ROOT / "reference_data" / "divisions.txt"
    if not p.exists():
        return []
    options: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            options.append(line)
    return sorted(options, key=lambda x: int(x.split("-")[0].strip()) if x.split("-")[0].strip().isdigit() else 0)

def _division_display_to_id(display: str) -> str:
    """Extract the numeric ID from a 'ID - Name' display string."""
    return display.split("-")[0].strip()

def _division_ids_to_display(ids_str: str, options: list[str]) -> list[str]:
    """Convert a comma-separated IDs string to matching display options."""
    if not ids_str:
        return []
    # dict, not set: preserves the stored order so the widget doesn't reshuffle and re-save it
    ids = dict.fromkeys(i.strip() for i in ids_str.split(",") if i.strip())
    # Build a lookup from ID -> display string
    id_to_display = {}
    for opt in options:
        opt_id = _division_display_to_id(opt)
        id_to_display[opt_id] = opt
    return [id_to_display[i] for i in ids if i in id_to_display]

def _check_banner_spelling(rows: list) -> list[str]:
    """Return advisory warnings for banner names not in reference_data/banners.txt."""
    valid = _load_valid_banners()
    if not valid:
        return []
    warnings: list[str] = []
    for i, r in enumerate(rows):
        vlabel = r.get("_vlabel", f"Row {i+1}")
        label = r.get("campaign_name") or "(empty)"
        bad: list[str] = []
        # Flat targeting banners
        for b in (r.get("banners") or "").split(","):
            b = b.strip().lower()
            if b and b not in valid:
                bad.append(b)
        # OR group banners
        for g in r.get("div_banner_groups", []):
            for b in (g.get("banners") or "").split(","):
                b = b.strip().lower()
                if b and b not in valid:
                    bad.append(b)
        if bad:
            for b in sorted(set(bad)):
                warnings.append(f"{vlabel} — **{label}**: banner '**{b}**' is not a recognised banner name — check spelling")
    return warnings

_TRIM_FIELDS = ("message", "title", "offer_id", "theme", "banners")

def _trim_whitespace_fields(rows: list) -> list[str]:
    """Auto-trim leading/trailing and collapse internal consecutive spaces on key fields.

    Handles multi-theme containers by descending into sub_rows.
    Returns advisory messages.
    """
    notices: list[str] = []
    # Build a flat list of (row_dict, display_label) covering both top-level rows
    # and sub-rows from multi-theme containers.
    flat: list[tuple[dict, str]] = []
    for i, r in enumerate(rows):
        if r.get("multi_theme") and r.get("sub_rows"):
            pri = r.get("priority", i + 1)
            for si, sr in enumerate(r["sub_rows"]):
                flat.append((sr, f"Row {pri}.{si + 1}"))
        else:
            flat.append((r, f"Row {i + 1}"))
    for r, default_vlabel in flat:
        vlabel = r.get("_vlabel", default_vlabel)
        trimmed: list[str] = []
        for field in _TRIM_FIELDS:
            val = r.get(field, "")
            if not isinstance(val, str):
                continue
            fixed = val.strip()
            fixed = _MULTI_SPACE_RE.sub(" ", fixed)
            if fixed != val:
                r[field] = fixed
                trimmed.append(f"**{field}**")
        if trimmed:
            label = r.get("campaign_name") or "(empty)"
            notices.append(f"{vlabel} — {label}: trimmed whitespace from {', '.join(trimmed)}, NO ACTION NEEDED")
    return notices


# ── Title / Message character-count swap detection ──
# Fallback averages based on historical campaign data (used when no recent
# campaigns are available to compute dynamic baselines).
_FALLBACK_AVG_TITLE_LEN = 26
_FALLBACK_AVG_MESSAGE_LEN = 95


@st.cache_data(ttl=300, show_spinner=False)
def _compute_historical_char_stats() -> tuple[float, float]:
    """Compute average title/message char lengths from campaigns built in the last 7 days.

    Returns (avg_title_len, avg_message_len). Falls back to hardcoded
    constants if no recent data is available.
    """
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=7)
    title_lens: list[int] = []
    message_lens: list[int] = []
    try:
        all_campaigns = list_campaigns()
    except Exception:
        return float(_FALLBACK_AVG_TITLE_LEN), float(_FALLBACK_AVG_MESSAGE_LEN)
    for c in all_campaigns:
        send_date_str = c.get("send_date", "")
        try:
            sd = date.fromisoformat(send_date_str)
        except (ValueError, TypeError):
            continue
        if sd < cutoff:
            continue
        for r in c.get("rows", []):
            # Include sub-rows from multi-theme containers
            if r.get("multi_theme") and r.get("sub_rows"):
                for sr in r["sub_rows"]:
                    title = (sr.get("title") or "").strip()
                    message = (sr.get("message") or "").strip()
                    if title:
                        title_lens.append(len(title))
                    if message:
                        message_lens.append(len(message))
                continue
            title = (r.get("title") or "").strip()
            message = (r.get("message") or "").strip()
            if title:
                title_lens.append(len(title))
            if message:
                message_lens.append(len(message))
    avg_t = (sum(title_lens) / len(title_lens)) if title_lens else float(_FALLBACK_AVG_TITLE_LEN)
    avg_m = (sum(message_lens) / len(message_lens)) if message_lens else float(_FALLBACK_AVG_MESSAGE_LEN)
    return avg_t, avg_m


def _check_title_message_swap(rows: list) -> list[str]:
    """Detect rows where title and message may have been accidentally swapped.

    Uses average character counts from recent campaign builds as a baseline.
    Flags rows where:
      - title is longer than message (strong signal)
      - title exceeds 1.5× the historical average AND message is below 0.6× its average
    """
    warnings: list[str] = []
    avg_title, avg_message = _compute_historical_char_stats()
    for i, r in enumerate(rows):
        title = (r.get("title") or "").strip()
        message = (r.get("message") or "").strip()
        if not title or not message:
            continue
        t_len = len(title)
        m_len = len(message)
        vlabel = r.get("_vlabel", f"Row {i+1}")
        label = r.get("campaign_name") or "(empty)"
        # Strong signal: title is longer than message
        if t_len > m_len:
            warnings.append(
                f"{vlabel} — **{label}**: title ({t_len} chars) is **longer** than message ({m_len} chars) "
                f"— these fields may be swapped (avg title ~{avg_title:.0f}, avg message ~{avg_message:.0f})"
            )
        # Weaker signal: title is abnormally long AND message is abnormally short
        elif t_len > avg_title * 1.5 and m_len < avg_message * 0.6:
            warnings.append(
                f"{vlabel} — **{label}**: title is {t_len} chars (avg ~{avg_title:.0f}) "
                f"and message is only {m_len} chars (avg ~{avg_message:.0f}) "
                f"— verify these fields aren't swapped"
            )
    return warnings


# Offer-ID token pattern: 6–10 digits, optional `-LETTER` suffix.
# Matches the production pattern observed in existing campaign data
# (e.g. `90358653-D`, `41776202-D`).
_OFFER_ID_TOKEN_RE = _re.compile(r"^\d{6,10}(-[A-Z])?$")

# Store IDs must be digits only, comma-separated (whitespace tolerated around commas).
_STORE_ID_TOKEN_RE = _re.compile(r"^\d+$")


def _invalid_store_id_tokens(raw: str) -> list[str]:
    """Return non-numeric tokens found in a comma-separated store_ids string.

    Empty/whitespace strings are treated as valid (no filter). Whitespace around
    commas is trimmed. Any token that isn't a run of digits is returned so the
    caller can surface an error.
    """
    if not raw or not raw.strip():
        return []
    bad: list[str] = []
    for tok in raw.split(","):
        t = tok.strip()
        if not t:
            continue
        if not _STORE_ID_TOKEN_RE.match(t):
            bad.append(t)
    return bad


def _check_offer_id_format(rows: list) -> list[str]:
    """Warn when offer_id tokens don't match the expected `########-L` pattern.

    Skipped for rows whose offer_type is empty or PUSHSECTION (no offer JOIN).
    Multiple offer IDs may be comma-separated; each token is checked individually.
    """
    warnings: list[str] = []
    for i, r in enumerate(rows):
        if r.get("custom_sql"):
            continue
        offer_type = (r.get("offer_type") or "").strip().upper()
        if not offer_type or offer_type == "PUSHSECTION":
            continue
        raw = (r.get("offer_id") or "").strip()
        if not raw:
            continue
        bad: list[str] = []
        for tok in [t.strip() for t in raw.split(",") if t.strip()]:
            if tok.upper() == "TBD":
                continue  # placeholder is allowed, will surface elsewhere
            if not _OFFER_ID_TOKEN_RE.match(tok):
                bad.append(tok)
        if bad:
            vlabel = r.get("_vlabel", f"Row {i+1}")
            label = r.get("campaign_name") or "(empty)"
            warnings.append(
                f"{vlabel} — **{label}**: offer_id token(s) **{', '.join(bad)}** "
                f"don't match the expected pattern `########-L` (e.g. `90358653-D`)"
            )
    return warnings


def _check_canonicalcampaignid_present(rows: list) -> list[str]:
    """Warn when a row has no CANONICALCAMPAIGNID value.

    Applies to both form and SQL template rows. For SQL template rows the
    row value overrides the template's hard-coded ``'' as CANONICALCAMPAIGNID``
    at render time (see ``_override_canonicalcampaignid`` in compose.py).
    """
    warnings: list[str] = []
    for i, r in enumerate(rows):
        val = (r.get("CANONICALCAMPAIGNID") or "").strip()
        if val:
            continue
        vlabel = r.get("_vlabel", f"Row {i+1}")
        label = r.get("campaign_name") or "(empty)"
        warnings.append(
            f"{vlabel} — **{label}**: CANONICALCAMPAIGNID is blank — paste the ID from the CRF Notes column."
        )
    return warnings


def _check_store_ids_format(rows: list) -> list[str]:
    """Blocker: store_ids must be digits only (comma-separated).

    Checks the flat `store_ids` field on every row plus each `div_banner_groups`
    entry. Non-numeric tokens (e.g. `abc`, `Store_Number`, `1,001`) are surfaced
    so the user must fix them before submit / export.
    """
    errors: list[str] = []
    for i, r in enumerate(rows):
        vlabel = r.get("_vlabel", f"Row {i+1}")
        label = r.get("campaign_name") or "(empty)"

        bad = _invalid_store_id_tokens(r.get("store_ids") or "")
        if bad:
            errors.append(
                f"{vlabel} — **{label}**: `store_ids` contains non-numeric token(s) "
                f"**{', '.join(bad)}** — enter numbers only, separated by commas (e.g. `100,200,300`)"
            )

        for gi, g in enumerate(r.get("div_banner_groups") or []):
            bad_g = _invalid_store_id_tokens(g.get("store_ids") or "")
            if bad_g:
                errors.append(
                    f"{vlabel} — **{label}** OR group #{gi+1}: `store_ids` contains non-numeric "
                    f"token(s) **{', '.join(bad_g)}** — enter numbers only, separated by commas"
                )
    return errors


def _targeting_signature(r: dict) -> str | None:
    """Return a normalized signature for a row's targeting, or None if no targeting set."""
    parts: list[str] = []
    for fld, mode_fld in (("division_ids", "division_mode"),
                          ("banners", "banner_mode"),
                          ("store_ids", "store_mode")):
        vals = sorted(v.strip().lower() for v in (r.get(fld) or "").split(",") if v.strip())
        if vals:
            parts.append(f"{fld}:{r.get(mode_fld, 'IN')}:{','.join(vals)}")
    for g in (r.get("div_banner_groups") or []):
        gparts: list[str] = []
        for fld, mode_fld in (("division_ids", "div_mode"),
                              ("banners", "banner_mode"),
                              ("store_ids", "store_mode")):
            vals = sorted(v.strip().lower() for v in (g.get(fld) or "").split(",") if v.strip())
            if vals:
                gparts.append(f"{fld}:{g.get(mode_fld, 'IN')}:{','.join(vals)}")
        if gparts:
            parts.append("group(" + "|".join(gparts) + ")")
    return "||".join(sorted(parts)) if parts else None


def _check_targeting_sanity(rows: list) -> list[str]:
    """Detect EXCLUDE-with-empty-list, single-group OR blocks, and duplicate targeting sets."""
    warnings: list[str] = []
    sigs: dict[str, list[str]] = {}
    for i, r in enumerate(rows):
        if r.get("custom_sql"):
            continue
        vlabel = r.get("_vlabel", f"Row {i+1}")
        label = r.get("campaign_name") or "(empty)"

        # EXCLUDE mode with empty list (no-op)
        for fld, mode_fld, name in (("division_ids", "division_mode", "division_ids"),
                                    ("banners", "banner_mode", "banners"),
                                    ("store_ids", "store_mode", "store_ids")):
            mode = (r.get(mode_fld) or "IN").upper()
            val = (r.get(fld) or "").strip()
            if mode in ("NOT IN", "EXCLUDE") and not val:
                warnings.append(
                    f"{vlabel} — **{label}**: `{name}` set to EXCLUDE but list is empty — has no effect, remove it or fill the list"
                )

        # Single-group OR block (flatten suggestion)
        groups = r.get("div_banner_groups") or []
        if len(groups) == 1:
            warnings.append(
                f"{vlabel} — **{label}**: only one OR group defined — consider moving its values "
                f"into the flat targeting fields above and removing the OR group"
            )

        # Duplicate-targeting detection across rows
        sig = _targeting_signature(r)
        if sig:
            sigs.setdefault(sig, []).append(vlabel)

    for sig, row_labels in sigs.items():
        if len(row_labels) > 1:
            warnings.append(
                f"Rows **{', '.join(row_labels)}** share identical targeting — "
                f"likely a duplicate audience; verify each row really needs its own send"
            )
    return warnings


# ── SQL dry-parse (sqlglot, BigQuery dialect) ──────────────
def _render_row_sql_for_parse(r: dict, env, env_preview, tables, wk_id: str, send_date: str) -> tuple[str, str | None]:
    """Render a row's SQL exactly as it will appear in the export.
    Returns (sql_text, render_error). On error, sql_text is "" and the
    error string explains the render failure."""
    try:
        if r.get("custom_sql"):
            tpl_ctx = {k: v for k, v in r.items() if k not in ("custom_sql", "_row_id")}
            tpl_ctx["wk_id"] = wk_id
            tpl_ctx["send_date"] = send_date
            tpl_ctx["tables"] = tables
            tpl_ctx = _expand_offer_ids(tpl_ctx)
            tpl_ctx = _expand_extra_themes(tpl_ctx)
            tpl_ctx = _escape_sql_strings(tpl_ctx)
            return _override_canonicalcampaignid(env_preview.from_string(r["custom_sql"]).render(**tpl_ctx), r), None
        return render_campaign_insert(env, tables, r), None
    except Exception as exc:
        return "", str(exc)


def _check_sql_syntax(rows: list, wk_id: str, send_date: str, sql_overrides: dict | None = None) -> list[str]:
    """Parse each row's rendered SQL with sqlglot (BigQuery dialect).
    Returns blocker strings — anything that fails to parse will fail in BigQuery.
    Skipped silently if sqlglot is not installed."""
    try:
        import sqlglot
        from sqlglot.errors import ParseError
    except ImportError:
        return []

    sql_overrides = sql_overrides or {}
    env = jinja_env()
    env_preview = create_permissive_env()
    tables = load_tables(send_day=_derive_send_day(send_date))
    errors: list[str] = []
    for i, r in enumerate(rows):
        rid = r.get("_row_id", str(i))
        label = r.get("campaign_name") or "(empty)"
        sql_text = sql_overrides.get(rid)
        render_err = None
        if not sql_text:
            sql_text, render_err = _render_row_sql_for_parse(r, env, env_preview, tables, wk_id, send_date)
        if render_err:
            errors.append(f"Row {i+1} — **{label}**: SQL render error — `{render_err}`")
            continue
        if not (sql_text or "").strip():
            continue
        try:
            sqlglot.parse(sql_text, dialect="bigquery")
        except ParseError as pe:
            # First line of the parse error is usually the most informative.
            msg = str(pe).strip().splitlines()[0] if str(pe).strip() else "parse error"
            errors.append(f"Row {i+1} — **{label}**: SQL parse error — `{msg}`")
        except Exception as exc:
            errors.append(f"Row {i+1} — **{label}**: SQL parse error — `{exc}`")
    return errors


# ── Prior-week diff (recurring-campaign drift detection) ───
# Fields surfaced in the side-by-side diff panel.
_DIFF_FIELDS = (
    "theme", "title", "message", "media_url", "pushsection",
    "param_q", "screentitle", "subtitle",
    "offer_type", "offer_id",
    "division_ids", "division_mode", "banners", "banner_mode", "store_ids", "store_mode",
)


def _normalize_name(s: str) -> str:
    return (s or "").strip().lower()


def _find_previous_row(curr_row: dict, current_send_date: str, current_send_day: str,
                        current_campaign_id: str, all_campaigns: list[dict]) -> tuple[dict | None, dict | None]:
    """Find the prior week's matching row.

    Match rule: same send_day, earlier send_date, same campaign_name (case-insensitive).
    Returns (prior_campaign_meta, prior_row) — both None if no match.
    """
    name = _normalize_name(curr_row.get("campaign_name"))
    if not name:
        return None, None
    candidates: list[tuple[str, dict, dict]] = []
    for c in all_campaigns:
        if c.get("id") == current_campaign_id:
            continue
        if (c.get("send_day") or "").upper() != (current_send_day or "").upper():
            continue
        cs_date = c.get("send_date") or ""
        if not cs_date or cs_date >= current_send_date:
            continue
        for r in c.get("rows") or []:
            # Check sub-rows inside multi-theme containers
            if r.get("multi_theme") and r.get("sub_rows"):
                for sr in r["sub_rows"]:
                    if _normalize_name(sr.get("campaign_name")) == name:
                        candidates.append((cs_date, c, sr))
                        break
                if candidates and candidates[-1][1] is c:
                    break
                continue
            if _normalize_name(r.get("campaign_name")) == name:
                candidates.append((cs_date, c, r))
                break  # one match per campaign is enough
    if not candidates:
        return None, None
    candidates.sort(key=lambda t: t[0], reverse=True)
    _, prev_c, prev_r = candidates[0]
    return prev_c, prev_r


def _row_field_diffs(curr_row: dict, prev_row: dict) -> list[tuple[str, str, str]]:
    """Return [(field, prev_value, curr_value), ...] for fields that changed."""
    diffs: list[tuple[str, str, str]] = []
    for fld in _DIFF_FIELDS:
        cv = str(curr_row.get(fld, "") or "").strip()
        pv = str(prev_row.get(fld, "") or "").strip()
        if cv != pv:
            diffs.append((fld, pv, cv))
    return diffs


def _check_prior_week_drift(rows: list, current_campaign_id: str,
                             current_send_date: str, current_send_day: str) -> list[str]:
    """Warn when a row's `theme` is byte-identical to its prior-week counterpart
    (almost always means the wk-number wasn't updated)."""
    warnings: list[str] = []
    if not current_send_date or not current_send_day:
        return warnings
    try:
        all_campaigns = list_campaigns()
    except Exception:
        return warnings
    for i, r in enumerate(rows):
        if not (r.get("campaign_name") or "").strip():
            continue
        _, prev_r = _find_previous_row(r, current_send_date, current_send_day,
                                        current_campaign_id, all_campaigns)
        if not prev_r:
            continue
        curr_theme = (r.get("theme") or "").strip()
        prev_theme = (prev_r.get("theme") or "").strip()
        if curr_theme and curr_theme == prev_theme:
            vlabel = r.get("_vlabel", f"Row {i+1}")
            label = r.get("campaign_name") or "(empty)"
            warnings.append(
                f"{vlabel} — **{label}**: theme is identical to last week's value "
                f"(`{curr_theme}`) — looks like the week number wasn't updated"
            )
    return warnings


def _render_prior_week_panel(rows: list, current_campaign_id: str,
                              current_send_date: str, current_send_day: str) -> None:
    """Render the side-by-side previous-week diff panel."""
    if not current_send_date or not current_send_day:
        st.caption("Set Send Date and Send Day to enable previous-week comparison.")
        return
    try:
        all_campaigns = list_campaigns()
    except Exception as exc:
        st.warning(f"Could not load prior campaigns: {exc}")
        return

    # Flatten multi-theme containers into sub-rows for comparison
    flat_rows: list[dict] = []
    for i, r in enumerate(rows):
        if r.get("multi_theme") and r.get("sub_rows"):
            pri = r.get("priority", i + 1)
            for si, sr in enumerate(r["sub_rows"]):
                sr_copy = dict(sr)
                sr_copy["_vlabel"] = f"Row {pri}.{si + 1}"
                flat_rows.append(sr_copy)
        else:
            r_copy = dict(r)
            r_copy["_vlabel"] = f"Row {i + 1}"
            flat_rows.append(r_copy)

    matched = 0
    unmatched: list[str] = []
    for i, r in enumerate(flat_rows):
        name = (r.get("campaign_name") or "").strip()
        if not name:
            continue
        vlabel = r.get("_vlabel", f"Row {i+1}")
        prev_c, prev_r = _find_previous_row(r, current_send_date, current_send_day,
                                              current_campaign_id, all_campaigns)
        if not prev_r:
            unmatched.append(f"{vlabel} — **{name}** — no prior {current_send_day.title()} row found")
            continue
        matched += 1
        prev_label = f"Wk {prev_c.get('wk_id', '?')} · {prev_c.get('send_date', '?')}"
        diffs = _row_field_diffs(r, prev_r)
        with st.expander(
            f"{vlabel} — **{name}** vs {prev_label}  ·  "
            f"{len(diffs)} field(s) changed",
            expanded=False,
        ):
            if not diffs:
                st.success("Every tracked field is unchanged from last week. Verify this is intentional for a recurring send.")
            else:
                df = pd.DataFrame(
                    [(fld, pv or "(empty)", cv or "(empty)") for fld, pv, cv in diffs],
                    columns=["Field", f"Last week ({prev_c.get('send_date', '?')})", "This week"],
                )
                st.dataframe(df, hide_index=True, use_container_width=True)

    if matched == 0 and not unmatched:
        st.caption("No rows with a `campaign_name` to compare.")
        return
    st.caption(f"Compared {matched} row(s) against prior {current_send_day.title()} sends.")
    if unmatched:
        with st.expander(f"ℹ️ {len(unmatched)} row(s) without a prior match", expanded=False):
            for u in unmatched:
                st.markdown(f"- {u}")


# ── Consolidated Pre-QC Report ──────────────────────────────
_JINJA_VAR_RE = _re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _find_unfilled_placeholders(rows: list, sql_overrides: dict, wk_id: str) -> list[str]:
    """Return error strings for SQL template rows whose Jinja2 placeholders aren't filled."""
    errors: list[str] = []
    campaign_level = {
        "wk_id": (wk_id or "").strip(),
        "send_date": str(st.session_state.get("send_date", "") or "").strip(),
    }
    for i, r in enumerate(rows):
        if not r.get("custom_sql"):
            continue
        rid = r.get("_row_id", str(i))
        if rid in sql_overrides:
            continue
        placeholders = set(_JINJA_VAR_RE.findall(r["custom_sql"]))
        if not placeholders:
            continue
        # Build derived offer_id_N and offer_id_list from the offer_id field
        _offer_ids = [v.strip() for v in (r.get("offer_id") or "").split(",") if v.strip()]
        _derived: dict[str, str] = {}
        for _oi, _ov in enumerate(_offer_ids, start=1):
            _derived[f"offer_id_{_oi}"] = _ov
        if _offer_ids:
            _derived["offer_id_list"] = ",".join(f"'{o}'" for o in _offer_ids)
        # Build derived theme_N from extra_themes list
        _extra_themes = r.get("extra_themes", [])
        for _ti, _tv in enumerate(_extra_themes, start=1):
            _derived[f"theme_{_ti}"] = _tv
        unfilled: list[str] = []
        for var in sorted(placeholders):
            if var in campaign_level:
                if not campaign_level[var]:
                    unfilled.append(var)
            elif var in _derived:
                if not _derived[var]:
                    unfilled.append(var)
            else:
                if not (r.get(var) or "").strip():
                    unfilled.append(var)
        if unfilled:
            vlabel = r.get("_vlabel", f"Row {i+1}")
            label = r.get("campaign_name") or vlabel
            errors.append(
                f"{vlabel} ({label}): unfilled placeholder(s) — "
                + ", ".join("**{{" + v + "}}**" for v in unfilled)
            )
    return errors


def _run_preqc(
    rows: list,
    wk_id: str,
    send_day: str,
    *,
    sql_overrides: dict | None = None,
    include_placeholder: bool = False,
    current_campaign_id: str = "",
    current_send_date: str = "",
) -> dict:
    """Run all pre-QC checks and return a structured report.

    Returns a dict with keys:
      - blockers: list of {check, items: [str]} — must fix before submit/export
      - warnings: list of {check, items: [str]} — advisory, can acknowledge
      - notices:  list of {check, items: [str]} — informational only (auto-fixed)
      - passed:   list of check labels that produced no findings

    Channel-aware: PUSH runs the original check set; RCS runs a distinct set that
    skips PUSH-only concepts (title/message swap, param_q/screentitle, offer_id
    format, SQL-template placeholders) and adds RCS-only ones (BU_CC_ID
    underscore convention, FALLBACK_MESSAGE_BODY not double-prefixed, CARD/CAROUSEL
    body presence per card).
    """
    if _current_channel() == "rcs":
        return _run_preqc_rcs(
            rows, wk_id, send_day,
            current_campaign_id=current_campaign_id,
            current_send_date=current_send_date,
        )
    sql_overrides = sql_overrides or {}
    report: dict = {"blockers": [], "warnings": [], "notices": [], "passed": []}

    # Flatten multi-theme containers into sub-rows for validation.
    # Each row gets a _vlabel field for human-readable display.
    flat_rows: list[dict] = []
    for i, r in enumerate(rows):
        if r.get("multi_theme") and r.get("sub_rows"):
            pri = r.get("priority", i + 1)
            for si, sr in enumerate(r["sub_rows"]):
                sr_copy = dict(sr)
                sr_copy["_vlabel"] = f"Row {pri}.{si + 1}"
                sr_copy["priority"] = pri
                flat_rows.append(sr_copy)
        else:
            r_copy = dict(r)
            r_copy["_vlabel"] = f"Row {i + 1}"
            flat_rows.append(r_copy)
    rows = flat_rows

    def _section(bucket: str, label: str, items: list[str]) -> None:
        if items:
            report[bucket].append({"check": label, "items": items})
        else:
            report["passed"].append(label)

    # ---- BLOCKERS ----
    missing: list[str] = []
    for i, r in enumerate(rows):
        if r.get("custom_sql"):
            continue
        # Check REQUIRED_COLUMNS + theme (theme is rendered separately but still required)
        miss = [f for f in (REQUIRED_COLUMNS + [THEME_FIELD]) if not (r.get(f) or "").strip()]
        if miss:
            vlabel = r.get("_vlabel", f"Row {i+1}")
            label_row = r.get("campaign_name") or "(empty)"
            missing.append(f"{vlabel} ({label_row}): missing **{', '.join(miss)}**")
    _section("blockers", "Required fields present on every form row", missing)

    _section("blockers", "store_ids contain only numbers (comma-separated)",
             _check_store_ids_format(rows))

    if include_placeholder:
        ph_errors = _find_unfilled_placeholders(rows, sql_overrides, wk_id)
        _section("blockers", "All SQL template placeholders filled", ph_errors)

    # SQL dry-parse runs only after placeholders are filled, otherwise we
    # would parse incomplete templates and surface noisy false positives.
    if include_placeholder and not report["blockers"]:
        send_date = str(st.session_state.get("send_date", "") or "")
        parse_errors = _check_sql_syntax(rows, wk_id, send_date, sql_overrides)
        _section("blockers", "Each row parses as valid BigQuery SQL", parse_errors)

    # ---- WARNINGS ----
    dup_pri: list[str] = []
    dup_theme: list[str] = []
    no_offer: list[str] = []
    seen_pri: list = []
    seen_theme: list[str] = []
    for i, r in enumerate(rows):
        vlabel = r.get("_vlabel", f"Row {i+1}")
        p = r.get("priority")
        # Sub-rows (label contains '.') intentionally share priority — skip dup check for them
        if "." not in vlabel:
            if p in seen_pri:
                dup_pri.append(f"{vlabel}: priority **{p}** is used more than once")
            seen_pri.append(p)
        t = (r.get("theme") or "").strip()
        if t and t in seen_theme:
            dup_theme.append(f"{vlabel}: theme **'{t}'** repeats")
        if t:
            seen_theme.append(t)
        if not r.get("custom_sql") and not (r.get("offer_type") or "").strip():
            label_row = r.get("campaign_name") or "(empty)"
            no_offer.append(
                f"{vlabel} ({label_row}): no offer type set — `pushoffertype` and `pushofferid` will be NULL (no offer JOIN)"
            )
    _section("warnings", "No duplicate priorities", dup_pri)
    _section("warnings", "No duplicate themes", dup_theme)
    _section("warnings", "Offer type set on every form row", no_offer)

    _section("warnings", "title/message clean (no smart-quotes, [Banner], or stray whitespace)",
             _check_content_warnings(rows))
    _section("warnings", "title/message character counts (possible swap detection)",
             _check_title_message_swap(rows))
    _section("warnings", "param_q / screentitle formatting", _check_param_q_warnings(rows))
    _section("warnings", "theme ends with `_YYYY-MM-DD` matching Send Date",
             _check_theme_send_date_suffix(rows, current_send_date))
    _section("warnings", "banner names recognised", _check_banner_spelling(rows))
    _section("warnings", "offer_id matches expected format", _check_offer_id_format(rows))
    _section("warnings", "CANONICALCAMPAIGNID set on every form row", _check_canonicalcampaignid_present(rows))
    _section("warnings", "targeting setup looks sane", _check_targeting_sanity(rows))
    _section(
        "warnings",
        "themes updated from last week (recurring drift)",
        _check_prior_week_drift(rows, current_campaign_id, current_send_date, send_day),
    )

    return report


_RCS_CARD_COUNT_BOUNDS = {"CHOICE": (1, 1), "CARD": (1, 5), "CAROUSEL": (2, 7)}


def _run_preqc_rcs(
    rows: list,
    wk_id: str,
    send_day: str,
    *,
    current_campaign_id: str = "",
    current_send_date: str = "",
) -> dict:
    """Pre-QC report tailored to RCS row schemas.

    Skips PUSH-only checks (title/message swap, param_q, offer_id format, SQL syntax
    on templated SQL) and adds RCS-only ones (BU_CC_ID underscore convention,
    FALLBACK_MESSAGE_BODY not double-prefixed, MESSAGE_BODY per used card).
    """
    report: dict = {"blockers": [], "warnings": [], "notices": [], "passed": []}

    # Flatten multi-theme containers (mirrors the PUSH branch).
    flat_rows: list[dict] = []
    for i, r in enumerate(rows):
        if r.get("multi_theme") and r.get("sub_rows"):
            pri = r.get("priority", i + 1)
            for si, sr in enumerate(r["sub_rows"]):
                sr_copy = dict(sr)
                sr_copy["_vlabel"] = f"Row {pri}.{si + 1}"
                sr_copy["priority"] = pri
                flat_rows.append(sr_copy)
        else:
            r_copy = dict(r)
            r_copy["_vlabel"] = f"Row {i + 1}"
            flat_rows.append(r_copy)
    rows = flat_rows

    def _section(bucket: str, label: str, items: list[str]) -> None:
        if items:
            report[bucket].append({"check": label, "items": items})
        else:
            report["passed"].append(label)

    # ---- BLOCKERS ----
    missing: list[str] = []
    missing_body: list[str] = []
    for i, r in enumerate(rows):
        vlabel = r.get("_vlabel", f"Row {i+1}")
        label_row = r.get("campaign_name") or "(empty)"
        subtype = (r.get("channelsubtype") or r.get("offer_type") or "").strip().upper()

        miss = []
        if not (r.get("campaign_name") or "").strip():
            miss.append("campaign_name")
        if not (r.get("theme") or "").strip():
            miss.append("theme")
        if not (r.get("bu_cc_id") or "").strip():
            miss.append("bu_cc_id")
        if not subtype:
            miss.append("channelsubtype")
        if miss:
            missing.append(f"{vlabel} ({label_row}): missing **{', '.join(miss)}**")

        # MESSAGE_BODY presence per used card.
        if subtype:
            min_c, max_c = _RCS_CARD_COUNT_BOUNDS.get(subtype, (1, 1))
            if subtype == "CAROUSEL":
                declared = int(r.get("carousel_card_count") or min_c)
                used_cards = max(min_c, min(max_c, declared))
            else:
                used_cards = min_c
            cards = r.get("cards") or []
            for ci in range(used_cards):
                body = ""
                if ci < len(cards) and isinstance(cards[ci], dict):
                    body = (cards[ci].get("body") or "").strip()
                if not body:
                    missing_body.append(
                        f"{vlabel} ({label_row}): missing **MESSAGE_BODY_{ci + 1}**"
                    )
    _section("blockers", "Required RCS fields present on every row", missing)
    _section("blockers", "MESSAGE_BODY populated on every used card", missing_body)

    _section("blockers", "store_ids contain only numbers (comma-separated)",
             _check_store_ids_format(rows))

    # ---- WARNINGS ----
    dup_pri: list[str] = []
    dup_theme: list[str] = []
    no_subtype: list[str] = []
    seen_pri: list = []
    seen_theme: list[str] = []
    for i, r in enumerate(rows):
        vlabel = r.get("_vlabel", f"Row {i+1}")
        p = r.get("priority")
        if "." not in vlabel:
            if p in seen_pri:
                dup_pri.append(f"{vlabel}: priority **{p}** is used more than once")
            seen_pri.append(p)
        t = (r.get("theme") or "").strip()
        if t and t in seen_theme:
            dup_theme.append(f"{vlabel}: theme **'{t}'** repeats")
        if t:
            seen_theme.append(t)
        subtype = (r.get("channelsubtype") or r.get("offer_type") or "").strip()
        if not subtype:
            label_row = r.get("campaign_name") or "(empty)"
            no_subtype.append(
                f"{vlabel} ({label_row}): no CHANNEL_SUB_TYPE set — cannot dispatch to CHOICE/CARD/CAROUSEL template"
            )
    _section("warnings", "No duplicate priorities", dup_pri)
    _section("warnings", "No duplicate themes", dup_theme)
    _section("warnings", "CHANNEL_SUB_TYPE set on every row", no_subtype)

    # BU_CC_ID convention — must end in underscore.
    bad_bu: list[str] = []
    for i, r in enumerate(rows):
        v = (r.get("bu_cc_id") or "").strip()
        if v and not v.endswith("_"):
            vlabel = r.get("_vlabel", f"Row {i+1}")
            bad_bu.append(f"{vlabel}: BU_CC_ID **'{v}'** should end with `_` (e.g. `region-promo_`)")
    _section("warnings", "BU_CC_ID ends in underscore", bad_bu)

    # FALLBACK_MESSAGE_BODY must not be double-prefixed with [BANNER]:
    bad_fb: list[str] = []
    for i, r in enumerate(rows):
        v = (r.get("fallback_message_body") or "").strip()
        if v.lower().startswith("[banner]:"):
            vlabel = r.get("_vlabel", f"Row {i+1}")
            bad_fb.append(
                f"{vlabel}: FALLBACK_MESSAGE_BODY starts with `[BANNER]:` — the prefix is added automatically at export, remove it here"
            )
    _section("warnings", "FALLBACK_MESSAGE_BODY not double-prefixed with [BANNER]:", bad_fb)

    _section("warnings", "theme contains week ID and send day", _check_theme_mismatch(rows, wk_id, send_day))
    _section("warnings", "banner names recognised", _check_banner_spelling(rows))
    _section("warnings", "targeting setup looks sane", _check_targeting_sanity(rows))
    _section(
        "warnings",
        "themes updated from last week (recurring drift)",
        _check_prior_week_drift(rows, current_campaign_id, current_send_date, send_day),
    )

    return report


def _render_preqc_scorecard(report: dict, *, row_count: int | None = None) -> tuple[bool, bool]:
    """Render the consolidated Pre-QC scorecard.

    Returns (has_blockers, has_warnings) so callers can gate Submit/Export buttons.
    """
    # If no rows exist, skip the full scorecard — checks are meaningless on an empty grid
    if row_count is not None and row_count == 0:
        st.info("No campaign rows yet — add rows to enable pre-QC checks.")
        return False, False

    n_block = sum(len(s["items"]) for s in report["blockers"])
    n_warn = sum(len(s["items"]) for s in report["warnings"])

    c1, c2 = st.columns(2)
    with c1:
        st.metric("⚠️ Warnings", n_warn)
    with c2:
        st.metric("🚫 Blockers", n_block)

    if n_block:
        st.error(f"🚫 {n_block} blocker(s) found — must be fixed before submitting / exporting.")
        for sec in report["blockers"]:
            with st.expander(f"❌ {sec['check']} — {len(sec['items'])} issue(s)", expanded=True):
                for item in sec["items"]:
                    st.markdown(f"- {item}")

    if n_warn:
        with st.expander(
            f"⚠️ {n_warn} advisory warning(s) — review before submitting",
            expanded=not n_block,
        ):
            for sec in report["warnings"]:
                st.markdown(f"**{sec['check']}** — {len(sec['items'])}")
                for item in sec["items"]:
                    st.markdown(f"  - {item}")
                st.markdown("")

    return bool(n_block), bool(n_warn)


@st.cache_data(ttl=60)
def load_sql_templates():
    if not _sql_templates_dir().exists():
        return {}
    return {
        p.stem: p.read_text(encoding="utf-8")
        for p in sorted(_sql_templates_dir().glob("*.sql"))
    }

_EXCEL_TEXT_FORCE_COLS = {"store_ids", "division_ids", "offer_id"}


def _build_csv_bytes(df: pd.DataFrame, save_path: Path | None = None) -> bytes:
    """Encode DataFrame as UTF-8 CSV with BOM so Excel renders emojis correctly.
    If *save_path* is given, also writes the bytes to disk for verification.
    All columns are explicitly cast to string (except priority which stays int)
    to prevent pandas from auto-inferring numeric types. Numeric-looking text
    columns (store_ids, division_ids, offer_id) are wrapped in =\"value\" to
    prevent Excel from converting them into numbers."""
    df_out = df.copy()
    # Force all columns to string to guarantee consistent quoting/format,
    # except priority which is intentionally an integer column.
    for col in df_out.columns:
        if col == "priority":
            continue
        df_out[col] = df_out[col].fillna("").astype(str)
    # Wrap numeric-ID columns with ="value" so Excel keeps them as text
    for col in _EXCEL_TEXT_FORCE_COLS:
        if col in df_out.columns:
            df_out[col] = df_out[col].apply(
                lambda v: f'="{v}"' if v and str(v).strip() else v
            )
    csv_str = df_out.to_csv(index=False)
    data = b"\xef\xbb\xbf" + csv_str.encode("utf-8")
    if save_path is not None:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(data)
    return data

def _import_csv_rows(uploaded_file) -> tuple[list[dict], list[str]]:
    """Parse an uploaded CSV (UTF-8/BOM) into a list of row dicts matching the grid schema.
    Returns (rows, parse_warnings) — rows ready to append, warnings for fields that could not be parsed."""
    raw = uploaded_file.read()
    # Strip BOM if present
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]
    text = raw.decode("utf-8")
    df = pd.read_csv(pd.io.common.StringIO(text), dtype=str, keep_default_na=False)
    imported: list[dict] = []
    parse_warnings: list[str] = []
    for row_num, (_, csv_row) in enumerate(df.iterrows(), start=1):
        row = {c: "" for c in _all_columns()}
        row["priority"] = ""
        row["custom_sql"] = ""
        row["targeting_notes"] = ""
        # Map CSV columns into row dict
        for col in df.columns:
            col_clean = col.strip()
            if col_clean in row:
                val = str(csv_row[col]).strip()
                # Strip ="..." wrapper used for Excel text-force columns
                if col_clean in _EXCEL_TEXT_FORCE_COLS and val.startswith('="') and val.endswith('"'):
                    val = val[2:-1]
                row[col_clean] = val
        # Coerce priority to int
        try:
            row["priority"] = int(float(row.get("priority", 0) or 0))
        except (ValueError, TypeError):
            row["priority"] = 0
        # Default mode columns
        for mode_col in ("division_mode", "banner_mode", "store_mode"):
            if row[mode_col] not in ("IN", "NOT IN"):
                row[mode_col] = "IN"
        # Parse div_banner_groups from JSON string (CSV roundtrip)
        dbg_raw = str(csv_row.get("div_banner_groups", "")).strip() if "div_banner_groups" in df.columns else ""
        if dbg_raw:
            try:
                parsed = _json.loads(dbg_raw)
                if isinstance(parsed, list):
                    row["div_banner_groups"] = parsed
                else:
                    parse_warnings.append(f"Row {row_num}: div_banner_groups was not a valid list — targeting groups cleared.")
                    row["div_banner_groups"] = []
            except (ValueError, TypeError):
                parse_warnings.append(f"Row {row_num}: div_banner_groups could not be parsed — targeting groups cleared.")
                row["div_banner_groups"] = []
        else:
            row["div_banner_groups"] = []
        # Parse custom_joins from JSON string (CSV roundtrip)
        cj_raw = str(csv_row.get("custom_joins", "")).strip() if "custom_joins" in df.columns else ""
        if cj_raw:
            try:
                parsed_cj = _json.loads(cj_raw)
                if isinstance(parsed_cj, list):
                    row["custom_joins"] = parsed_cj
                else:
                    parse_warnings.append(f"Row {row_num}: custom_joins was not a valid list — custom JOINs cleared.")
                    row["custom_joins"] = []
            except (ValueError, TypeError):
                parse_warnings.append(f"Row {row_num}: custom_joins could not be parsed — custom JOINs cleared.")
                row["custom_joins"] = []
        else:
            row["custom_joins"] = []
        # Parse extra_themes from comma-separated string (CSV roundtrip)
        et_raw = str(csv_row.get("extra_themes", "")).strip() if "extra_themes" in df.columns else ""
        if et_raw:
            # Support legacy JSON format for backwards compatibility
            if et_raw.startswith("["):
                try:
                    parsed_et = _json.loads(et_raw)
                    if isinstance(parsed_et, list):
                        row["extra_themes"] = parsed_et
                    else:
                        row["extra_themes"] = []
                except (ValueError, TypeError):
                    row["extra_themes"] = [v.strip() for v in et_raw.split(",") if v.strip()]
            else:
                row["extra_themes"] = [v.strip() for v in et_raw.split(",") if v.strip()]
        else:
            row["extra_themes"] = []
        # Restore targeting_notes from CSV (not in ALL_COLUMNS but already initialised)
        tn_raw = str(csv_row.get("targeting_notes", "")).strip() if "targeting_notes" in df.columns else ""
        if tn_raw:
            row["targeting_notes"] = tn_raw
        # Restore rich_push_image flag from CSV (Y/N)
        rpi_raw = str(csv_row.get("rich_push_image", "")).strip().upper() if "rich_push_image" in df.columns else ""
        row["rich_push_image"] = rpi_raw == "Y"
        row["multi_theme"] = False
        row["sub_rows"] = []
        row["handling_time"] = 0.0
        row["_row_id"] = _new_row_id()
        imported.append(row)

    # ---- Auto-group rows sharing the same priority into multi-theme containers ----
    from collections import OrderedDict as _OD
    priority_groups: dict[int, list[dict]] = _OD()
    for r in imported:
        pri = r.get("priority", 0)
        priority_groups.setdefault(pri, []).append(r)

    grouped: list[dict] = []
    grouped_count = 0
    for pri, group in priority_groups.items():
        if len(group) == 1:
            grouped.append(group[0])
        else:
            # Create multi-theme container from the group
            parent = {c: "" for c in _all_columns()}
            parent["priority"] = pri
            # Use first sub-row's campaign_name as group label
            parent["campaign_name"] = group[0].get("campaign_name", "")
            parent["multi_theme"] = True
            parent["sub_rows"] = group  # each row becomes a sub-row
            parent["custom_sql"] = ""
            parent["targeting_notes"] = ""
            parent["div_banner_groups"] = []
            parent["custom_joins"] = []
            parent["extra_themes"] = []
            parent["rich_push_image"] = False
            parent["handling_time"] = 0.0
            parent["_row_id"] = _new_row_id()
            # Mark sub-rows as non-multi (they're leaves)
            for sr in group:
                sr["multi_theme"] = False
                sr["sub_rows"] = []
            grouped.append(parent)
            grouped_count += 1

    if grouped_count:
        parse_warnings.append(
            f"Auto-grouped {sum(len(g) for g in priority_groups.values() if len(g) > 1)} rows "
            f"into {grouped_count} multi-theme container(s) based on shared priority."
        )

    return grouped, parse_warnings

# ──────────────────────────────────────────────
# HELPERS — load active campaign into session state
# ──────────────────────────────────────────────

def _load_into_session(campaign: dict):
    """Populate session state from a campaign day dict."""
    st.session_state.active_campaign_id = campaign["id"]
    st.session_state.wk_id = campaign.get("wk_id", "")
    # Sync the detail-view Week ID input widget to the loaded campaign
    st.session_state["detail_wk_id"] = campaign.get("wk_id", "")
    st.session_state.send_date = (
        datetime.strptime(campaign["send_date"], "%Y-%m-%d").date()
        if campaign.get("send_date") else date.today()
    )
    st.session_state.send_day = campaign.get("send_day", "")
    st.session_state.rows = campaign.get("rows", [])
    # Backfill stable row IDs for rows loaded from older JSON files
    for r in st.session_state.rows:
        if "_row_id" not in r:
            r["_row_id"] = _new_row_id()
        if "handling_time" not in r:
            r["handling_time"] = 0.0
        if "multi_theme" not in r:
            r["multi_theme"] = False
        if "sub_rows" not in r:
            r["sub_rows"] = []
    st.session_state.audit = campaign.get("audit", [])
    st.session_state.campaign_status = campaign.get("status", "Draft")
    st.session_state["_loaded_updated_at"] = campaign.get("updated_at")
    st.session_state.pop("_save_conflict", None)
    # Reset handling-time tracker for the new campaign
    st.session_state.pop("_ht_active_rid", None)
    st.session_state.pop("_ht_last_time", None)
    # Per-row targeting_notes are stored inside each row dict — no campaign-level field needed


def _apply_pushsection_default(rows: list) -> None:
    """In-place: for any row (or sub-row) with a pushsection value and blank offer_type, set offer_type=PUSHSECTION."""
    for r in rows or []:
        if isinstance(r, dict):
            _promote_pushsection_offer_type(r)
            for sr in r.get("sub_rows", []) or []:
                if isinstance(sr, dict):
                    _promote_pushsection_offer_type(sr)


def _note_external_change(disk_campaign: dict) -> None:
    """Record a conflict if the on-disk campaign was saved by someone else since we loaded it."""
    loaded_at = st.session_state.get("_loaded_updated_at")
    disk_at = disk_campaign.get("updated_at")
    if loaded_at and disk_at and disk_at != loaded_at:
        st.session_state["_save_conflict"] = {"at": disk_at, "other": _copy.deepcopy(disk_campaign)}


def _save_from_session(activity_event: str | None = None):
    """Save current session state back to disk.

    Args:
        activity_event: Optional lifecycle event name to append to the
            campaign's ``activity_log`` (e.g. "Saved", "Submitted for Export").
    """
    cid = st.session_state.get("active_campaign_id")
    if not cid:
        return
    campaign = load_campaign(cid) or {}
    _note_external_change(campaign)
    prev_status = campaign.get("status", "Draft")
    new_status = st.session_state.get("campaign_status", "Draft")
    _apply_pushsection_default(st.session_state.get("rows", []))
    campaign.update({
        "id": cid,
        "wk_id": st.session_state.get("wk_id", ""),
        "send_date": str(st.session_state.get("send_date", date.today())),
        "send_day": st.session_state.get("send_day", ""),
        "status": new_status,
        "rows": st.session_state.get("rows", []),
        "audit": st.session_state.get("audit", []),
    })
    # Track status transitions
    if new_status != prev_status:
        history = campaign.get("status_history", [])
        history.append({"status": new_status, "ts": datetime.now().isoformat()})
        campaign["status_history"] = history
    # Append activity log entry
    if activity_event:
        log = campaign.get("activity_log", [])
        log.append({"action": activity_event, "ts": datetime.now().isoformat()})
        campaign["activity_log"] = log
    save_campaign(campaign)
    st.session_state["_loaded_updated_at"] = campaign.get("updated_at")
    st.session_state.last_saved_at = datetime.now().strftime("%I:%M:%S %p")


# ──────────────────────────────────────────────
# VIEW: Dashboard
# ──────────────────────────────────────────────

def _status_badge(status: str) -> str:
    color = STATUS_COLORS.get(status, "#787878")
    return (
        f'<span style="background:{color};color:white;padding:6px 14px;'
        f'border-radius:999px;font-size:0.8em;font-weight:700;letter-spacing:0.03em;'
        f'text-transform:uppercase;box-shadow:0 2px 6px rgba(0,0,0,0.25),'
        f'inset 0 1px 0 rgba(255,255,255,0.15);display:inline-block;">{status}</span>'
    )


def _sanitize_wk_id_key(key: str) -> None:
    """Strip non-digits and cap at 6 chars for the given session_state key."""
    raw = st.session_state.get(key, "") or ""
    digits = "".join(ch for ch in str(raw) if ch.isdigit())[:6]
    if digits != raw:
        st.session_state[key] = digits


def _pst_today() -> date:
    """Return the current calendar date in America/Los_Angeles (the tz the app uses
    for status auto-transitions and the sidebar clock)."""
    return datetime.now(_ZoneInfo("America/Los_Angeles")).date()


# ──────────────────────────────────────────────
# BUILD TIME ANALYTICS VIEW (Developer only)
# ──────────────────────────────────────────────

_DOW_ORDER = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
_DOW_SHORT = {"MONDAY": "Mon", "TUESDAY": "Tue", "WEDNESDAY": "Wed", "THURSDAY": "Thu",
              "FRIDAY": "Fri", "SATURDAY": "Sat", "SUNDAY": "Sun"}


# ──────────────────────────────────────────────
# PER-ROW EXPANDABLE FORM
# ──────────────────────────────────────────────

# JOIN types available for custom JOINs
_JOIN_TYPES = ["JOIN", "LEFT JOIN", "INNER JOIN", "CROSS JOIN"]

# User-friendly labels for IN / NOT IN mode selectors
_MODE_DISPLAY = {"IN": "INCLUDE", "NOT IN": "EXCLUDE"}
_MODE_STORAGE = {"INCLUDE": "IN", "EXCLUDE": "NOT IN"}
_MODE_OPTIONS = ["INCLUDE", "EXCLUDE"]

# ─────────────────────────────────────────────────────────────────────
# RCS row form — completely separate from PUSH. All labels are SQL column
# names verbatim. Cards edited via tabs; buttons under sub-expanders.
# ─────────────────────────────────────────────────────────────────────

_RCS_CARD_COUNTS = {"CHOICE": (1, 1), "CARD": (1, 5), "CAROUSEL": (2, 7)}


def _promote_pushsection_offer_type(row: dict) -> None:
    """Set ``row['offer_type']`` to PUSHSECTION when the row has a pushsection value
    and no explicit offer type was supplied by the CRF Type column."""
    if row.get("pushsection") and not (row.get("offer_type") or "").strip():
        row["offer_type"] = "PUSHSECTION"


# ──────────────────────────────────────────────
# VIEW: Script Editor (Developer only)
# ──────────────────────────────────────────────

# Editable SQL script files — label → path relative to the active channel folder
# (reference_data/ is shared and resolved from ROOT).
_SCRIPT_EDITOR_FILES = {
    "Campaign INSERT (campaign_insert.sql.j2)": "macros/campaign_insert.sql.j2",
    "Preamble (preamble.sql.j2)": "macros/preamble.sql.j2",
    "Finalization (finalization.sql.j2)": "macros/finalization.sql.j2",
    "Finalization Static Tail (finalization_static_tail.sql)": "extras/finalization_static_tail.sql",
    "Offer — Personalized Deal (personalized_deal.sql.j2)": "macros/offer_types/personalized_deal.sql.j2",
    "Offer — Store Coupon (store_coupon.sql.j2)": "macros/offer_types/store_coupon.sql.j2",
    "Offer — PUSHSECTION (pushsection.sql.j2)": "macros/offer_types/pushsection.sql.j2",
    "Store Banners (banners.txt)": "reference_data/banners.txt",
    "Divisions (divisions.txt)": "reference_data/divisions.txt",
}


# ──────────────────────────────────────────────
# MAIN — view router
# ──────────────────────────────────────────────

# Human-readable labels for each channel (used in sidebar/dashboard headers).
_CHANNEL_LABELS = {"push": "PUSH", "rcs": "RCS"}
_CHANNEL_ICONS = {"push": "📱", "rcs": "💬"}
_CHANNEL_TAGLINES = {
    "push": "Build PUSH campaign scripts — PERSONALIZED DEAL, STORE COUPON, and PUSHSECTION campaigns.",
    "rcs": "Build RCS campaign scripts — CHOICE, CARD, and CAROUSEL campaigns.",
}


def _channel_badge_html(channel: str | None = None, *, size: str = "md") -> str:
    """Small pill showing the active channel (icon + label). Used in headers and breadcrumbs."""
    ch = (channel or _current_channel() or "push").lower()
    label = _CHANNEL_LABELS.get(ch, ch.upper())
    icon = _CHANNEL_ICONS.get(ch, "")
    if size == "sm":
        pad, font = "2px 8px", "0.72em"
    else:
        pad, font = "4px 12px", "0.82em"
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f'padding:{pad};border-radius:999px;font-size:{font};font-weight:700;'
        f'background:rgba(87,155,252,0.12);border:1px solid rgba(87,155,252,0.35);'
        f'color:var(--pace-primary);letter-spacing:0.04em;">'
        f'{icon} {label}</span>'
    )


def main():
    # Imported here, not at module top: the views import helpers back from this module.
    from views.analytics import render_analytics
    from views.crf_converter import render_crf_converter
    from views.dashboard import render_dashboard
    from views.detail import render_detail
    from views.landing import _render_channel_selector, render_landing
    from views.script_editor import render_script_editor

    st.set_page_config(page_title="P·A·C·E — Precision Audience Campaign Engine", layout="wide")
    init_state()

    # ===== Global CSS: modern P·A·C·E design system (loaded from app/static/pace_global.html) =====
    st.markdown(_load_pace_global_css(), unsafe_allow_html=True)

    # ---- Landing gate: no channel selected → show landing only, no sidebar/nav ----
    if not st.session_state.get("channel"):
        render_landing()
        return

    # ---- Sidebar: role selector + styled title ----
    with st.sidebar:
        _channel_active = st.session_state.get("channel")
        _channel_tag = _CHANNEL_LABELS.get(_channel_active, "")
        _tagline = (
            f"ORCHARD & TIDE · CAMPAIGN STUDIO<br/>"
            f"<span style='color:var(--pace-primary);'>{_channel_tag}</span> channel"
        ) if _channel_tag else "ORCHARD & TIDE · CAMPAIGN STUDIO"
        st.markdown(f"""
        <div class="pace-logo-block">
        <div style="text-align:center;padding:14px 0 10px 0;">
            <div style="display:inline-block;padding:8px 20px;border-radius:16px;
                        background:linear-gradient(135deg, rgba(87,155,252,0.18) 0%, rgba(162,93,220,0.12) 100%);
                        border:1px solid rgba(87,155,252,0.30);
                        box-shadow:0 4px 16px rgba(87,155,252,0.15);">
                <div style="font-size:2.2em;font-weight:800;letter-spacing:0.16em;line-height:1;
                            background:linear-gradient(135deg, #6ba9ff 0%, #a25ddc 100%);
                            -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                            background-clip:text;">P·A·C·E</div>
            </div>
            <div style="font-size:0.72em;color:var(--pace-text-muted);margin-top:10px;letter-spacing:0.08em;
                        font-weight:600;text-transform:uppercase;line-height:1.5;">
                {_tagline}
            </div>
        </div>
        </div>
        <div class="pace-logo-btn-marker"></div>
        """, unsafe_allow_html=True)
        if st.button("Go to Dashboard", key="pace_logo_home_btn", use_container_width=True):
            st.session_state.view = "dashboard"
            st.rerun()
        st.divider()

        # ---- Channel selector (PUSH ↔ RCS) ----
        if _RCS_ENABLED:
            _render_channel_selector()

        st.markdown("<div style='font-size:0.72em;color:var(--pace-text-muted);font-weight:600;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:6px;'>Role</div>", unsafe_allow_html=True)
        role_btn_col1, role_btn_col2 = st.columns(2)
        with role_btn_col1:
            if st.button("👤 User", key="role_user_btn", type="primary" if st.session_state.role == "user" else "secondary", use_container_width=True):
                st.session_state.role = "user"
                st.rerun()
        with role_btn_col2:
            if st.button("🔧 Developer", key="role_dev_btn", type="primary" if st.session_state.role == "developer" else "secondary", use_container_width=True):
                if st.session_state.get("dev_unlocked"):
                    st.session_state.role = "developer"
                    st.rerun()
                else:
                    st.session_state["_dev_prompt"] = True
                    st.rerun()

        # --- Developer passphrase prompt ---
        if st.session_state.get("_dev_prompt") and not st.session_state.get("dev_unlocked"):
            st.markdown("---")
            st.markdown("🔒 **Enter developer passphrase**")
            pwd = st.text_input("Passphrase", type="password", key="dev_pwd_input", label_visibility="collapsed")
            pcol1, pcol2 = st.columns(2)
            with pcol1:
                if st.button("Unlock", key="dev_unlock_btn", use_container_width=True):
                    expected = _load_dev_passphrase_hash()
                    entered = _hashlib.sha256(pwd.encode()).hexdigest() if pwd else ""
                    if expected and entered == expected:
                        st.session_state.dev_unlocked = True
                        st.session_state.role = "developer"
                        st.session_state.pop("_dev_prompt", None)
                        st.rerun()
                    else:
                        st.error("Incorrect passphrase.")
            with pcol2:
                if st.button("Cancel", key="dev_cancel_btn", use_container_width=True):
                    st.session_state.pop("_dev_prompt", None)
                    st.rerun()

        st.divider()
        # PST clock
        _pst_clock = datetime.now(_ZoneInfo("America/Los_Angeles"))
        st.markdown(
            f"""
            <div style="padding:8px 12px;border-radius:10px;background:rgba(87,155,252,0.06);
                        border:1px solid rgba(87,155,252,0.20);">
                <div style="font-size:0.68em;color:var(--pace-text-muted);letter-spacing:0.10em;
                            text-transform:uppercase;font-weight:600;margin-bottom:2px;">
                    Pacific Time
                </div>
                <div style="font-size:1.05em;font-weight:700;color:var(--pace-text);letter-spacing:-0.01em;">
                    🕐 {_pst_clock.strftime('%I:%M %p')}
                </div>
                <div style="font-size:0.78em;color:var(--pace-text-muted);margin-top:2px;">
                    {_pst_clock.strftime('%A · %b %d, %Y')}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.divider()
        # Breadcrumb navigation (channel-prefixed)
        _bc_badge = _channel_badge_html(size="sm")
        if st.session_state.view == "detail":
            d = st.session_state.get("send_date", "")
            st.markdown(f"<div style='font-size:0.85em;color:var(--pace-text-muted);display:flex;align-items:center;gap:6px;flex-wrap:wrap;'>{_bc_badge} <span>📍 Dashboard → <span style='color:var(--pace-text);font-weight:600;'>{d}</span></span></div>", unsafe_allow_html=True)
        elif st.session_state.view == "analytics":
            st.markdown(f"<div style='font-size:0.85em;color:var(--pace-text-muted);display:flex;align-items:center;gap:6px;flex-wrap:wrap;'>{_bc_badge} <span>📍 Dashboard → <span style='color:var(--pace-text);font-weight:600;'>Build Analytics</span></span></div>", unsafe_allow_html=True)
        elif st.session_state.view == "script_editor":
            st.markdown(f"<div style='font-size:0.85em;color:var(--pace-text-muted);display:flex;align-items:center;gap:6px;flex-wrap:wrap;'>{_bc_badge} <span>📍 Dashboard → <span style='color:var(--pace-text);font-weight:600;'>Script Editor</span></span></div>", unsafe_allow_html=True)
        elif st.session_state.view == "crf_converter":
            st.markdown(f"<div style='font-size:0.85em;color:var(--pace-text-muted);display:flex;align-items:center;gap:6px;flex-wrap:wrap;'>{_bc_badge} <span>📍 Dashboard → <span style='color:var(--pace-text);font-weight:600;'>CRF Converter</span></span></div>", unsafe_allow_html=True)
        # CRF Converter nav button (all roles) — sits just above the Developer-only tools group
        else:
            st.markdown(f"<div style='font-size:0.85em;color:var(--pace-text);font-weight:600;display:flex;align-items:center;gap:6px;flex-wrap:wrap;'>{_bc_badge} <span>📍 Dashboard</span></div>", unsafe_allow_html=True)

        # Active sessions indicator (Developer only)
        if _is_developer():
            count = _get_active_session_count()
            if count is not None:
                st.divider()
                st.markdown(
                    f"""
                    <div style="display:inline-flex;align-items:center;gap:6px;
                                padding:4px 10px;border-radius:999px;
                                background:rgba(34,197,94,0.10);
                                border:1px solid rgba(34,197,94,0.30);
                                font-size:0.82em;font-weight:600;color:#22c55e;">
                        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;
                                     background:#22c55e;box-shadow:0 0 8px #22c55e;"></span>
                        {count} active session{'s' if count != 1 else ''}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # CRF Converter nav button (all roles)
        st.divider()
        if st.session_state.view != "crf_converter":
            if st.button("📋 CRF Converter", key="nav_crf_btn", use_container_width=True):
                st.session_state.view = "crf_converter"
                st.rerun()
        else:
            if st.button("← Dashboard", key="nav_crf_back_btn", use_container_width=True):
                st.session_state.view = "dashboard"
                st.rerun()

        if _is_developer():
            # Analytics nav button
            st.divider()
            if st.session_state.view != "analytics":
                if st.button("📊 Build Analytics", key="nav_analytics_btn", use_container_width=True):
                    st.session_state.view = "analytics"
                    st.rerun()
            else:
                if st.button("← Dashboard", key="nav_dashboard_btn", use_container_width=True):
                    st.session_state.view = "dashboard"
                    st.rerun()
            # Script Editor nav button
            if st.session_state.view != "script_editor":
                if st.button("📝 Script Editor", key="nav_scripts_btn", use_container_width=True):
                    st.session_state.view = "script_editor"
                    st.rerun()
            else:
                if st.button("← Dashboard", key="nav_scripts_back_btn", use_container_width=True):
                    st.session_state.view = "dashboard"
                    st.rerun()

    if st.session_state.view == "detail" and st.session_state.active_campaign_id:
        render_detail()
    elif st.session_state.view == "analytics":
        render_analytics()
    elif st.session_state.view == "script_editor":
        render_script_editor()
    elif st.session_state.view == "crf_converter":
        render_crf_converter()
    elif st.session_state.view == "landing":
        render_landing()
    else:
        render_dashboard()


if __name__ == "__main__":
    main()


