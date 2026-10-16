# app/views/crf_converter.py
"""CRF Converter view (Excel CRF -> campaign rows)."""

import copy as _copy
import io as _io
import json as _json
import re as _re
from datetime import datetime

import pandas as pd
import streamlit as st

from audit import log_change
from storage import create_campaign, list_campaigns, load_campaign, save_campaign
from ui import (
    REQUIRED_COLUMNS, TARGETING_COLUMNS, THEME_FIELD, _CRF_COLUMN_MAP,
    _CRF_IGNORE_COLS, _CRF_PLACEHOLDER_RE, _CRF_RICH_PUSH_TYPE_VALUES, _CRF_VALID_OFFER_TYPES,
    _EXCEL_TEXT_FORCE_COLS, _all_columns, _build_csv_bytes, _crf_clean_cell,
    _crf_expand_pushsection_cell, _crf_sanitize_offer_id, _current_channel, _get_crf_deep_link_extras,
    _import_csv_rows, _load_into_session, _new_row_id, _optional_columns,
    _parse_key_value_block, _promote_pushsection_offer_type, _pst_today, _sanitize_wk_id_key,
)


# ──────────────────────────────────────────────
# VIEW: CRF Converter (all roles)
# ──────────────────────────────────────────────

def _crf_normalize_header(h: str) -> str:
    """Normalize a CRF sheet header for tolerant lookup: lowercase, collapse whitespace."""
    return " ".join(str(h or "").strip().lower().split())


def _is_theme_placeholder(val: str) -> bool:
    """True if a Title/Message/URL/PushSection cell value is a canonical theme string used as fill-in text."""
    v = str(val or "").strip()
    if not v:
        return False
    return bool(_CRF_PLACEHOLDER_RE.match(v))


def _crf_new_sub_row(camp: dict, theme: str, content: dict) -> dict:
    """Build a PACE sub-row inheriting campaign-level fields plus the given theme + content."""
    sr = {c: "" for c in _all_columns()}
    sr["priority"] = camp["priority"]
    sr["campaign_name"] = camp["campaign_name"]
    sr["offer_type"] = camp["offer_type"]
    sr["offer_id"] = camp["offer_id"]
    sr["store_ids"] = camp["store_ids"]
    sr["theme"] = theme
    # Copy every content key that maps to a real PACE row column (title, message,
    # media_url, pushsection + any deep-link extras like param_q/screentitle/subtitle).
    for k, v in content.items():
        if k in sr and v not in (None, ""):
            sr[k] = v
    _promote_pushsection_offer_type(sr)
    sr["rich_push_image"] = bool(camp.get("is_rich_push")) or bool(sr["media_url"])
    for m in ("division_mode", "banner_mode", "store_mode"):
        sr[m] = "IN"
    sr["custom_sql"] = ""
    sr["div_banner_groups"] = []
    sr["custom_joins"] = []
    sr["extra_themes"] = []
    sr["targeting_notes"] = ""
    sr["multi_theme"] = False
    sr["sub_rows"] = []
    sr["handling_time"] = 0.0
    sr["row_type"] = "form"
    sr["sql_template_name"] = ""
    sr["_row_id"] = _new_row_id()
    return sr


def _crf_new_parent_row(camp: dict) -> dict:
    """Build a multi-theme container row from the campaign accumulator."""
    parent = {c: "" for c in _all_columns()}
    parent["priority"] = camp["priority"]
    parent["campaign_name"] = camp["campaign_name"]
    parent["offer_type"] = camp["offer_type"]
    parent["offer_id"] = camp["offer_id"]
    parent["store_ids"] = camp["store_ids"]
    parent["multi_theme"] = True
    for m in ("division_mode", "banner_mode", "store_mode"):
        parent[m] = "IN"
    parent["custom_sql"] = ""
    parent["div_banner_groups"] = []
    parent["custom_joins"] = []
    parent["extra_themes"] = []
    parent["targeting_notes"] = ""
    parent["rich_push_image"] = bool(camp.get("is_rich_push"))
    parent["handling_time"] = 0.0
    parent["row_type"] = "form"
    parent["sql_template_name"] = ""
    parent["_row_id"] = _new_row_id()
    return parent


def _crf_rows_from_dataframe(df: "pd.DataFrame") -> tuple[list[dict], list[str]]:
    """Convert a raw CRF DataFrame into PACE row dicts.

    Uses label/content classification instead of one-Excel-row-per-PACE-row:
    Label rows (title/message contain theme-name placeholders) set the current theme;
    Content rows (real title/message text) emit one PACE sub-row per row using the
    most recently established theme. Rows whose only non-blank cell is Targeting or
    Push Section are accumulated as campaign-level targeting notes.
    """
    warnings: list[str] = []

    header_to_field: dict[str, str] = {}
    unmapped_headers: list[str] = []
    for col in df.columns:
        norm = _crf_normalize_header(col)
        if not norm or norm in _CRF_IGNORE_COLS:
            continue
        if norm in _CRF_COLUMN_MAP:
            header_to_field[col] = _CRF_COLUMN_MAP[norm]
        else:
            unmapped_headers.append(str(col))
    if unmapped_headers:
        warnings.append("Unrecognized column(s) skipped: " + ", ".join(unmapped_headers))

    mapped_fields = set(header_to_field.values())
    missing_core = [f for f in ("campaign_name", "title", "message", "theme") if f not in mapped_fields]
    if missing_core:
        warnings.append("CRF is missing column(s) for: " + ", ".join(missing_core))

    campaigns: list[dict] = []
    current: dict | None = None
    current_theme: str = ""
    declared_themes: list[str] = []
    emitted_themes: set[str] = set()

    def flush_current():
        nonlocal current, current_theme, declared_themes, emitted_themes
        if current is None:
            return
        # Emit blank sub-rows for themes declared but never given content (form campaigns only).
        if not current.get("is_sql"):
            for t in declared_themes:
                if t not in emitted_themes:
                    warnings.append(f"P{current['priority']}: theme '{t}' declared but no content — blank sub-row emitted.")
                    current["sub_rows"].append(_crf_new_sub_row(current, t, {}))
            # If Push Section / media_url / deep-link extras arrived on the header row (or
            # continuation rows) but no content row ever gave us a sub-row, create a bare
            # sub-row to carry them so they aren't silently dropped.
            if current.get("_pending_extras") and not current["sub_rows"]:
                warnings.append(
                    f"P{current['priority']}: Push Section / media_url arrived without a content row "
                    "— blank sub-row emitted to carry them."
                )
                current["sub_rows"].append(_crf_new_sub_row(current, "", {}))
            # Drain any leftover pending extras into the first sub-row.
            if current.get("_pending_extras") and current["sub_rows"]:
                tgt = current["sub_rows"][0]
                for k, v in current["_pending_extras"].items():
                    if k in tgt and not tgt.get(k):
                        tgt[k] = v
                _promote_pushsection_offer_type(tgt)
                if tgt.get("media_url"):
                    tgt["rich_push_image"] = True
                current["_pending_extras"] = {}
        # Broadcast accumulated targeting notes to every sub-row.
        joined_notes = "\n".join(current["targeting_notes_list"]).strip()
        if joined_notes:
            for sr in current["sub_rows"]:
                sr["targeting_notes"] = joined_notes
            current["targeting_notes"] = joined_notes
        campaigns.append(current)
        current = None
        current_theme = ""
        declared_themes = []
        emitted_themes = set()

    for row_num, (_, csv_row) in enumerate(df.iterrows(), start=2):
        vals: dict[str, str] = {}
        for src_col, pace_field in header_to_field.items():
            raw = csv_row[src_col]
            v = str(raw).strip() if raw is not None else ""
            if pace_field in _EXCEL_TEXT_FORCE_COLS and v.startswith('="') and v.endswith('"'):
                v = v[2:-1]
            v = _crf_clean_cell(v)
            vals[pace_field] = v

        if vals.get("offer_id"):
            cleaned, dropped = _crf_sanitize_offer_id(vals["offer_id"])
            vals["offer_id"] = cleaned
            if dropped:
                snippet = dropped if len(dropped) <= 80 else dropped[:77] + "..."
                warnings.append(f"Row {row_num}: offer_id ignored (not in `NNN-X` format): {snippet}")

        # "Rich Push" in the Type column is not a valid offer_type — blank it out and remember
        # the flag so every emitted row for this campaign gets rich_push_image=True.
        row_is_rich_push = False
        if vals.get("offer_type"):
            norm = " ".join(vals["offer_type"].strip().lower().split())
            if norm in _CRF_RICH_PUSH_TYPE_VALUES:
                row_is_rich_push = True
                vals["offer_type"] = ""
            elif norm not in _CRF_VALID_OFFER_TYPES:
                # Non-PACE type value (e.g. "Push", "SMS") — blank so pushsection promotion can fire.
                vals["offer_type"] = ""
            else:
                # Normalise to canonical PACE casing.
                vals["offer_type"] = norm.upper()

        # Push Section cell may hold a Smart-Paste key=value block — expand into individual PACE fields.
        if vals.get("pushsection"):
            expanded, unknown_keys = _crf_expand_pushsection_cell(vals["pushsection"])
            if expanded:
                vals.pop("pushsection", None)
                for k, v in expanded.items():
                    if not vals.get(k):
                        vals[k] = v
            if unknown_keys:
                warnings.append(
                    f"Row {row_num}: Push Section unrecognised key(s) skipped: "
                    + ", ".join(sorted(set(unknown_keys)))
                )

        # Notes cell (mapped to CANONICALCAMPAIGNID) may hold a raw ID or a key=value block
        # like `canonicalcampaignid=abc; eventid=42`. Expand blocks; leave raw values alone.
        notes_val = vals.get("CANONICALCAMPAIGNID", "")
        if notes_val and "=" in notes_val:
            parsed, unknown_keys = _parse_key_value_block(notes_val)
            if parsed:
                vals.pop("CANONICALCAMPAIGNID", None)
                for k, v in parsed.items():
                    if not vals.get(k):
                        vals[k] = v
            if unknown_keys:
                warnings.append(
                    f"Row {row_num}: Notes unrecognised key(s) skipped: "
                    + ", ".join(sorted(set(unknown_keys)))
                )

        pri_raw = vals.get("priority", "")
        if pri_raw:
            flush_current()
            try:
                pri = int(float(pri_raw))
            except (ValueError, TypeError):
                pri = 0
                warnings.append(f"Row {row_num}: priority '{pri_raw}' is not numeric — defaulted to 0.")
            current = {
                "priority": pri,
                "campaign_name": vals.get("campaign_name", ""),
                "offer_type": vals.get("offer_type", ""),
                "offer_id": vals.get("offer_id", ""),
                "store_ids": vals.get("store_ids", ""),
                "CANONICALCAMPAIGNID": vals.get("CANONICALCAMPAIGNID", ""),
                "targeting_notes_list": [],
                "sub_rows": [],
                "is_sql": vals.get("row_type", "").strip().lower() == "sql",
                "is_rich_push": row_is_rich_push,
                "_pending_extras": {},
            }
            current_theme = ""
            declared_themes = []
            emitted_themes = set()

        if current is None:
            continue

        # Rich Push on any continuation row also flags the whole campaign.
        if row_is_rich_push:
            current["is_rich_push"] = True

        for f in ("campaign_name", "offer_type", "offer_id", "store_ids", "CANONICALCAMPAIGNID"):
            if vals.get(f):
                current[f] = vals[f]

        # SQL campaigns: skip label/content classifier and ignore the Targeting column entirely —
        # targeting for SQL rows is handled inside the .sql template, not via targeting_notes.
        if current.get("is_sql"):
            continue

        # Classify field cells: real content vs theme-name placeholder.
        placeholder_fields: list[tuple[str, str]] = []
        real_content: dict[str, str] = {}
        for f in ("title", "message", "media_url", "pushsection"):
            v = vals.get(f, "")
            if not v:
                continue
            if _is_theme_placeholder(v):
                placeholder_fields.append((f, v))
            else:
                real_content[f] = v
        # Deep-link extras from an expanded Push Section cell ride along with whatever the classifier emits.
        _crf_extras = _get_crf_deep_link_extras()
        for f in _crf_extras:
            v = vals.get(f, "")
            if v:
                real_content[f] = v

        theme_cell = vals.get("theme", "")
        has_real_content = bool(real_content.get("title") or real_content.get("message"))
        is_label_row = bool(placeholder_fields) and not has_real_content
        is_content_row = has_real_content

        # Non-placeholder Targeting text → accumulate as campaign-level notes.
        targ = vals.get("targeting_notes", "")
        if targ and not _is_theme_placeholder(targ):
            current["targeting_notes_list"].append(targ)
        # Push Section fragments spread across continuation rows (no title/message here):
        # merge into the most-recently-emitted sub-row, or buffer for the next one.
        if not is_content_row:
            extras: dict[str, str] = {}
            for f in ("pushsection", "media_url") + _crf_extras:
                v = real_content.get(f)
                if v:
                    extras[f] = v
            if extras:
                if current["sub_rows"]:
                    tgt = current["sub_rows"][-1]
                    for k, v in extras.items():
                        if k in tgt and not tgt.get(k):
                            tgt[k] = v
                    _promote_pushsection_offer_type(tgt)
                else:
                    current["_pending_extras"].update(
                        {k: v for k, v in extras.items() if k not in current["_pending_extras"]}
                    )

        if is_label_row and placeholder_fields:
            label_theme = placeholder_fields[0][1]
            current_theme = label_theme
            if label_theme not in declared_themes:
                declared_themes.append(label_theme)
        elif theme_cell and not is_content_row and not is_label_row:
            current_theme = theme_cell
            if theme_cell not in declared_themes:
                declared_themes.append(theme_cell)

        if is_content_row:
            row_theme = current_theme or theme_cell or ""
            if not row_theme:
                warnings.append(f"Row {row_num}: content row with no theme association — theme left blank.")
            sr = _crf_new_sub_row(current, row_theme, real_content)
            # Drain any Push Section extras that arrived before this content row.
            if current.get("_pending_extras"):
                for k, v in current["_pending_extras"].items():
                    if k in sr and not sr.get(k):
                        sr[k] = v
                current["_pending_extras"] = {}
                _promote_pushsection_offer_type(sr)
            current["sub_rows"].append(sr)
            if row_theme:
                emitted_themes.add(row_theme)
            # A Theme cell on a content row is a "next theme" declaration.
            if theme_cell and theme_cell != current_theme:
                if theme_cell not in declared_themes:
                    declared_themes.append(theme_cell)
                current_theme = theme_cell

    flush_current()

    # Convert each accumulated campaign into either a standalone row or a multi-theme container.
    output: list[dict] = []
    for camp in campaigns:
        if camp.get("is_sql"):
            sql_row = {c: "" for c in _all_columns()}
            sql_row["priority"] = camp["priority"]
            sql_row["campaign_name"] = camp["campaign_name"]
            sql_row["offer_type"] = camp["offer_type"]
            sql_row["offer_id"] = camp["offer_id"]
            sql_row["store_ids"] = camp["store_ids"]
            sql_row["CANONICALCAMPAIGNID"] = camp.get("CANONICALCAMPAIGNID", "")
            for m in ("division_mode", "banner_mode", "store_mode"):
                sql_row[m] = "IN"
            sql_row["custom_sql"] = ""
            sql_row["div_banner_groups"] = []
            sql_row["custom_joins"] = []
            sql_row["extra_themes"] = []
            sql_row["targeting_notes"] = ""
            sql_row["multi_theme"] = False
            sql_row["sub_rows"] = []
            sql_row["rich_push_image"] = bool(camp.get("is_rich_push"))
            sql_row["handling_time"] = 0.0
            sql_row["row_type"] = "sql"
            sql_row["sql_template_name"] = ""
            sql_row["_row_id"] = _new_row_id()
            output.append(sql_row)
            continue
        subs = camp["sub_rows"]
        if not subs:
            warnings.append(f"P{camp['priority']}: no content rows found — campaign skipped.")
            continue
        if len(subs) == 1:
            r = subs[0]
            r["multi_theme"] = False
            r["sub_rows"] = []
            output.append(r)
        else:
            parent = _crf_new_parent_row(camp)
            parent["sub_rows"] = subs
            parent["targeting_notes"] = camp.get("targeting_notes", "")
            output.append(parent)

    return output, warnings


def _crf_flatten_rows_for_csv(rows: list[dict]) -> list[dict]:
    """Flatten multi-theme containers back into simple rows for CSV export.

    Sub-rows share the container's priority, mirroring the _import_csv_rows()
    auto-grouping contract (import re-groups by shared priority).
    """
    flat: list[dict] = []
    for r in rows:
        if r.get("multi_theme") and r.get("sub_rows"):
            for sr in r["sub_rows"]:
                flat.append(sr)
        else:
            flat.append(r)
    return flat


def render_crf_converter():
    """Convert a manually-prepared CRF .xlsx into a PACE-importable CSV."""
    st.header("📋 CRF Converter")

    if _current_channel() == "rcs":
        col_back, _ = st.columns([1, 5])
        with col_back:
            if st.button("← Dashboard", key="crf_back_btn"):
                st.session_state.view = "dashboard"
                st.rerun()
        st.info(
            "🚧 **RCS CRF Converter — coming soon.**\n\n"
            "The CRF Converter is currently PUSH-only. RCS support will be added once a "
            "sample RCS CRF spreadsheet is provided so the column mapping can be authored."
        )
        return

    st.caption(
        "Upload a CRF Excel file (`.xlsx`) with headers on row 1. "
        "The converter maps CRF columns to PACE row fields and produces a CSV you can "
        "import from the campaign detail view using the **📤 Import CSV** button."
    )

    col_back, _ = st.columns([1, 5])
    with col_back:
        if st.button("← Dashboard", key="crf_back_btn"):
            st.session_state.view = "dashboard"
            st.rerun()

    with st.expander("Expected CRF columns", expanded=False):
        st.markdown(
            "**Used:** " + ", ".join(
                sorted({v for v in _CRF_COLUMN_MAP.values()})
            ) + "\n\n"
            "**Ignored:** " + ", ".join(sorted(_CRF_IGNORE_COLS)) + "\n\n"
            "**Header matching** is case- and whitespace-insensitive. "
            "The `Type` column must be pre-filled with a valid PACE value "
            "(`PERSONALIZED DEAL`, `STORE COUPON`, `PUSHSECTION`, or blank).\n\n"
            "**Row Type column** (optional, placed just before `Type`): set to `sql` "
            "on the priority row of a SQL-template campaign. All Title/Message/Theme/Media URL "
            "cells in that campaign block are ignored; only campaign metadata and Targeting "
            "notes are kept. Leave blank (or set to `form`) for standard PACE form rows."
        )

    uploaded = st.file_uploader(
        "Upload CRF file",
        type=["xlsx"],
        key="crf_upload",
        accept_multiple_files=False,
    )

    if not uploaded:
        st.info("Upload a CRF file to begin.")
        return

    # Cache the parsed result keyed by uploaded file identity to avoid re-parsing on every rerun.
    # Bump _CRF_PARSER_VERSION whenever the parser logic changes to auto-invalidate stale caches.
    _CRF_PARSER_VERSION = "v13-pending-extras-flush-drain"
    dedup_key = f"{_CRF_PARSER_VERSION}|{uploaded.name}|{uploaded.size}"
    cache = st.session_state.get("_crf_cache", {})
    if cache.get("key") != dedup_key:
        try:
            df_raw = pd.read_excel(
                uploaded,
                sheet_name=0,
                dtype=str,
                header=0,
                keep_default_na=False,
                engine="openpyxl",
            )
        except Exception as exc:
            st.error(f"Failed to read Excel file: {exc}")
            return
        rows, warnings = _crf_rows_from_dataframe(df_raw)
        cache = {"key": dedup_key, "rows": rows, "warnings": warnings}
        st.session_state["_crf_cache"] = cache

    rows: list[dict] = cache["rows"]
    warnings: list[str] = cache["warnings"]

    if not rows:
        st.error("No usable rows found in the CRF. Check that headers are on row 1 and that required columns are present.")
        if warnings:
            with st.expander("Parse warnings", expanded=True):
                for w in warnings:
                    st.write(f"• {w}")
        return

    # Build the export DataFrame in the exact same column order as _build_csv_bytes/visible_cols.
    flat_rows = _crf_flatten_rows_for_csv(rows)
    export_cols = (
        ["priority", "row_type", "rich_push_image", "offer_type", "offer_id"]
        + REQUIRED_COLUMNS + [THEME_FIELD] + _optional_columns() + TARGETING_COLUMNS
        + ["div_banner_groups", "custom_joins", "extra_themes", "targeting_notes"]
    )
    df_export = pd.DataFrame(flat_rows)
    for col in export_cols:
        if col not in df_export.columns:
            df_export[col] = ""
    # Serialize list fields as JSON strings so the existing importer can round-trip them.
    for col in ("div_banner_groups", "custom_joins", "extra_themes"):
        df_export[col] = df_export[col].apply(
            lambda v: _json.dumps(v) if isinstance(v, list) and v else ""
        )
    df_export["rich_push_image"] = df_export["rich_push_image"].apply(
        lambda v: "Y" if bool(v) else "N"
    )
    df_export = df_export[export_cols]

    # Summary + warnings
    total_rows = len(rows)
    total_flat = len(flat_rows)
    st.success(
        f"Converted **{total_rows}** row(s) "
        + (f"({total_flat} after flattening multi-theme containers)" if total_flat != total_rows else "")
        + "."
    )
    if warnings:
        with st.expander(f"⚠ {len(warnings)} parse warning(s)", expanded=False):
            for w in warnings:
                st.write(f"• {w}")

    st.subheader("Preview")
    st.caption(
        "Edit any cell before downloading or injecting. Complex fields "
        "(`div_banner_groups`, `custom_joins`, `extra_themes`) are shown as JSON strings — "
        "keep valid JSON if you change them. Priority collisions auto-group into multi-theme "
        "containers on import, matching CSV import behaviour."
    )
    edited_df = st.data_editor(
        df_export,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        key="crf_preview_editor",
    )

    # Filename derives from the uploaded CRF's stem so the CSV is easy to trace back.
    upload_stem = _re.sub(r"\.xlsx$", "", uploaded.name, flags=_re.IGNORECASE) or "CRF"
    fname = f"{upload_stem}_CRF_import.csv"

    csv_bytes = _build_csv_bytes(edited_df, save_path=None)

    # Roundtrip edited CSV bytes back through the standard importer so injection paths
    # pick up user edits AND re-apply priority-collision multi-theme grouping.
    try:
        _bio = _io.BytesIO(csv_bytes)
        injectable_rows, edit_warnings = _import_csv_rows(_bio)
    except Exception as exc:
        st.error(f"Could not parse edited preview: {exc}")
        injectable_rows = _copy.deepcopy(rows)
        edit_warnings = []
    if edit_warnings:
        with st.expander(f"⚠ {len(edit_warnings)} edit warning(s)", expanded=False):
            for w in edit_warnings:
                st.write(f"• {w}")
    st.download_button(
        "⬇ Download CSV for Import",
        data=csv_bytes,
        file_name=fname,
        mime="text/csv",
        key="crf_download_btn",
        use_container_width=False,
    )
    st.caption(
        "Next: open the target campaign day and use **📤 Import CSV** in the detail view "
        "to load these rows."
    )

    # ---- Direct injection into a campaign day ----
    st.markdown("---")
    st.subheader("🎯 Inject directly into a campaign day")
    st.caption(
        "Skip the CSV round-trip: push these rows into an existing campaign day, "
        "or create a brand-new one right here."
    )

    def _fmt_campaign(c: dict) -> str:
        wk = c.get("wk_id", "") or "—"
        sd = c.get("send_date", "") or "—"
        sday = c.get("send_day", "") or ""
        status = c.get("status", "Draft")
        nrows = len(c.get("rows", []))
        return f"{wk} · {sd} {sday} · {status} · {nrows} row(s)"

    inject_target = st.radio(
        "Target",
        options=["Existing campaign day", "Create new campaign day"],
        index=0,
        key="crf_inject_target_mode",
        horizontal=True,
    )

    # --- Branch A: create a new campaign day and inject into it ---
    if inject_target == "Create new campaign day":
        nc_col1, nc_col2 = st.columns([1, 1])
        with nc_col1:
            new_wk_id = st.text_input(
                "Week ID (YYYYWW)",
                key="crf_new_wk_id",
                max_chars=6,
                on_change=_sanitize_wk_id_key,
                args=("crf_new_wk_id",),
                help="6 digits only (YYYYWW), e.g. 202629",
            )
        with nc_col2:
            _today_pst = _pst_today()
            new_send_date = st.date_input(
                "Send Date",
                value=_today_pst,
                min_value=_today_pst,
                key="crf_new_send_date",
                help="Send Date must be today or later (PST). Past dates are blocked.",
            )

        if st.button("🚀 Create campaign day & inject rows", key="crf_create_inject_btn", type="primary"):
            new_wk_id = (new_wk_id or "").strip()
            if not new_wk_id:
                st.error("Week ID is required.")
                st.stop()
            if not (len(new_wk_id) == 6 and new_wk_id.isdigit()):
                st.error("Week ID must be exactly 6 digits (YYYYWW), e.g. `202614`.")
                st.stop()
            if new_send_date < _pst_today():
                st.error("Send Date cannot be in the past. Pick today or a future date.")
                st.stop()
            send_day = new_send_date.strftime("%A").upper()
            existing = list_campaigns()
            dup = next(
                (c for c in existing
                 if c.get("wk_id") == new_wk_id
                 and c.get("send_date") == str(new_send_date)),
                None,
            )
            if dup:
                st.error(
                    f"A campaign day already exists for **Week {new_wk_id}** / "
                    f"**{new_send_date.strftime('%b %d, %Y')}** ({send_day}). "
                    f"Status: {dup.get('status', 'Draft')}. "
                    "Switch to **Existing campaign day** and pick it from the list instead."
                )
                st.stop()
            target = create_campaign(
                wk_id=new_wk_id,
                send_date=str(new_send_date),
                send_day=send_day,
            )
            injected = _copy.deepcopy(injectable_rows)
            for i, r in enumerate(injected, start=1):
                r["priority"] = i
                for sr in r.get("sub_rows", []) or []:
                    sr["priority"] = i
            target["rows"] = injected
            log_change(
                target.setdefault("audit", []),
                action="crf_inject",
                before=[],
                after=target["rows"],
                details=f"Created campaign day and injected {len(injected)} row(s) from CRF Converter",
            )
            target.setdefault("activity_log", []).append({
                "action": f"CRF Created & Injected ({len(injected)} row(s))",
                "ts": datetime.now().isoformat(),
            })
            target["updated_at"] = datetime.now().isoformat()
            save_campaign(target)
            st.session_state.pop("_crf_cache", None)
            _load_into_session(target)
            st.session_state.view = "detail"
            st.success(
                f"Created campaign day {_fmt_campaign(target)} and injected {len(injected)} row(s). "
                "Opening it now…"
            )
            st.rerun()
        return

    # --- Branch B: inject into an existing campaign day ---
    all_campaigns = list_campaigns()
    if not all_campaigns:
        st.info("No campaign days exist yet — switch to **Create new campaign day** above to make one now.")
        return

    _CRF_INJECTABLE_STATUSES = {"Draft", "Pending Assets"}
    injectable = [c for c in all_campaigns if c.get("status", "Draft") in _CRF_INJECTABLE_STATUSES]
    if not injectable:
        st.info(
            f"No campaign days are eligible for injection. Only campaigns in "
            f"**{', '.join(sorted(_CRF_INJECTABLE_STATUSES))}** status can receive CRF rows. "
            "Switch to **Create new campaign day** above to make a fresh one."
        )
        return

    id_to_campaign = {c["id"]: c for c in injectable}
    ids = list(id_to_campaign.keys())
    target_id = st.selectbox(
        "Target campaign day",
        options=ids,
        format_func=lambda cid: _fmt_campaign(id_to_campaign[cid]),
        key="crf_inject_target",
    )
    mode = st.radio(
        "Injection mode",
        options=["Append to existing rows", "Replace all existing rows"],
        index=0,
        key="crf_inject_mode",
        horizontal=True,
    )

    confirm_key = "crf_inject_confirm"
    replace_mode = mode.startswith("Replace")
    if replace_mode:
        st.warning(
            f"This will **delete all {len(id_to_campaign[target_id].get('rows', []))} existing row(s)** "
            f"in the target campaign day and replace them with the {len(injectable_rows)} parsed row(s)."
        )
        confirmed = st.checkbox("Yes, replace all rows", key=confirm_key)
    else:
        confirmed = True

    if st.button("🚀 Inject rows", key="crf_inject_btn", disabled=not confirmed):
        target = load_campaign(target_id)
        if target is None:
            st.error("Target campaign day could not be loaded (was it just deleted?).")
            return
        # Deep-copy so we don't mutate the cached rows in session state.
        injected = _copy.deepcopy(injectable_rows)
        before = list(target.get("rows", []))
        if replace_mode:
            target["rows"] = []
        start_pri = len(target["rows"]) + 1
        for i, r in enumerate(injected):
            new_pri = start_pri + i
            r["priority"] = new_pri
            for sr in r.get("sub_rows", []) or []:
                sr["priority"] = new_pri
            target["rows"].append(r)
        # Audit + activity log entries on the target campaign.
        log_change(
            target.setdefault("audit", []),
            action="crf_inject",
            before=before,
            after=target["rows"],
            details=f"Injected {len(injected)} row(s) from CRF Converter ({'replace' if replace_mode else 'append'})",
        )
        target.setdefault("activity_log", []).append({
            "action": f"CRF Injected ({len(injected)} row(s), {'replace' if replace_mode else 'append'})",
            "ts": datetime.now().isoformat(),
        })
        target["updated_at"] = datetime.now().isoformat()
        save_campaign(target)
        st.session_state.pop("_crf_cache", None)
        _load_into_session(target)
        st.session_state.view = "detail"
        st.success(
            f"Injected {len(injected)} row(s) into {_fmt_campaign(target)}. "
            "Opening the campaign day now…"
        )
        st.rerun()
