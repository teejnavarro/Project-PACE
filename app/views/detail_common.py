# app/views/detail_common.py
"""Detail-view widgets shared by PUSH and RCS rows."""

import streamlit as st
import yaml
from ui import (
    _JOIN_TYPES, _MODE_OPTIONS, _MODE_STORAGE, _config_dir,
    _division_display_to_id, _division_ids_to_display, _invalid_store_id_tokens, _load_banner_options,
    _load_division_options, _parse_store_paste, _save_from_session,
)


# Load known division/banner hints once
@st.cache_data(ttl=300)
def _load_targeting_hints() -> tuple[list, list]:
    targeting_path = _config_dir() / "targeting.yaml"
    if targeting_path.exists():
        with open(targeting_path) as f:
            tgt_cfg = yaml.safe_load(f) or {}
        return tgt_cfg.get("divisions", []), tgt_cfg.get("banners", [])
    return [], []


# ─────────────────────────────────────────────────────────────────────
# Shared row-level targeting UI. PUSH and RCS both call this — the SQL
# alias difference (a. vs s.) is handled in compose.py, not in the UI.
# ─────────────────────────────────────────────────────────────────────

def _render_row_targeting_ui(idx: int, row: dict, rid: str, division_options: list, banner_options: list, known_divs: list) -> None:
    """Render the shared Targeting / Targeting notes / Custom JOINs expanders for one row.
    Widget keys use rm_* prefix + stable rid; safe for both channels since rid is unique.
    """
    with st.expander("🎯 Targeting", expanded=False):
        # Division IDs — multiselect dropdown
        if division_options:
            vc, mc = st.columns([3, 1])
            with vc:
                cur_div_str = row.get("division_ids", "")
                cur_div_display = _division_ids_to_display(cur_div_str, division_options)
                selected_divs = st.multiselect(
                    "Division IDs", options=division_options,
                    default=[d for d in cur_div_display if d in division_options],
                    key=f"frm_division_ids_{rid}",
                )
                new_div_str = ",".join(_division_display_to_id(d) for d in selected_divs)
                if new_div_str != (row.get("division_ids") or ""):
                    st.session_state.rows[idx]["division_ids"] = new_div_str
            with mc:
                cur_mode = row.get("division_mode", "IN")
                display_idx = 0 if cur_mode == "IN" else 1
                chosen_display = st.selectbox("division_ids mode", options=_MODE_OPTIONS, index=display_idx, key=f"frm_division_mode_{rid}")
                new_mode = _MODE_STORAGE[chosen_display]
                if new_mode != cur_mode:
                    st.session_state.rows[idx]["division_mode"] = new_mode
        else:
            # Fallback to text input if divisions.txt not found
            vc, mc = st.columns([3, 1])
            with vc:
                new_val = st.text_input(f"Division IDs{' (known: ' + ', '.join(str(d) for d in known_divs) + ')' if known_divs else ''}", value=row.get("division_ids", ""), key=f"frm_division_ids_{rid}")
                if new_val != (row.get("division_ids") or ""):
                    st.session_state.rows[idx]["division_ids"] = new_val
            with mc:
                cur_mode = row.get("division_mode", "IN")
                display_idx = 0 if cur_mode == "IN" else 1
                chosen_display = st.selectbox("division_ids mode", options=_MODE_OPTIONS, index=display_idx, key=f"frm_division_mode_{rid}")
                new_mode = _MODE_STORAGE[chosen_display]
                if new_mode != cur_mode:
                    st.session_state.rows[idx]["division_mode"] = new_mode

        # Store IDs
        vc, mc = st.columns([3, 1])
        with vc:
            new_val = st.text_input("Store IDs", value=row.get("store_ids", ""), key=f"frm_store_ids_{rid}")
            if new_val != (row.get("store_ids") or ""):
                st.session_state.rows[idx]["store_ids"] = new_val
            _bad_sid = _invalid_store_id_tokens(new_val)
            if _bad_sid:
                st.error(
                    f"⛔ Non-numeric token(s): **{', '.join(_bad_sid)}** — "
                    f"enter numbers only, separated by commas (e.g. `100,200,300`)."
                )
        with mc:
            cur_mode = row.get("store_mode", "IN")
            display_idx = 0 if cur_mode == "IN" else 1
            chosen_display = st.selectbox("store_ids mode", options=_MODE_OPTIONS, index=display_idx, key=f"frm_store_mode_{rid}")
            new_mode = _MODE_STORAGE[chosen_display]
            if new_mode != cur_mode:
                st.session_state.rows[idx]["store_mode"] = new_mode

        # Paste a vertical Excel column of store numbers → auto-join to comma-separated
        _sp_success_key = f"_frm_store_paste_success_{rid}"
        if _sp_success_key in st.session_state:
            st.success(st.session_state.pop(_sp_success_key))
        with st.expander("📋 Paste a store list", expanded=False):
            st.caption(
                "Copy a column of store numbers from Excel (with or without a header) "
                "and paste it below. Non-numeric tokens are safely ignored — store IDs "
                "can never merge together. Duplicates are preserved so the count matches "
                "your Excel source; any duplicates found are reported as an advisory."
            )
            paste_val = st.text_area(
                "Paste store IDs (one per line)",
                key=f"frm_store_paste_{rid}",
                height=140,
                placeholder="Store_Number\n1001\n1002\n1003",
                label_visibility="collapsed",
            )
            valid_ids, warnings = _parse_store_paste(paste_val)
            for w in warnings:
                st.caption(f"⚠️ {w}")
            if valid_ids:
                preview = ", ".join(valid_ids[:10])
                if len(valid_ids) > 10:
                    preview += f", … (+{len(valid_ids) - 10} more)"
                st.caption(f"✅ {len(valid_ids)} store ID(s) ready")
                st.code(preview, language=None)
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("Replace Store IDs", key=f"frm_store_paste_replace_{rid}", type="primary"):
                        st.session_state.rows[idx]["store_ids"] = ",".join(valid_ids)
                        st.session_state["_pending_paste_overrides"] = {
                            f"frm_store_paste_{rid}": "",
                            f"frm_store_ids_{rid}": ",".join(valid_ids),
                        }
                        st.session_state[_sp_success_key] = f"Replaced Store IDs with {len(valid_ids)} store number(s)."
                        _save_from_session()
                        st.rerun()
                with bc2:
                    if st.button("Append to Store IDs", key=f"frm_store_paste_append_{rid}"):
                        existing_raw = (row.get("store_ids") or "").strip()
                        existing = [t.strip() for t in existing_raw.split(",") if t.strip()]
                        merged = existing + valid_ids
                        st.session_state.rows[idx]["store_ids"] = ",".join(merged)
                        st.session_state["_pending_paste_overrides"] = {
                            f"frm_store_paste_{rid}": "",
                            f"frm_store_ids_{rid}": ",".join(merged),
                        }
                        st.session_state[_sp_success_key] = f"Added {len(valid_ids)} store number(s)."
                        _save_from_session()
                        st.rerun()
            elif paste_val.strip() and not warnings:
                st.caption("No valid numeric store IDs found.")

        # Banners — multiselect dropdown
        if banner_options:
            vc, mc = st.columns([3, 1])
            with vc:
                cur_banners_str = row.get("banners", "")
                cur_banners_list = [b.strip().lower() for b in cur_banners_str.split(",") if b.strip()] if cur_banners_str else []
                selected_banners = st.multiselect(
                    "Banners", options=banner_options,
                    default=[b for b in cur_banners_list if b in banner_options],
                    key=f"frm_banners_{rid}",
                )
                new_banners_str = ",".join(selected_banners)
                if new_banners_str != (row.get("banners") or ""):
                    st.session_state.rows[idx]["banners"] = new_banners_str
            with mc:
                cur_mode = row.get("banner_mode", "IN")
                display_idx = 0 if cur_mode == "IN" else 1
                chosen_display = st.selectbox("banners mode", options=_MODE_OPTIONS, index=display_idx, key=f"frm_banner_mode_{rid}")
                new_mode = _MODE_STORAGE[chosen_display]
                if new_mode != cur_mode:
                    st.session_state.rows[idx]["banner_mode"] = new_mode
        else:
            # Fallback to text input if banners.txt not found
            vc, mc = st.columns([3, 1])
            with vc:
                new_val = st.text_input("Banners", value=row.get("banners", ""), key=f"frm_banners_{rid}")
                if new_val != (row.get("banners") or ""):
                    st.session_state.rows[idx]["banners"] = new_val
            with mc:
                cur_mode = row.get("banner_mode", "IN")
                display_idx = 0 if cur_mode == "IN" else 1
                chosen_display = st.selectbox("banners mode", options=_MODE_OPTIONS, index=display_idx, key=f"frm_banner_mode_{rid}")
                new_mode = _MODE_STORAGE[chosen_display]
                if new_mode != cur_mode:
                    st.session_state.rows[idx]["banner_mode"] = new_mode

        # ---- OR Groups (within targeting sub-expander) ----
        groups = row.get("div_banner_groups", [])
        if groups or True:  # always show section
            st.markdown("---")
            st.caption("**Division + Banner/Store OR groups** — compound OR clauses: "
                       "`(div=29 AND banner IN (...) OR div=33 AND banner IN (...))`")
            for gi, g in enumerate(groups):
                c1, c2, c3, c4, c5, c6, c7 = st.columns([1.2, 0.8, 1.5, 0.8, 1.2, 0.8, 0.5])
                with c1:
                    _or_div_options = _load_division_options()
                    if _or_div_options:
                        _cur_or_div = g.get("division_ids", "")
                        _cur_or_div_display = _division_ids_to_display(_cur_or_div, _or_div_options)
                        _sel_or_div = st.multiselect(
                            "Division IDs",
                            options=_or_div_options,
                            default=[d for d in _cur_or_div_display if d in _or_div_options],
                            key=f"frm_or_div_{rid}_{gi}",
                            label_visibility="collapsed" if gi > 0 else "visible",
                        )
                        g["division_ids"] = ",".join(_division_display_to_id(d) for d in _sel_or_div)
                    else:
                        g["division_ids"] = st.text_input(
                            "Division IDs", value=g.get("division_ids", ""),
                            key=f"frm_or_div_{rid}_{gi}", placeholder="29 or 5,17",
                            label_visibility="collapsed" if gi > 0 else "visible",
                        )
                with c2:
                    _dm_idx = 0 if g.get("div_mode", "IN") == "IN" else 1
                    _dm_display = st.selectbox(
                        "Div Mode", options=_MODE_OPTIONS,
                        index=_dm_idx,
                        key=f"frm_or_dmode_{rid}_{gi}",
                        label_visibility="collapsed" if gi > 0 else "visible",
                    )
                    g["div_mode"] = _MODE_STORAGE[_dm_display]
                with c3:
                    _or_banner_options = _load_banner_options()
                    if _or_banner_options:
                        _cur_or_ban = g.get("banners", "")
                        _cur_or_ban_list = [b.strip().lower() for b in _cur_or_ban.split(",") if b.strip()] if _cur_or_ban else []
                        _sel_or_ban = st.multiselect(
                            "Banners",
                            options=_or_banner_options,
                            default=[b for b in _cur_or_ban_list if b in _or_banner_options],
                            key=f"frm_or_ban_{rid}_{gi}",
                            label_visibility="collapsed" if gi > 0 else "visible",
                        )
                        g["banners"] = ",".join(_sel_or_ban)
                    else:
                        g["banners"] = st.text_input(
                            "Banners", value=g.get("banners", ""),
                            key=f"frm_or_ban_{rid}_{gi}", placeholder="cedar_market,blueharbor",
                            label_visibility="collapsed" if gi > 0 else "visible",
                        )
                with c4:
                    _bm_idx = 0 if g.get("banner_mode", "IN") == "IN" else 1
                    _bm_display = st.selectbox(
                        "Ban Mode", options=_MODE_OPTIONS,
                        index=_bm_idx,
                        key=f"frm_or_bmode_{rid}_{gi}",
                        label_visibility="collapsed" if gi > 0 else "visible",
                    )
                    g["banner_mode"] = _MODE_STORAGE[_bm_display]
                with c5:
                    g["store_ids"] = st.text_input(
                        "Store IDs", value=g.get("store_ids", ""),
                        key=f"frm_or_sid_{rid}_{gi}", placeholder="100,200",
                        label_visibility="collapsed" if gi > 0 else "visible",
                    )
                    _bad_sid = _invalid_store_id_tokens(g["store_ids"])
                    if _bad_sid:
                        st.caption(f"⛔ Non-numeric: **{', '.join(_bad_sid)}** — digits only, comma-separated.")
                with c6:
                    _sm_idx = 0 if g.get("store_mode", "IN") == "IN" else 1
                    _sm_display = st.selectbox(
                        "Sto Mode", options=_MODE_OPTIONS,
                        index=_sm_idx,
                        key=f"frm_or_smode_{rid}_{gi}",
                        label_visibility="collapsed" if gi > 0 else "visible",
                    )
                    g["store_mode"] = _MODE_STORAGE[_sm_display]
                with c7:
                    if gi == 0:
                        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if st.button("✕", key=f"frm_or_rm_{rid}_{gi}", help="Remove this OR group"):
                        st.session_state.rows[idx]["div_banner_groups"].pop(gi)
                        _save_from_session()
                        st.rerun()
                groups[gi] = g

            # Save any field edits
            if groups != row.get("div_banner_groups", []):
                st.session_state.rows[idx]["div_banner_groups"] = groups
                _save_from_session()

            if st.button("＋ Add OR group", key=f"frm_or_add_{rid}"):
                if "div_banner_groups" not in st.session_state.rows[idx]:
                    st.session_state.rows[idx]["div_banner_groups"] = []
                st.session_state.rows[idx]["div_banner_groups"].append({
                    "division_ids": "", "div_mode": "IN",
                    "banners": "", "banner_mode": "IN",
                    "store_ids": "", "store_mode": "IN",
                })
                _save_from_session()
                st.rerun()

    # ---- Targeting notes (collapsed sub-expander) ----
    with st.expander("📝 Targeting notes", expanded=False):
        current_notes = row.get("targeting_notes", "")
        updated_notes = st.text_area(
            "Targeting instructions",
            value=current_notes,
            height=80,
            key=f"frm_tnotes_{rid}",
            placeholder="e.g. Include only customers from custom_audience WHERE segment = 'high_value'",
            label_visibility="collapsed",
        )
        if updated_notes != current_notes:
            st.session_state.rows[idx]["targeting_notes"] = updated_notes

    # ---- Custom JOINs (collapsed sub-expander) ----
    cjoins = row.get("custom_joins", [])
    cj_label = f"🔗 Custom JOINs ({len(cjoins)})" if cjoins else "🔗 Custom JOINs"
    with st.expander(cj_label, expanded=False):
        st.caption("Add custom JOIN clauses. Choose **Structured** for guided fields or **Free text** to paste raw SQL.")
        for ji, j in enumerate(cjoins):
            cur_mode = j.get("mode", "structured")
            mode_col, content_col, rm_col = st.columns([1, 6, 0.4])
            with mode_col:
                new_mode = st.selectbox(
                    "Mode", options=["structured", "freetext"],
                    index=0 if cur_mode == "structured" else 1,
                    key=f"frm_cj_mode_{rid}_{ji}",
                    label_visibility="collapsed" if ji > 0 else "visible",
                )
                j["mode"] = new_mode
            with content_col:
                if new_mode == "freetext":
                    j["raw_sql"] = st.text_area(
                        "SQL", value=j.get("raw_sql", ""),
                        key=f"frm_cj_raw_{rid}_{ji}", height=100,
                        placeholder="JOIN project.dataset.table b\n  ON a.id = b.id\nWHERE b.status = 'active'",
                        label_visibility="collapsed" if ji > 0 else "visible",
                    )
                else:
                    sc1, sc2, sc3, sc4 = st.columns([1, 2.5, 0.7, 2.5])
                    with sc1:
                        j["join_type"] = st.selectbox(
                            "Type", options=_JOIN_TYPES,
                            index=_JOIN_TYPES.index(j.get("join_type", "JOIN")) if j.get("join_type", "JOIN") in _JOIN_TYPES else 0,
                            key=f"frm_cj_type_{rid}_{ji}",
                            label_visibility="collapsed" if ji > 0 else "visible",
                        )
                    with sc2:
                        j["table_path"] = st.text_input(
                            "Table path", value=j.get("table_path", ""),
                            key=f"frm_cj_tbl_{rid}_{ji}", placeholder="project.dataset.table_name",
                            label_visibility="collapsed" if ji > 0 else "visible",
                        )
                    with sc3:
                        j["alias"] = st.text_input(
                            "Alias", value=j.get("alias", ""),
                            key=f"frm_cj_alias_{rid}_{ji}", placeholder="b",
                            label_visibility="collapsed" if ji > 0 else "visible",
                        )
                    with sc4:
                        j["on_clause"] = st.text_input(
                            "ON clause", value=j.get("on_clause", ""),
                            key=f"frm_cj_on_{rid}_{ji}", placeholder="a.household_id = b.household_id",
                            label_visibility="collapsed" if ji > 0 else "visible",
                        )
            with rm_col:
                if ji == 0:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("✕", key=f"frm_cj_rm_{rid}_{ji}", help="Remove this JOIN"):
                    st.session_state.rows[idx]["custom_joins"].pop(ji)
                    _save_from_session()
                    st.rerun()
            cjoins[ji] = j

        # Save field edits
        if cjoins != row.get("custom_joins", []):
            st.session_state.rows[idx]["custom_joins"] = cjoins
            _save_from_session()

        add_col1, add_col2 = st.columns(2)
        with add_col1:
            if st.button("＋ Add structured JOIN", key=f"frm_cj_add_{rid}"):
                if "custom_joins" not in st.session_state.rows[idx]:
                    st.session_state.rows[idx]["custom_joins"] = []
                st.session_state.rows[idx]["custom_joins"].append({
                    "mode": "structured", "join_type": "JOIN", "table_path": "",
                    "alias": "", "on_clause": "",
                })
                _save_from_session()
                st.rerun()
        with add_col2:
            if st.button("＋ Add free-text JOIN", key=f"frm_cj_addfree_{rid}"):
                if "custom_joins" not in st.session_state.rows[idx]:
                    st.session_state.rows[idx]["custom_joins"] = []
                st.session_state.rows[idx]["custom_joins"].append({
                    "mode": "freetext", "raw_sql": "",
                })
                _save_from_session()
                st.rerun()
