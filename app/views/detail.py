# app/views/detail.py
"""Campaign Detail view: row forms (PUSH + RCS) and Review & Export."""

import copy as _copy
import json as _json
import re as _re
from datetime import date, datetime

import pandas as pd
import streamlit as st

from audit import _friendly_ts, diff_rows, log_change
from compose import (
    _escape_sql_strings, _expand_extra_themes, _expand_offer_ids, _inject_notes_after_from,
    _load_optional_columns, _override_canonicalcampaignid, _targeting_notes_comment, build_rcs_sql,
    build_sql, render_campaign_insert, render_rcs_campaign_insert,
)
from renderer import create_permissive_env
from storage import load_campaign
from ui import (
    JOIN_COLUMNS, REQUIRED_COLUMNS, TARGETING_COLUMNS, THEME_FIELD,
    _LOCKED_FOR_USER, _accumulate_handling_time, _all_columns, _apply_pending_widget_clear,
    _btn_color, _build_csv_bytes, _channel_export_prefix, _clear_row_widget_state,
    _config_dir, _csv_dir, _current_channel, _format_handling_time,
    _import_csv_rows, _invalidate_sql_on_template_change, _is_developer, _is_user_locked,
    _load_into_session, _load_optional_columns_cfg, _load_rcs_tables_cfg, _new_row_id,
    _note_external_change, _offer_template_fingerprint, _optional_columns, _render_preqc_scorecard,
    _render_prior_week_panel, _run_preqc, _sanitize_wk_id_key, _save_from_session,
    _sql_exports_dir, _sql_templates_dir, _status_badge, _trim_whitespace_fields,
    jinja_env, load_sql_templates, load_tables,
)
from views.detail_push import _render_row_form


# ──────────────────────────────────────────────
# VIEW: Campaign Day Detail (the original editor)
# ──────────────────────────────────────────────

def render_detail():
    # Flush any pending widget-state clear BEFORE widgets render
    _apply_pending_widget_clear()

    # Accumulate handling time for the previously-active row
    _accumulate_handling_time()

    is_dev = _is_developer()
    cid = st.session_state.get("active_campaign_id")
    if not cid:
        st.session_state.view = "dashboard"
        st.rerun()

    # Re-hydrate session state from disk after a full page refresh so that
    # status (and other fields) aren't lost and defaulted back to "Draft".
    if "campaign_status" not in st.session_state:
        campaign = load_campaign(cid)
        if campaign:
            _load_into_session(campaign)
        else:
            st.session_state.view = "dashboard"
            st.rerun()
    else:
        _note_external_change(load_campaign(cid) or {})

    conflict = st.session_state.get("_save_conflict")
    if conflict:
        warn_col, btn_col = st.columns([4, 1], vertical_alignment="center")
        with warn_col:
            st.warning(
                "⚠️ This campaign day was modified elsewhere (another tab, user, or the dashboard) "
                f"at {_friendly_ts(conflict['at'])} while you had it open — your edits replaced that version. "
                "Restore the other version (discards your edits), or keep yours."
            )
        with btn_col:
            if st.button("↩️ Restore other version", key="save_conflict_restore"):
                _clear_row_widget_state()
                _load_into_session(conflict["other"])
                st.session_state.pop("_loaded_updated_at", None)
                _save_from_session(activity_event="Restored version from concurrent edit")
                st.rerun()
            if st.button("Keep mine", key="save_conflict_keep"):
                st.session_state.pop("_save_conflict", None)
                st.rerun()

    # ---- Back button + auto-save ----
    back_col, title_col, status_col = st.columns([0.8, 3, 1.5])
    with back_col:
        if st.button("← Dashboard"):
            _accumulate_handling_time()  # flush time before leaving
            _save_from_session(activity_event="Saved")
            st.session_state.view = "dashboard"
            st.session_state.generated_sql = ""
            st.rerun()
    with title_col:
        send_d_str = st.session_state.get("send_date", "")
        send_day = st.session_state.get("send_day", "")
        st.markdown(
            f"""
            <div style="margin:0;">
                <div style="font-size:0.72em;color:var(--pace-text-muted);letter-spacing:0.10em;
                            text-transform:uppercase;font-weight:600;">
                    Campaign Day
                </div>
                <div style="font-size:1.7em;font-weight:800;letter-spacing:-0.02em;line-height:1.15;
                            color:var(--pace-text);">
                    {send_d_str} <span style="color:var(--pace-text-muted);font-weight:600;font-size:0.72em;">· {send_day}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with status_col:
        cur_status = st.session_state.get("campaign_status", "Draft")
        badge_html = _status_badge(cur_status)
        st.markdown(f"<div style='padding-top:6px;text-align:right;'>{badge_html}</div>", unsafe_allow_html=True)

    # ---- User-lock check ----
    user_locked = _is_user_locked()
    if user_locked:
        st.warning(
            f"This campaign day is **{cur_status}** and locked for editing. "
            f"A Developer must unlock it before you can make changes.",
            icon="🔒",
        )

    # ---- Header fields (card container) ----
    with st.container(border=True):
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if "detail_wk_id" not in st.session_state:
                st.session_state["detail_wk_id"] = st.session_state.get("wk_id", "")
            _wk_id_input = st.text_input(
                "Week ID (YYYYWW)",
                key="detail_wk_id",
                max_chars=6,
                on_change=_sanitize_wk_id_key,
                args=("detail_wk_id",),
                disabled=user_locked,
                help="6 digits only (YYYYWW), e.g. 202629",
            )
            _wk_id_stripped = _wk_id_input.strip()
            if not _wk_id_stripped:
                st.error("Week ID is required.")
            elif not (len(_wk_id_stripped) == 6 and _wk_id_stripped.isdigit()):
                st.error("Week ID must be exactly 6 digits (YYYYWW), e.g. `202614`.")
            else:
                st.session_state.wk_id = _wk_id_stripped
        with col2:
            chosen_date = st.date_input("Send Date", value=st.session_state.get("send_date", date.today()), disabled=user_locked)
            if not user_locked:
                st.session_state.send_date = chosen_date
                st.session_state.send_day = chosen_date.strftime("%A").upper()
        with col3:
            st.text_input("Send Day", value=st.session_state.get("send_day", ""), disabled=True)

    # ---- Last saved indicator (#10) ----
    last_saved = st.session_state.get("last_saved_at", "")
    if last_saved:
        st.caption(f"💾 Last saved: {last_saved}")

    # ── Early exit for locked Users: show rows read-only, hide edit controls ──
    if user_locked:
        st.subheader("Campaign Rows (read-only)")
        rows = st.session_state.get("rows", [])
        if not rows:
            st.info("No rows in this campaign day.")
        for i, r in enumerate(rows):
            label = r.get("campaign_name") or f"Row {i+1}"
            row_type = "sql" if r.get("custom_sql") else "form"
            with st.expander(f"Row {i+1} — {label}  `[{row_type}]`", expanded=False):
                # Handling time
                ht = r.get("handling_time", 0.0)
                if ht:
                    st.caption(f"⏱️ Active edit time: {_format_handling_time(ht)}")
                for fld in REQUIRED_COLUMNS + [THEME_FIELD] + JOIN_COLUMNS:
                    val = r.get(fld) or ""
                    if val:
                        st.markdown(f"**{fld}**: {val}")
                for fld in _optional_columns():
                    val = r.get(fld) or ""
                    if val:
                        st.markdown(f"**{fld}**: {val}")
                # Targeting summary
                tgt = []
                for fld in ("division_ids", "banners", "store_ids"):
                    v = (r.get(fld) or "").strip()
                    if v:
                        mode = r.get(fld.replace("_ids", "_mode").replace("banners", "banner_mode"), "IN")
                        tgt.append(f"{fld} {mode} ({v})")
                if tgt:
                    st.markdown("**Targeting**: " + " · ".join(tgt))

        # Show PreQC as info even while locked (helpful for the developer handoff)
        st.divider()
        st.subheader("Pre-QC Report")
        preqc_report = _run_preqc(
            rows,
            st.session_state.get("wk_id", ""),
            st.session_state.get("send_day", ""),
            sql_overrides=st.session_state.get("sql_overrides", {}),
            include_placeholder=True,
            current_campaign_id=cid,
            current_send_date=str(st.session_state.get("send_date", "") or ""),
        )
        _render_preqc_scorecard(preqc_report, row_count=len(rows))

        # Skip the rest of the User editing section — jump to Developer section below
        if is_dev:
            pass  # fall through
        else:
            return

    st.subheader("Campaign Rows")

    # ---- SQL Template Library ----
    sql_templates = load_sql_templates()
    if sql_templates:
        with st.expander("Load from Recurring SQL Template Library", expanded=False):
            st.caption("Select pre-built SQL files from `sql_templates/` to add as custom SQL rows.")
            sql_tpl_names = list(sql_templates.keys())
            # Clear multiselect on the render cycle after templates were added
            _tpl_default = [] if st.session_state.pop("_clear_sql_tpl_select", False) else None
            selected_sql = st.multiselect(
                "Select SQL templates",
                options=sql_tpl_names,
                key="sql_template_select",
                default=_tpl_default,
            )
            if st.button("Add selected SQL templates") and selected_sql:
                before = list(st.session_state.rows)
                for name in selected_sql:
                    new_row = {c: "" for c in _all_columns()}
                    new_row["priority"] = len(st.session_state.rows) + 1
                    new_row["campaign_name"] = name
                    new_row["theme"] = ""
                    new_row["custom_sql"] = sql_templates[name]
                    new_row["sql_template_name"] = name
                    new_row["division_mode"] = "IN"
                    new_row["banner_mode"] = "IN"
                    new_row["store_mode"] = "IN"
                    new_row["div_banner_groups"] = []
                    new_row["custom_joins"] = []
                    new_row["extra_themes"] = []
                    new_row["multi_theme"] = False
                    new_row["sub_rows"] = []
                    new_row["handling_time"] = 0.0
                    new_row["_row_id"] = _new_row_id()
                    st.session_state.rows.append(new_row)
                log_change(st.session_state.audit, action="add_from_sql_template",
                           before=before, after=st.session_state.rows,
                           details={"sql_templates": selected_sql})
                _save_from_session()
                _clear_row_widget_state()
                st.session_state["_clear_sql_tpl_select"] = True
                st.rerun()
            st.divider()
            uploaded_sql = st.file_uploader("Upload a .sql file to the library", type=["sql"], key="sql_upload")
            if uploaded_sql and st.button("Save to sql_templates/"):
                dest = _sql_templates_dir() / uploaded_sql.name
                dest.write_bytes(uploaded_sql.getvalue())
                load_sql_templates.clear()
                st.success(f"Saved `{uploaded_sql.name}` to sql_templates/. Refresh to see it in the list.")
                st.rerun()

    # ---- Optional Column Schema Editor (Developer only) ----
    if is_dev:
        with st.expander("⚙️ Optional Column Schema (Developer)", expanded=False):
            st.caption(
                "Add new optional columns to the campaign INSERT `SELECT` list. "
                "Each entry appends to `config/optional_columns.yaml` and appears in "
                "Optional Fields immediately on next interaction."
            )
            _ocs_all = _load_optional_columns_cfg()
            _ocs_loop = [c for c in _ocs_all if c.get("sql_managed", "loop") == "loop" and c.get("ui_visible", True)]
            if _ocs_loop:
                st.markdown("**Current loop-managed optional columns:**")
                st.dataframe(
                    [
                        {
                            "name": c["name"],
                            "label": c.get("label", c["name"]),
                            "sql_alias": c.get("sql_alias", ""),
                            "sql_type": c.get("sql_type", "text"),
                            "sql_escape": "✓" if c.get("sql_escape") else "",
                            "help": c.get("help", ""),
                        }
                        for c in _ocs_loop
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            st.markdown("---")
            st.markdown("**Add a new optional column:**")
            _ncc1, _ncc2, _ncc3 = st.columns(3)
            with _ncc1:
                _new_col_name = st.text_input("Field name *", key="ocs_name", placeholder="e.g. brandid")
            with _ncc2:
                _new_col_label = st.text_input("UI label", key="ocs_label", placeholder="Defaults to field name")
            with _ncc3:
                _new_col_alias = st.text_input("SQL alias", key="ocs_alias", placeholder="Defaults to field name")
            _nca1, _nca2, _nca3 = st.columns(3)
            with _nca1:
                _new_col_type = st.selectbox("SQL type", options=["text", "bool"], key="ocs_type")
            with _nca2:
                _new_col_escape = st.checkbox("Escape apostrophes (sql_escape)", key="ocs_escape")
            with _nca3:
                _new_col_help = st.text_input("Help text (tooltip)", key="ocs_help")
            if st.button("＋ Add Column to Schema", key="ocs_add", type="primary"):
                _cname = (_new_col_name or "").strip()
                if not _cname:
                    st.error("Field name is required.")
                elif not _re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", _cname):
                    st.error("Field name must be a valid identifier (letters, digits, underscores only — no spaces).")
                elif _cname in [c["name"] for c in _ocs_all]:
                    st.error(f"Column '{_cname}' already exists in the schema.")
                else:
                    _clabel = (_new_col_label or "").strip() or _cname
                    _calias = (_new_col_alias or "").strip()
                    _chelp = (_new_col_help or "").strip()
                    _new_lines = [f"\n  - name: {_cname}\n"]
                    if _new_col_type != "text":
                        _new_lines.append(f"    sql_type: {_new_col_type}\n")
                    if _new_col_escape:
                        _new_lines.append(f"    sql_escape: true\n")
                    if _calias:
                        _new_lines.append(f"    sql_alias: {_calias}\n")
                    _new_lines.append(f"    label: {_clabel}\n")
                    if _chelp:
                        _new_lines.append(f'    help: "{_chelp}"\n')
                    _ocs_path = _config_dir() / "optional_columns.yaml"
                    with open(_ocs_path, "a", encoding="utf-8") as _yf:
                        _yf.writelines(_new_lines)
                    _load_optional_columns.cache_clear()
                    _load_optional_columns_cfg.cache_clear()
                    st.success(f"✅ Column '{_cname}' added to schema. It will appear in Optional Fields immediately.")
                    st.rerun()

    # ---- In-App SQL Template Editor (Developer only) ----
    if sql_templates and is_dev:
        # Available placeholder tokens mapped to their row/campaign column
        _PLACEHOLDER_TOKENS = [
            "{{ title }}", "{{ theme }}", "{{ message }}", "{{ media_url }}", "{{ pushsection }}",
            "{{ param_q }}", "{{ screentitle }}", "{{ subtitle }}", "{{ offer_type }}",
            "{{ offer_id }}", "{{ gameid }}", "{{ product }}", "{{ searchterm }}",
            "{{ store }}", "{{ seller }}", "{{ category }}", "{{ program }}",
            "{{ pagename }}", "{{ datasource }}", "{{ modelconfigid }}", "{{ partnerid }}",
        ]

        with st.expander("🔧 Edit SQL Template Library (Developer)", expanded=False):
            st.caption(
                "Open any `.sql` file from the library, swap hardcoded weekly values "
                "for Jinja2 placeholders using the converter below, then save back to disk."
            )

            tpl_names = list(sql_templates.keys())
            sel_tpl = st.selectbox("Select template to edit", options=tpl_names, key="tpl_editor_select")

            # Initialize working copy in session state
            _wk_key = "tpl_editor_working"
            _orig_key = "tpl_editor_orig"
            _name_key = "tpl_editor_name"

            # Bypass the 60s cache and read straight from disk so the editor
            # never shows a stale snapshot when the file changed underneath us.
            _tpl_path = _sql_templates_dir() / f"{sel_tpl}.sql"
            try:
                _disk_sql = _tpl_path.read_text(encoding="utf-8")
            except OSError:
                _disk_sql = sql_templates.get(sel_tpl, "")

            _switched_template = st.session_state.get(_name_key) != sel_tpl
            _first_open = _wk_key not in st.session_state
            _disk_changed = (
                not _switched_template
                and not _first_open
                and _disk_sql != st.session_state.get(_orig_key)
            )
            _has_unsaved = (
                not _first_open
                and st.session_state.get(_wk_key) != st.session_state.get(_orig_key)
            )

            if _switched_template or _first_open:
                st.session_state[_wk_key] = _disk_sql
                st.session_state[_orig_key] = _disk_sql
                st.session_state[_name_key] = sel_tpl
            elif _disk_changed and not _has_unsaved:
                st.session_state[_wk_key] = _disk_sql
                st.session_state[_orig_key] = _disk_sql
                st.info("🔄 Template refreshed — the file on disk changed since you opened the editor.")
            elif _disk_changed and _has_unsaved:
                st.warning(
                    "⚠️ The file on disk changed since you opened this template, but you have "
                    "unsaved edits in the editor. Save to overwrite, or use **Revert** to discard "
                    "your edits and reload the current disk version."
                )
                # Update the baseline so Revert reloads from the newest disk content.
                st.session_state[_orig_key] = _disk_sql

            # --- Find & Replace converter ---
            st.markdown("**Placeholder Converter** — replace a hardcoded value with a `{{ }}` token:")
            conv_col1, conv_col2, conv_col3 = st.columns([1.2, 2, 0.6])
            with conv_col1:
                chosen_token = st.selectbox(
                    "Target placeholder",
                    options=_PLACEHOLDER_TOKENS,
                    key="tpl_conv_token",
                )
            with conv_col2:
                find_value = st.text_input(
                    "Hardcoded value to replace",
                    key="tpl_conv_find",
                    placeholder="e.g. loy-lty_bp-wk05_2026",
                )
            with conv_col3:
                st.write("")  # spacing
                if st.button("Apply", key="tpl_conv_apply"):
                    if find_value and find_value in st.session_state[_wk_key]:
                        st.session_state[_wk_key] = st.session_state[_wk_key].replace(
                            find_value, chosen_token
                        )
                        st.success(f"Replaced all occurrences of `{find_value}` → `{chosen_token}`")
                        st.rerun()
                    elif find_value:
                        st.warning("Value not found in the current template text.")

            # Show current working SQL
            st.markdown("**Current template content** (read-only preview):")
            st.code(st.session_state[_wk_key], language="sql")

            # Save / Revert buttons
            sv_col, rv_col = st.columns(2)
            with sv_col:
                if st.button("💾 Save changes to library", key="tpl_editor_save", type="primary"):
                    dest = _sql_templates_dir() / f"{sel_tpl}.sql"
                    dest.write_text(st.session_state[_wk_key], encoding="utf-8")
                    st.session_state[_orig_key] = st.session_state[_wk_key]
                    load_sql_templates.clear()
                    st.success(f"Saved `{sel_tpl}.sql` to sql_templates/.")
                    st.rerun()
            with rv_col:
                if st.button("↩ Revert to last saved", key="tpl_editor_revert"):
                    st.session_state[_wk_key] = st.session_state[_orig_key]
                    st.rerun()

            # Help note
            st.info(
                "**Available placeholders:** "
                + ", ".join(f"`{t}`" for t in _PLACEHOLDER_TOKENS)
                + "\n\nEach maps to the column of the same name in the campaign row table "
                "(or a campaign-level field like `wk_id` / `send_date`)."
            )

    # ---- Add / Remove / Import Row Controls ----
    with st.container(border=True):
        _ar_col1, _ar_col2, _ar_col3, _ar_col4 = st.columns([1, 2, 4, 2], vertical_alignment="bottom")
        with _ar_col1:
            add_count = st.number_input("Rows to add", min_value=1, max_value=50, value=1, step=1, key="add_row_count", label_visibility="collapsed")
        with _ar_col2:
            _add_clicked = st.button("➕ Add blank row(s)")
        with _ar_col3:
            if st.session_state.rows:
                row_labels = [f"Row {i+1} — {r.get('campaign_name') or '(empty)'}" for i, r in enumerate(st.session_state.rows)]
                remove_selection = st.selectbox("Select row to remove", options=range(len(row_labels)), format_func=lambda i: row_labels[i], key="remove_row_select", label_visibility="collapsed")
            else:
                row_labels = []
                remove_selection = None
        with _ar_col4:
            if st.session_state.rows:
                _btn_color("red")
                _remove_clicked = st.button("🗑️ Remove selected row", type="secondary")
            else:
                _remove_clicked = False

    if _add_clicked:
        before = list(st.session_state.rows)
        for _ in range(int(add_count)):
            new_row = {c: "" for c in _all_columns()}
            new_row["priority"] = len(st.session_state.rows) + 1
            new_row["autoimage"] = ""
            new_row["division_mode"] = "IN"
            new_row["banner_mode"] = "IN"
            new_row["store_mode"] = "IN"
            new_row["div_banner_groups"] = []
            new_row["custom_joins"] = []
            new_row["extra_themes"] = []
            new_row["multi_theme"] = False
            new_row["sub_rows"] = []
            new_row["handling_time"] = 0.0
            new_row["_row_id"] = _new_row_id()
            st.session_state.rows.append(new_row)
        log_change(st.session_state.audit, action="add_row", before=before, after=st.session_state.rows)
        _save_from_session()
        _clear_row_widget_state()
        st.rerun()

    if _remove_clicked:
        st.session_state["confirm_remove_row"] = True
    if st.session_state.get("confirm_remove_row") and row_labels:
        st.warning(f"⚠️ Remove **{row_labels[remove_selection]}**?")
        rc1, rc2 = st.columns(2)
        with rc1:
            _btn_color("red")
            if st.button("Yes, remove", key="confirm_remove_yes", type="primary"):
                before = list(st.session_state.rows)
                removed = st.session_state.rows.pop(remove_selection)
                for i, r in enumerate(st.session_state.rows):
                    r["priority"] = i + 1
                log_change(st.session_state.audit, action="remove_row", before=before, after=st.session_state.rows, details={"removed": removed})
                st.session_state.pop("confirm_remove_row", None)
                _save_from_session()
                _clear_row_widget_state()
                st.session_state.pop("generated_sql", None)
                st.rerun()
        if rc2.button("Cancel", key="confirm_remove_no"):
            st.session_state.pop("confirm_remove_row", None)
            st.rerun()

    # ---- Display CSV import warnings from previous import ----
    if st.session_state.get("_csv_import_warnings"):
        _imp_warns = st.session_state.pop("_csv_import_warnings")
        with st.expander(f"⚠️ CSV import: {len(_imp_warns)} field(s) could not be parsed", expanded=True):
            for _w in _imp_warns:
                st.warning(_w)

    # ---- Import CSV (always visible, even with no rows) ----
    with st.container(border=True):
        csv_imp_col1, csv_imp_col2 = st.columns([7, 2], vertical_alignment="bottom")
        with csv_imp_col1:
            csv_upload = st.file_uploader(
                "📤 Import CSV", type=["csv"],
                help="Upload a UTF-8 CSV (exported grid format). Click Import to load rows.",
                key="csv_import_uploader",
                label_visibility="collapsed",
            )
        with csv_imp_col2:
            if csv_upload is not None:
                upload_id = f"{csv_upload.name}_{csv_upload.size}"
                if st.session_state.get("_last_csv_import_id") != upload_id:
                    if st.button("📤 Import rows from CSV"):
                        try:
                            new_rows, parse_warnings = _import_csv_rows(csv_upload)
                            if new_rows:
                                before = list(st.session_state.rows)
                                # If grid is empty or only has blank rows, replace them
                                all_blank = not st.session_state.rows or all(
                                    not any((r.get(c) or "").strip() for c in ("campaign_name", "theme", "message", "custom_sql"))
                                    for r in st.session_state.rows
                                )
                                if all_blank:
                                    st.session_state.rows.clear()
                                start_pri = len(st.session_state.rows) + 1
                                for i, r in enumerate(new_rows):
                                    r["priority"] = start_pri + i
                                    st.session_state.rows.append(r)
                                log_change(st.session_state.audit, action="import_csv",
                                           before=before, after=st.session_state.rows,
                                           details=f"Imported {len(new_rows)} row(s) from CSV")
                                _save_from_session()
                                st.session_state["_last_csv_import_id"] = upload_id
                                if parse_warnings:
                                    st.session_state["_csv_import_warnings"] = parse_warnings
                                st.success(f"Imported {len(new_rows)} row(s) from CSV.")
                                st.rerun()
                            else:
                                st.warning("CSV file was empty — no rows imported.")
                        except Exception as exc:
                            st.error(f"CSV import failed: {exc}")
                else:
                    st.info("This file has already been imported.")

    # ---- Per-row expandable forms ----
    if st.session_state.rows:
        snapshot_before = _copy.deepcopy(st.session_state.rows)
        for idx, row in enumerate(st.session_state.rows):
            _render_row_form(idx, row, is_dev)
        # Audit‐log any changes collected from per-row widgets
        if st.session_state.rows != snapshot_before:
            diffs = diff_rows(
                [dict(r) for r in snapshot_before],
                [dict(r) for r in st.session_state.rows],
            )
            if diffs:
                log_change(st.session_state.audit, action="edit_rows",
                           before=snapshot_before, after=st.session_state.rows,
                           details=diffs)
            _save_from_session()
            st.session_state.pop("generated_sql", None)

    # ---- Export grid as CSV (UTF-8 with BOM for emoji support) ----
    if st.session_state.rows:
        visible_cols = ["priority", "row_type", "rich_push_image", "offer_type", "offer_id"] + REQUIRED_COLUMNS + [THEME_FIELD] + _optional_columns() + TARGETING_COLUMNS + ["div_banner_groups", "custom_joins", "extra_themes", "targeting_notes"]
        display_rows = []
        for r in st.session_state.rows:
            # Multi-theme container: export sub-rows as flat rows (parent excluded)
            if r.get("multi_theme") and r.get("sub_rows"):
                parent_pri = r.get("priority", 0)
                for si, sr in enumerate(r["sub_rows"]):
                    dr = dict(sr)
                    dr["priority"] = parent_pri
                    dr["row_type"] = "form"
                    dr["rich_push_image"] = "Y" if sr.get("rich_push_image") else "N"
                    groups = sr.get("div_banner_groups", [])
                    dr["div_banner_groups"] = _json.dumps(groups) if groups else ""
                    cjoins = sr.get("custom_joins", [])
                    dr["custom_joins"] = _json.dumps(cjoins) if cjoins else ""
                    ethemes = sr.get("extra_themes", [])
                    dr["extra_themes"] = ", ".join(ethemes) if ethemes else ""
                    dr["targeting_notes"] = sr.get("targeting_notes", "")
                    display_rows.append(dr)
                continue
            dr = dict(r)
            dr["row_type"] = "sql" if r.get("custom_sql") else "form"
            dr["rich_push_image"] = "Y" if r.get("rich_push_image") else "N"
            groups = r.get("div_banner_groups", [])
            dr["div_banner_groups"] = _json.dumps(groups) if groups else ""
            cjoins = r.get("custom_joins", [])
            dr["custom_joins"] = _json.dumps(cjoins) if cjoins else ""
            ethemes = r.get("extra_themes", [])
            dr["extra_themes"] = ", ".join(ethemes) if ethemes else ""
            dr["targeting_notes"] = r.get("targeting_notes", "")
            display_rows.append(dr)
        df_display = pd.DataFrame(display_rows)
        for col in visible_cols:
            if col not in df_display.columns:
                df_display[col] = ""
        df_display = df_display[visible_cols].fillna("")

        wk_id = st.session_state.get("wk_id", "")
        wk_num = wk_id[-2:] if len(wk_id) >= 2 else "00"
        day_abbr = st.session_state.get("send_day", "")[:3].capitalize() if st.session_state.get("send_day") else "Day"
        csv_fname = f"{_channel_export_prefix()}_Wk{wk_num}_{day_abbr}_grid.csv"
        if st.button("📥 Export Grid to CSV", help="Saves the campaign grid as a UTF-8 CSV to exports/. Emojis are preserved."):
            out_path = _csv_dir() / csv_fname
            _build_csv_bytes(df_display, save_path=out_path)
            st.success(f"CSV saved to `exports/{csv_fname}`")

        # ---- Utility buttons (compact row) ----
        util_col1, util_col2, util_col3 = st.columns([1, 1, 2])
        with util_col1:
            if st.button("Sort by priority"):
                # Rows whose priority was manually changed (differs from current
                # position) get a lower tiebreaker so they "win" when two rows
                # share the same target priority.
                _rows = st.session_state.rows
                _keyed = [
                    (int(r.get("priority", 0) or 0),
                     0 if int(r.get("priority", 0) or 0) != i + 1 else 1,
                     r)
                    for i, r in enumerate(_rows)
                ]
                _keyed.sort(key=lambda t: (t[0], t[1]))
                st.session_state.rows = [t[2] for t in _keyed]
                for i, r in enumerate(st.session_state.rows):
                    r["priority"] = i + 1
                _save_from_session()
                _clear_row_widget_state()
                st.session_state.pop("generated_sql", None)
                st.rerun()
        with util_col2:
            if st.button("🔄 Reload SQL from library", help="Re-reads .sql files from disk for all SQL template rows."):
                refreshed_templates = load_sql_templates()
                updated_count = 0
                for r in st.session_state.rows:
                    if r.get("custom_sql"):
                        # Prefer sql_template_name; fall back to campaign_name for legacy rows
                        tpl_name = r.get("sql_template_name") or r.get("campaign_name", "")
                        if tpl_name in refreshed_templates:
                            r["custom_sql"] = refreshed_templates[tpl_name]
                            r["sql_template_name"] = tpl_name  # backfill if missing
                            updated_count += 1
                if updated_count:
                    _save_from_session()
                    st.success(f"Refreshed {updated_count} SQL template row(s) from disk.")
                    st.rerun()
                else:
                    st.info("No SQL template rows matched library files.")

    # ---- Section 2: role-dependent ----
    if not is_dev:
        # ---- User: Save / Submit ----
        st.divider()

        # ---- Activity Log ----
        campaign_data = load_campaign(cid) or {}
        activity_log = campaign_data.get("activity_log", [])

        with st.expander(f"📝 Activity Log ({len(activity_log)} entries)", expanded=False):
            if activity_log:
                for entry in reversed(activity_log):
                    action = entry.get("action", "")
                    ts = entry.get("ts", "")
                    try:
                        dt = datetime.fromisoformat(ts)
                        ts_fmt = dt.strftime("%b %d, %I:%M %p")
                    except (ValueError, TypeError):
                        ts_fmt = ts
                    st.caption(f"{action} — {ts_fmt}")
            else:
                st.caption("No activity recorded yet.")

        # ---- Change History (audit trail) ----
        audit = st.session_state.get("audit", [])
        with st.expander(f"🕓 Change History ({len(audit)} entries)", expanded=False):
            if not audit:
                st.caption("No changes recorded yet.")
            else:
                for entry in reversed(audit):
                    ts = _friendly_ts(entry.get("ts", ""))
                    summaries = entry.get("summary", [entry.get("action", "unknown")])
                    for line in summaries:
                        st.markdown(f"- `{ts}` — {line}")

        st.subheader("Pre-QC Report")

        rows = st.session_state.get("rows", [])

        # Auto-trim whitespace before running checks so trimmed values feed the report
        trim_notices = _trim_whitespace_fields(rows)
        if trim_notices:
            with st.expander(f"ℹ️ {len(trim_notices)} field(s) auto-trimmed", expanded=False):
                st.caption("Leading/trailing spaces were removed automatically — no action needed.")
                for tn in trim_notices:
                    st.markdown(f"- {tn}")

        preqc_report = _run_preqc(
            rows,
            st.session_state.get("wk_id", ""),
            st.session_state.get("send_day", ""),
            sql_overrides=st.session_state.get("sql_overrides", {}),
            include_placeholder=True,
            current_campaign_id=cid,
            current_send_date=str(st.session_state.get("send_date", "") or ""),
        )
        has_blockers, has_warnings = _render_preqc_scorecard(preqc_report, row_count=len(rows))

        with st.expander("🔁 Compare to previous week (recurring-campaign diff)", expanded=False):
            _render_prior_week_panel(
                rows,
                cid,
                str(st.session_state.get("send_date", "") or ""),
                st.session_state.get("send_day", ""),
            )

        st.divider()
        st.subheader("Save & Submit")

        # Acknowledge-warnings gate
        ack_key = f"preqc_ack_{cid}"
        ack = False
        if has_warnings and not has_blockers:
            ack = st.checkbox(
                "I have reviewed the advisory warnings above and confirm this campaign day is ready to submit.",
                key=ack_key,
            )

        save_col, submit_col = st.columns(2)

        with save_col:
            if st.button("💾 Save as Pending Assets", type="primary"):
                st.session_state.campaign_status = "Pending Assets"
                _save_from_session(activity_event="Saved")
                st.toast("Campaign saved as **Pending Assets**.")
                st.session_state.view = "dashboard"
                st.session_state.generated_sql = ""
                st.rerun()

        with submit_col:
            submit_disabled = has_blockers or (has_warnings and not ack)
            help_msg = None
            if has_blockers:
                help_msg = "Fix the blockers in the Pre-QC Report before submitting."
            elif has_warnings and not ack:
                help_msg = "Acknowledge the advisory warnings above to enable Submit."
            if st.button("✅ Submit for Export", type="primary", disabled=submit_disabled, help=help_msg):
                st.session_state.campaign_status = "Submitted"
                _save_from_session(activity_event="Submitted for Export")
                st.toast("✅ Campaign day has been **submitted for export**!")
                st.session_state.view = "dashboard"
                st.session_state.generated_sql = ""
                st.session_state.pop(ack_key, None)
                st.rerun()

    if is_dev:
        # ---- Developer: Unlock for revision ----
        cur_status_dev = st.session_state.get("campaign_status", "Draft")
        if cur_status_dev in _LOCKED_FOR_USER:
            st.divider()
            _btn_color("red")
            if st.button(
                f"🔓 Unlock for revision (currently **{cur_status_dev}** → In Progress)",
                help="Resets the campaign to 'In Progress' so Users can edit again.",
            ):
                st.session_state.campaign_status = "In Progress"
                _save_from_session(activity_event=f"Unlocked from {cur_status_dev}")
                st.toast(f"Campaign unlocked → **In Progress** (was {cur_status_dev})")
                st.rerun()

        # ---- Developer: Input Summary ----
        st.divider()
        st.subheader("Input Summary")
        rows = st.session_state.get("rows", [])

        # Show per-row targeting notes summary for developer
        rows_with_notes = [(i, r) for i, r in enumerate(rows) if (r.get("targeting_notes") or "").strip()]
        if rows_with_notes:
            with st.expander(f"📝 Targeting Instructions ({len(rows_with_notes)} row(s))", expanded=True):
                for i, r in rows_with_notes:
                    label = r.get("campaign_name") or f"Row {i+1}"
                    st.markdown(f"**Row {i+1} — {label}:**")
                    st.code(r["targeting_notes"], language=None)

        # Show per-row OR group summary for developer
        rows_with_or = [(i, r) for i, r in enumerate(rows) if r.get("div_banner_groups")]
        if rows_with_or:
            total_or = sum(len(r.get("div_banner_groups", [])) for _, r in rows_with_or)
            with st.expander(f"🔗 Division+Banner OR Groups ({total_or} group(s) across {len(rows_with_or)} row(s))", expanded=True):
                for i, r in rows_with_or:
                    label = r.get("campaign_name") or f"Row {i+1}"
                    st.markdown(f"**Row {i+1} — {label}:**")
                    for gi, g in enumerate(r["div_banner_groups"]):
                        parts = []
                        if g.get("division_ids"):
                            parts.append(f"div {g.get('div_mode', 'IN')} ({g['division_ids']})")
                        if g.get("banners"):
                            parts.append(f"banner {g.get('banner_mode', 'IN')} ({g['banners']})")
                        if g.get("store_ids"):
                            parts.append(f"store {g.get('store_mode', 'IN')} ({g['store_ids']})")
                        st.markdown(f"  Group {gi+1}: {' AND '.join(parts)}" if parts else f"  Group {gi+1}: *(empty)*")

        if not rows:
            st.info("No campaign rows yet.")
        else:
            summary_cols = ["priority", "campaign_name", "theme", "offer_type", "offer_id",
                            "CANONICALCAMPAIGNID",
                            "division_ids", "division_mode", "banners", "banner_mode",
                            "store_ids", "store_mode"]
            summary_rows = []
            for r in rows:
                row_type = "sql" if r.get("custom_sql") else "form"
                sr = {"row_type": row_type}
                for c in summary_cols:
                    sr[c] = r.get(c, "")
                summary_rows.append(sr)
            st.dataframe(summary_rows, use_container_width=True, hide_index=True)

            # Quick stats
            form_count = sum(1 for r in rows if not r.get("custom_sql"))
            sql_count = sum(1 for r in rows if r.get("custom_sql"))
            targeting_count = sum(
                1 for r in rows
                if any((r.get(f) or "").strip() for f in ("division_ids", "banners", "store_ids"))
                or r.get("div_banner_groups")
            )
            offer_count = sum(1 for r in rows if (r.get("offer_type") or "").strip())

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Rows", len(rows))
            m2.metric("Form / SQL", f"{form_count} / {sql_count}")
            m3.metric("With Targeting", targeting_count)
            m4.metric("With Offer JOIN", offer_count)

        # ---- SQL Preview per row (editable) ----
        if rows:
            st.divider()
            st.subheader("SQL Preview")
            st.caption("Edit the rendered SQL per row before export. Changes here override the generated output.")
            env = jinja_env()
            _is_rcs_preview = _current_channel() == "rcs"
            if _is_rcs_preview:
                # RCS: full YAML dict (with 'tables' + 'runtime'); PUSH's load_tables would fail
                # because rcs/config/tables.yaml doesn't carry PUSH-specific keys.
                tables_cfg = _load_rcs_tables_cfg()
                tables = tables_cfg.get("tables", {}) if isinstance(tables_cfg, dict) else {}
                _preview_send_date = str(st.session_state.get("send_date", "") or "")
            else:
                tables_cfg = None
                tables = load_tables(send_day=st.session_state.get("send_day", ""))
                _preview_send_date = ""
            env_preview = create_permissive_env()

            def _render_preview_sql(row: dict) -> str:
                """Channel-aware single-row renderer for the preview text area."""
                if _is_rcs_preview:
                    return render_rcs_campaign_insert(env, tables_cfg, row, _preview_send_date)
                return render_campaign_insert(env, tables, row)

            # Ensure override store exists
            st.session_state.setdefault("sql_overrides", {})
            # Snapshot overrides before widgets render so we can detect changes
            st.session_state["_prev_sql_overrides"] = dict(st.session_state["sql_overrides"])

            for i, r in enumerate(rows):
                rid = r.get("_row_id", str(i))
                label = r.get("campaign_name") or f"Row {i+1}"
                row_type = "sql" if r.get("custom_sql") else "form"

                # ---- Multi-theme container: show sub-row previews ----
                if r.get("multi_theme") and r.get("sub_rows"):
                    pri = r.get("priority", i + 1)
                    with st.expander(f"Row {i+1} — {label}  `[multi-theme]` ({len(r['sub_rows'])} sub-rows)", expanded=False):
                        for si, sr in enumerate(r["sub_rows"]):
                            sr_rid = sr.get("_row_id", f"{rid}_{si}")
                            sr_label = sr.get("campaign_name") or f"Sub-Row {si+1}"
                            st.markdown(f"**Row {pri}.{si+1}: {sr_label}**")
                            sr_copy = dict(sr)
                            sr_copy["priority"] = int(pri)
                            try:
                                sr_default_sql = _render_preview_sql(sr_copy)
                            except Exception as exc:
                                st.error(f"Preview error for sub-row {si+1}: {exc}")
                                sr_default_sql = ""

                            _sr_wk = f"sql_preview_{sr_rid}"
                            _sr_ldk = f"_last_default_{sr_rid}"
                            if sr_rid not in st.session_state["sql_overrides"]:
                                prev_default = st.session_state.get(_sr_ldk)
                                if prev_default != sr_default_sql:
                                    st.session_state[_sr_wk] = sr_default_sql
                            st.session_state[_sr_ldk] = sr_default_sql

                            if _sr_wk not in st.session_state:
                                st.session_state[_sr_wk] = st.session_state["sql_overrides"].get(sr_rid, sr_default_sql)

                            edited_sql = st.text_area(
                                f"SQL {pri}.{si+1}", height=200, key=_sr_wk, label_visibility="collapsed",
                            )
                            if edited_sql != sr_default_sql:
                                st.session_state["sql_overrides"][sr_rid] = edited_sql
                            elif sr_rid in st.session_state["sql_overrides"]:
                                del st.session_state["sql_overrides"][sr_rid]

                            if sr_rid in st.session_state["sql_overrides"]:
                                st.caption("✏️ Modified — this override will be used at export.")
                                if st.button("Reset to generated", key=f"reset_sql_{sr_rid}"):
                                    del st.session_state["sql_overrides"][sr_rid]
                                    st.session_state.pop(_sr_wk, None)
                                    st.session_state.pop(_sr_ldk, None)
                                    st.rerun()
                            st.markdown("---")
                    continue

                with st.expander(f"Row {i+1} — {label}  `[{row_type}]`", expanded=False):
                    # Generate the default rendered SQL
                    default_sql = ""
                    if r.get("custom_sql"):
                        tpl_ctx = {k: v for k, v in r.items() if k not in ("custom_sql", "_row_id")}
                        tpl_ctx["wk_id"] = st.session_state.get("wk_id", "")
                        tpl_ctx["send_date"] = str(st.session_state.get("send_date", ""))
                        tpl_ctx["tables"] = tables
                        tpl_ctx = _expand_offer_ids(tpl_ctx)
                        tpl_ctx = _expand_extra_themes(tpl_ctx)
                        tpl_ctx = _escape_sql_strings(tpl_ctx)
                        notes_comment = _targeting_notes_comment(r)
                        try:
                            rendered = env_preview.from_string(r["custom_sql"]).render(**tpl_ctx)
                            rendered = _override_canonicalcampaignid(rendered, r)
                            rendered = _inject_notes_after_from(rendered, notes_comment)
                            default_sql = (
                                f"--======================================================================\n"
                                f"-- {label} (custom SQL)\n"
                                f"--======================================================================\n"
                                f"{rendered}"
                            )
                        except Exception as exc:
                            st.warning(f"Render error: {exc}")
                            default_sql = r["custom_sql"]
                    else:
                        try:
                            default_sql = _render_preview_sql(r)
                        except Exception as exc:
                            st.error(f"Preview error: {exc}")

                    # Sync widget value with generated default ONLY when the
                    # default itself has changed (form edit) and user has no
                    # active override.  Never overwrite an incoming user edit.
                    _ldk = f"_last_default_{rid}"
                    _widget_key = f"sql_preview_{rid}"
                    if rid not in st.session_state["sql_overrides"]:
                        prev_default = st.session_state.get(_ldk)
                        if prev_default != default_sql:
                            st.session_state[_widget_key] = default_sql
                    st.session_state[_ldk] = default_sql

                    # Initialize widget key if not yet in session state (first render).
                    # Must happen BEFORE the widget is created so we never pass both
                    # value= and a pre-existing session-state key (Streamlit warns on that).
                    if _widget_key not in st.session_state:
                        st.session_state[_widget_key] = st.session_state["sql_overrides"].get(rid, default_sql)

                    # No value= argument — session state drives the widget entirely
                    edited_sql = st.text_area(
                        "SQL",
                        height=250,
                        key=_widget_key,
                        label_visibility="collapsed",
                    )
                    if edited_sql != default_sql:
                        st.session_state["sql_overrides"][rid] = edited_sql
                    elif rid in st.session_state["sql_overrides"]:
                        del st.session_state["sql_overrides"][rid]

                    # Clear cached generated SQL when preview is edited
                    prev_override = st.session_state.get("_prev_sql_overrides", {}).get(rid)
                    curr_override = st.session_state["sql_overrides"].get(rid)
                    if curr_override != prev_override:
                        st.session_state.pop("generated_sql", None)

                    if rid in st.session_state["sql_overrides"]:
                        st.caption("✏️ Modified — this override will be used at export.")
                        if st.button("Reset to generated", key=f"reset_sql_{rid}"):
                            del st.session_state["sql_overrides"][rid]
                            st.session_state.pop(f"sql_preview_{rid}", None)
                            st.session_state.pop(_ldk, None)
                            st.rerun()

        # ---- Pre-QC Report (consolidated) ----
        st.divider()
        st.subheader("Pre-QC Report")

        # Auto-trim whitespace before running checks so trimmed values feed the report
        trim_notices_dev = _trim_whitespace_fields(rows)
        if trim_notices_dev:
            with st.expander(f"ℹ️ {len(trim_notices_dev)} field(s) auto-trimmed", expanded=False):
                st.caption("Leading/trailing spaces were removed automatically — no action needed.")
                for tn in trim_notices_dev:
                    st.markdown(f"- {tn}")

        preqc_report_dev = _run_preqc(
            rows,
            st.session_state.get("wk_id", ""),
            st.session_state.get("send_day", ""),
            sql_overrides=st.session_state.get("sql_overrides", {}),
            include_placeholder=True,
            current_campaign_id=cid,
            current_send_date=str(st.session_state.get("send_date", "") or ""),
        )
        has_blockers_dev, _ = _render_preqc_scorecard(preqc_report_dev, row_count=len(rows))

        with st.expander("🔁 Compare to previous week (recurring-campaign diff)", expanded=False):
            _render_prior_week_panel(
                rows,
                cid,
                str(st.session_state.get("send_date", "") or ""),
                st.session_state.get("send_day", ""),
            )

        st.divider()
        st.subheader("Review & Export")

        _invalidate_sql_on_template_change()

        gen_help = "Fix the blockers in the Pre-QC Report before generating SQL." if has_blockers_dev else None
        if st.button("Generate SQL", type="primary", disabled=has_blockers_dev, help=gen_help):
            if has_blockers_dev:
                st.error("Cannot generate SQL: blockers remain in the Pre-QC Report above.")
            else:
                try:
                    if _current_channel() == "rcs":
                        _tables_cfg = _load_rcs_tables_cfg()
                        sql_text = build_rcs_sql(
                            env, _tables_cfg, st.session_state.rows,
                            st.session_state.get("wk_id", ""), str(st.session_state.send_date),
                        )
                    else:
                        sql_text = build_sql(
                            env, tables, st.session_state.rows,
                            st.session_state.get("wk_id", ""), str(st.session_state.send_date),
                            sql_overrides=st.session_state.get("sql_overrides", {}),
                        )
                    st.session_state.generated_sql = sql_text
                    st.session_state["_offer_tpl_fp"] = _offer_template_fingerprint()
                    st.success("SQL generated successfully.")
                except RuntimeError as exc:
                    st.error(f"SQL generation failed: {exc}")
                except Exception as exc:
                    st.error(f"Unexpected error during SQL generation: {exc}")

        if sql_text := st.session_state.get("generated_sql"):
            wk_id = st.session_state.get("wk_id", "")
            wk_num = wk_id[-2:] if len(wk_id) >= 2 else "00"
            day_abbr = st.session_state.get("send_day", "")[:3].capitalize() if st.session_state.get("send_day") else "Day"
            export_name = f"{_channel_export_prefix()}_Wk{wk_num}_{day_abbr}.sql"
            if st.download_button("Download .sql", data=sql_text, file_name=export_name, mime="text/sql"):
                # Save .sql to sql_exports/ folder on disk (only on actual download)
                _sql_exports_dir().mkdir(parents=True, exist_ok=True)
                (_sql_exports_dir() / export_name).write_text(sql_text, encoding="utf-8")
                # Mark as Exported on download
                st.session_state.campaign_status = "Exported"
                _save_from_session()

        st.subheader("Change History")
        audit = st.session_state.get("audit", [])
        if not audit:
            st.caption("No changes recorded yet.")
        else:
            for entry in reversed(audit):
                ts = _friendly_ts(entry.get("ts", ""))
                summaries = entry.get("summary", [entry.get("action", "unknown")])
                for line in summaries:
                    st.markdown(f"- `{ts}` — {line}")

    # Auto-save on every render (header field changes, etc.)
    _save_from_session()
