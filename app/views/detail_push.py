# app/views/detail_push.py
"""PUSH row form and multi-theme sub-row form."""

import re as _re
import streamlit as st
from ui import (
    REQUIRED_COLUMNS, _JOIN_TYPES, _MODE_OPTIONS, _MODE_STORAGE,
    _all_columns, _btn_color, _channel_offer_types, _clear_row_widget_state,
    _current_channel, _division_display_to_id, _division_ids_to_display, _format_handling_time,
    _invalid_store_id_tokens, _load_banner_options, _load_division_options, _load_optional_columns_cfg,
    _mark_row_active, _new_row_id, _offer_field_label, _offer_field_name,
    _optional_columns, _parse_key_value_block, _row_offer_value, _save_from_session,
    load_sql_templates,
)
from views.detail_common import _load_targeting_hints, _render_row_targeting_ui
from views.detail_rcs import _render_rcs_row_form


def _render_sub_row_form(idx: int, si: int, sub_row: dict):
    """Render a full form for a sub-row inside a multi-theme container.

    Writes changes to st.session_state.rows[idx]["sub_rows"][si].
    Layout mirrors _render_row_form() for visual consistency.
    """
    srid = sub_row.get("_row_id", str(si))

    sr_row_type = "sql" if sub_row.get("custom_sql") else "form"

    # Detect Jinja2 placeholders in SQL template sub-rows for caption hints
    _jinja_tpl_re = _re.compile(r"\{\{\s*(\w+)\s*\}\}")
    _CAPTION_FIELDS = {"offer_id", "theme", "message", "title"}
    sr_template_placeholders = set(_jinja_tpl_re.findall(sub_row.get("custom_sql", ""))) if sub_row.get("custom_sql") else set()

    # ---- Top strip: offer_type, offer_id (same layout as standard row) ----
    tc1, tc2, tc3, tc4 = st.columns([0.7, 0.7, 1.5, 1.5], vertical_alignment="bottom")
    with tc1:
        st.text_input("Row Type", value=sr_row_type, disabled=True, key=f"sr_rtype_{srid}")
    with tc2:
        st.markdown("")  # spacer
    with tc3:
        offer_opts = _channel_offer_types()
        cur_offer = _row_offer_value(sub_row)
        oi = offer_opts.index(cur_offer) if cur_offer in offer_opts else 0
        new_offer = st.selectbox(_offer_field_label(), options=offer_opts, index=oi, key=f"sr_{srid}_otype")
        if new_offer != cur_offer:
            st.session_state.rows[idx]["sub_rows"][si][_offer_field_name()] = new_offer
    with tc4:
        new_oid = st.text_input("Offer ID", value=sub_row.get("offer_id", ""), key=f"sr_{srid}_oid")
        if new_oid != (sub_row.get("offer_id") or ""):
            st.session_state.rows[idx]["sub_rows"][si]["offer_id"] = new_oid
    # Placeholder captions for offer_id (outside column row to avoid misalignment)
    if sr_template_placeholders and "offer_id" in sr_template_placeholders and not (sub_row.get("offer_id") or "").strip():
        st.caption("⚠️ **Offer ID** is used as a placeholder in the SQL template — fill this in.")
    if sr_template_placeholders:
        _numbered_offer_phs = sorted(p for p in sr_template_placeholders if _re.match(r"^offer_id_\d+$", p))
        if _numbered_offer_phs:
            _offer_vals = [v.strip() for v in (sub_row.get("offer_id") or "").split(",") if v.strip()]
            _missing = [p for p in _numbered_offer_phs if int(p.split("_")[-1]) > len(_offer_vals)]
            if _missing:
                st.caption(f"⚠️ SQL template uses **{', '.join(_numbered_offer_phs)}** — enter comma-separated Offer IDs (e.g. `id1,id2`).")

    # ---- Required fields ----
    st.markdown("**Required Fields**")
    _sr_cols = st.columns(len(REQUIRED_COLUMNS))
    _sr_unfilled_placeholders = []
    for col_widget, field in zip(_sr_cols, REQUIRED_COLUMNS):
        with col_widget:
            if field in ("message", "title"):
                new_val = st.text_area(
                    f"{field} *", value=sub_row.get(field, ""),
                    key=f"sr_{srid}_{field}", height=80,
                )
            else:
                new_val = st.text_input(
                    f"{field} *", value=sub_row.get(field, ""),
                    key=f"sr_{srid}_{field}",
                )
            if new_val != (sub_row.get(field) or ""):
                st.session_state.rows[idx]["sub_rows"][si][field] = new_val
            if sr_template_placeholders and field in _CAPTION_FIELDS and field in sr_template_placeholders and not (sub_row.get(field) or "").strip():
                _sr_unfilled_placeholders.append(field)
    # Show placeholder captions outside the column row to avoid misalignment
    if _sr_unfilled_placeholders:
        st.caption("⚠️ **" + "**, **".join(_sr_unfilled_placeholders) + "** used as placeholder(s) in the SQL template — fill in above.")

    # ---- 🎯 Theme Variants ----
    st.markdown("**🎯 Theme Variants**")
    # Detect how many theme_N placeholders the SQL template uses
    _sr_theme_n_phs: list[str] = []
    if sub_row.get("custom_sql"):
        _sr_theme_n_phs = sorted(
            (p for p in sr_template_placeholders if _re.match(r"^theme_\d+$", p)),
            key=lambda x: int(x.split("_")[-1]),
        )
    _sr_theme_cols_count = 1 + len(_sr_theme_n_phs)
    _sr_theme_cols = st.columns(_sr_theme_cols_count)
    with _sr_theme_cols[0]:
        _new_theme = st.text_input(
            "theme *", value=sub_row.get("theme", ""),
            key=f"sr_{srid}_theme",
        )
        if _new_theme != (sub_row.get("theme") or ""):
            st.session_state.rows[idx]["sub_rows"][si]["theme"] = _new_theme
        if sr_template_placeholders and "theme" in sr_template_placeholders and not (sub_row.get("theme") or "").strip():
            st.caption("⚠️ **theme** is a placeholder in the SQL template — fill this in.")
    # Render auto-detected theme_N fields for SQL template sub-rows
    for _ti, _th_ph in enumerate(_sr_theme_n_phs):
        with _sr_theme_cols[_ti + 1]:
            _th_idx = int(_th_ph.split("_")[-1])
            _extra_themes = sub_row.get("extra_themes", [])
            _cur_val = _extra_themes[_th_idx - 1] if _th_idx - 1 < len(_extra_themes) else ""
            _new_th_val = st.text_input(
                f"{_th_ph} *",
                value=_cur_val,
                key=f"sr_{srid}_etheme_{_th_idx - 1}",
            )
            if _new_th_val != _cur_val:
                if "extra_themes" not in st.session_state.rows[idx]["sub_rows"][si]:
                    st.session_state.rows[idx]["sub_rows"][si]["extra_themes"] = []
                et_list = st.session_state.rows[idx]["sub_rows"][si]["extra_themes"]
                while len(et_list) < _th_idx:
                    et_list.append("")
                et_list[_th_idx - 1] = _new_th_val
            if not _cur_val.strip():
                st.caption(f"⚠️ **{_th_ph}** is required by the SQL template.")

    # ---- Rich Push Image toggle (PUSH channel only) ----
    if _current_channel() == "push":
        _rich_push = st.checkbox(
            "Rich Push Image", value=bool(sub_row.get("rich_push_image", False)),
            key=f"sr_{srid}_rich_push",
            help="When checked, media_url is required for this sub-row.",
        )
        if _rich_push != bool(sub_row.get("rich_push_image", False)):
            st.session_state.rows[idx]["sub_rows"][si]["rich_push_image"] = _rich_push

    # ---- Optional fields ----
    _sr_paste_success_key = f"_paste_success_sr_{srid}"
    _sr_paste_just_applied = st.session_state.pop(_sr_paste_success_key, False)
    if _sr_paste_just_applied:
        st.success(f"✅ Pasted fields applied: {_sr_paste_just_applied}")
    with st.expander("📎 Optional fields", expanded=bool(_sr_paste_just_applied)):
        for chunk_start in range(0, len(_optional_columns()), 3):
            chunk = _optional_columns()[chunk_start:chunk_start + 3]
            cols = st.columns(len(chunk))
            for col_widget, field in zip(cols, chunk):
                with col_widget:
                    new_val = st.text_input(
                        field, value=sub_row.get(field, ""),
                        key=f"sr_{srid}_{field}",
                    )
                    if new_val != (sub_row.get(field) or ""):
                        st.session_state.rows[idx]["sub_rows"][si][field] = new_val
                    # Inline guard: param_q must never contain underscores
                    if field == "param_q" and "_" in new_val:
                        st.warning("⚠️ `param_q` contains an underscore (`_`) — this field should not have underscores.")
                    # Inline guard: screentitle must never contain dashes
                    if field == "screentitle" and "-" in new_val:
                        st.warning("⚠️ `screentitle` contains a dash (`-`) — this field should not have dashes.")
                    # Inline guard: pushsection required when offer_type is PUSHSECTION
                    if field == "pushsection" and not new_val.strip() and (sub_row.get("offer_type") or "").upper() == "PUSHSECTION":
                        st.warning("⚠️ `pushsection` should not be blank when Offer Type is PUSHSECTION.")
                    # Inline guard: media_url required when Rich Push Image is checked
                    if field == "media_url" and not new_val.strip() and sub_row.get("rich_push_image"):
                        st.warning("⚠️ `media_url` should not be blank when Rich Push Image is checked.")

        # ---- Smart Paste parser ----
        st.markdown("---")
        st.caption("📋 **Paste deep-link params** — paste a `key=value` block copied from your source file to auto-fill the fields above.")
        _sr_paste_ctr_key = f"_paste_ctr_sr_{srid}"
        st.session_state.setdefault(_sr_paste_ctr_key, 0)
        _sr_paste_ta_key = f"sr_paste_{srid}_{st.session_state[_sr_paste_ctr_key]}"
        pasted = st.text_area(
            "Paste key=value block",
            height=100,
            key=_sr_paste_ta_key,
            placeholder="pushsection=aemLandingPage\nq=order/summer/fathers-day-ideas\nscreentitle=Father's_Day",
            label_visibility="collapsed",
        )
        if pasted.strip():
            _parsed, _unknown = _parse_key_value_block(pasted)
            for _k_raw in _unknown:
                st.caption(f"⚠️ Unrecognised key: `{_k_raw}` — skipped.")
            if _parsed:
                st.caption("**Preview — will be applied to this sub-row:**")
                _prev_cols = st.columns(min(len(_parsed), 3))
                for _pi, (_fld, _val) in enumerate(_parsed.items()):
                    with _prev_cols[_pi % 3]:
                        st.caption(f"`{_fld}` → `{_val}`")
                if st.button("✅ Apply", key=f"sr_paste_apply_{srid}", type="primary"):
                    _overrides = {}
                    for _fld, _val in _parsed.items():
                        st.session_state.rows[idx]["sub_rows"][si][_fld] = _val
                        _overrides[f"sr_{srid}_{_fld}"] = _val
                    # Schedule widget key pre-sets for next render (before widgets instantiate)
                    st.session_state["_pending_paste_overrides"] = _overrides
                    st.session_state[_sr_paste_ctr_key] += 1
                    st.session_state[_sr_paste_success_key] = ", ".join(_parsed.keys())
                    _save_from_session()
                    st.rerun()
            else:
                st.caption("⚠️ No recognised fields found. Expected format: `key=value`, one per line.")

    # ---- Targeting ----
    known_divs, known_banners = _load_targeting_hints()
    banner_options = _load_banner_options()
    division_options = _load_division_options()
    with st.expander("🎯 Targeting", expanded=False):
        # Division IDs — multiselect dropdown
        if division_options:
            vc, mc = st.columns([3, 1])
            with vc:
                cur_div_str = sub_row.get("division_ids", "")
                cur_div_display = _division_ids_to_display(cur_div_str, division_options)
                selected_divs = st.multiselect(
                    "Division IDs", options=division_options,
                    default=[d for d in cur_div_display if d in division_options],
                    key=f"sr_{srid}_division_ids",
                )
                new_div_str = ",".join(_division_display_to_id(d) for d in selected_divs)
                if new_div_str != (sub_row.get("division_ids") or ""):
                    st.session_state.rows[idx]["sub_rows"][si]["division_ids"] = new_div_str
            with mc:
                cur_mode = sub_row.get("division_mode", "IN")
                display_idx = 0 if cur_mode == "IN" else 1
                chosen_display = st.selectbox("division_ids mode", options=_MODE_OPTIONS, index=display_idx, key=f"sr_{srid}_division_mode")
                new_mode = _MODE_STORAGE[chosen_display]
                if new_mode != cur_mode:
                    st.session_state.rows[idx]["sub_rows"][si]["division_mode"] = new_mode
        else:
            # Fallback to text input if divisions.txt not found
            vc, mc = st.columns([3, 1])
            with vc:
                new_val = st.text_input(f"Division IDs{' (known: ' + ', '.join(str(d) for d in known_divs) + ')' if known_divs else ''}", value=sub_row.get("division_ids", ""), key=f"sr_{srid}_division_ids")
                if new_val != (sub_row.get("division_ids") or ""):
                    st.session_state.rows[idx]["sub_rows"][si]["division_ids"] = new_val
            with mc:
                cur_mode = sub_row.get("division_mode", "IN")
                display_idx = 0 if cur_mode == "IN" else 1
                chosen_display = st.selectbox("division_ids mode", options=_MODE_OPTIONS, index=display_idx, key=f"sr_{srid}_division_mode")
                new_mode = _MODE_STORAGE[chosen_display]
                if new_mode != cur_mode:
                    st.session_state.rows[idx]["sub_rows"][si]["division_mode"] = new_mode

        # Store IDs
        vc, mc = st.columns([3, 1])
        with vc:
            new_val = st.text_input("Store IDs", value=sub_row.get("store_ids", ""), key=f"sr_{srid}_store_ids")
            if new_val != (sub_row.get("store_ids") or ""):
                st.session_state.rows[idx]["sub_rows"][si]["store_ids"] = new_val
            _bad_sid = _invalid_store_id_tokens(new_val)
            if _bad_sid:
                st.error(
                    f"⛔ Non-numeric token(s): **{', '.join(_bad_sid)}** — "
                    f"enter numbers only, separated by commas (e.g. `100,200,300`)."
                )
        with mc:
            cur_mode = sub_row.get("store_mode", "IN")
            display_idx = 0 if cur_mode == "IN" else 1
            chosen_display = st.selectbox("store_ids mode", options=_MODE_OPTIONS, index=display_idx, key=f"sr_{srid}_store_mode")
            new_mode = _MODE_STORAGE[chosen_display]
            if new_mode != cur_mode:
                st.session_state.rows[idx]["sub_rows"][si]["store_mode"] = new_mode

        # Banners
        if banner_options:
            vc, mc = st.columns([3, 1])
            with vc:
                cur_banners_str = sub_row.get("banners", "")
                cur_banners_list = [b.strip().lower() for b in cur_banners_str.split(",") if b.strip()] if cur_banners_str else []
                selected_banners = st.multiselect(
                    "Banners", options=banner_options,
                    default=[b for b in cur_banners_list if b in banner_options],
                    key=f"sr_{srid}_banners",
                )
                new_banners_str = ",".join(selected_banners)
                if new_banners_str != (sub_row.get("banners") or ""):
                    st.session_state.rows[idx]["sub_rows"][si]["banners"] = new_banners_str
            with mc:
                cur_mode = sub_row.get("banner_mode", "IN")
                display_idx = 0 if cur_mode == "IN" else 1
                chosen_display = st.selectbox("banners mode", options=_MODE_OPTIONS, index=display_idx, key=f"sr_{srid}_banner_mode")
                new_mode = _MODE_STORAGE[chosen_display]
                if new_mode != cur_mode:
                    st.session_state.rows[idx]["sub_rows"][si]["banner_mode"] = new_mode
        else:
            vc, mc = st.columns([3, 1])
            with vc:
                new_val = st.text_input("Banners", value=sub_row.get("banners", ""), key=f"sr_{srid}_banners")
                if new_val != (sub_row.get("banners") or ""):
                    st.session_state.rows[idx]["sub_rows"][si]["banners"] = new_val
            with mc:
                cur_mode = sub_row.get("banner_mode", "IN")
                display_idx = 0 if cur_mode == "IN" else 1
                chosen_display = st.selectbox("banners mode", options=_MODE_OPTIONS, index=display_idx, key=f"sr_{srid}_banner_mode")
                new_mode = _MODE_STORAGE[chosen_display]
                if new_mode != cur_mode:
                    st.session_state.rows[idx]["sub_rows"][si]["banner_mode"] = new_mode

        # OR Groups
        groups = sub_row.get("div_banner_groups", [])
        st.markdown("---")
        st.caption("**Division + Banner/Store OR groups**")
        for gi, g in enumerate(groups):
            c1, c2, c3, c4, c5, c6, c7 = st.columns([1.2, 0.8, 1.5, 0.8, 1.2, 0.8, 0.5])
            with c1:
                g["division_ids"] = st.text_input(
                    "Division IDs", value=g.get("division_ids", ""),
                    key=f"sr_{srid}_or_div_{gi}", placeholder="29 or 5,17",
                    label_visibility="collapsed" if gi > 0 else "visible",
                )
            with c2:
                _dm_idx = 0 if g.get("div_mode", "IN") == "IN" else 1
                _dm_display = st.selectbox("Div Mode", options=_MODE_OPTIONS, index=_dm_idx, key=f"sr_{srid}_or_dmode_{gi}", label_visibility="collapsed" if gi > 0 else "visible")
                g["div_mode"] = _MODE_STORAGE[_dm_display]
            with c3:
                _or_banner_options = _load_banner_options()
                if _or_banner_options:
                    _cur_or_ban = g.get("banners", "")
                    _cur_or_ban_list = [b.strip().lower() for b in _cur_or_ban.split(",") if b.strip()] if _cur_or_ban else []
                    _sel_or_ban = st.multiselect("Banners", options=_or_banner_options, default=[b for b in _cur_or_ban_list if b in _or_banner_options], key=f"sr_{srid}_or_ban_{gi}", label_visibility="collapsed" if gi > 0 else "visible")
                    g["banners"] = ",".join(_sel_or_ban)
                else:
                    g["banners"] = st.text_input("Banners", value=g.get("banners", ""), key=f"sr_{srid}_or_ban_{gi}", placeholder="cedar_market,blueharbor", label_visibility="collapsed" if gi > 0 else "visible")
            with c4:
                _bm_idx = 0 if g.get("banner_mode", "IN") == "IN" else 1
                _bm_display = st.selectbox("Ban Mode", options=_MODE_OPTIONS, index=_bm_idx, key=f"sr_{srid}_or_bmode_{gi}", label_visibility="collapsed" if gi > 0 else "visible")
                g["banner_mode"] = _MODE_STORAGE[_bm_display]
            with c5:
                g["store_ids"] = st.text_input("Store IDs", value=g.get("store_ids", ""), key=f"sr_{srid}_or_sid_{gi}", placeholder="100,200", label_visibility="collapsed" if gi > 0 else "visible")
                _bad_sid = _invalid_store_id_tokens(g["store_ids"])
                if _bad_sid:
                    st.caption(f"⛔ Non-numeric: **{', '.join(_bad_sid)}** — digits only, comma-separated.")
            with c6:
                _sm_idx = 0 if g.get("store_mode", "IN") == "IN" else 1
                _sm_display = st.selectbox("Sto Mode", options=_MODE_OPTIONS, index=_sm_idx, key=f"sr_{srid}_or_smode_{gi}", label_visibility="collapsed" if gi > 0 else "visible")
                g["store_mode"] = _MODE_STORAGE[_sm_display]
            with c7:
                if gi == 0:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("✕", key=f"sr_{srid}_or_rm_{gi}", help="Remove this OR group"):
                    st.session_state.rows[idx]["sub_rows"][si]["div_banner_groups"].pop(gi)
                    _save_from_session()
                    st.rerun()
            groups[gi] = g

        if groups != sub_row.get("div_banner_groups", []):
            st.session_state.rows[idx]["sub_rows"][si]["div_banner_groups"] = groups
            _save_from_session()

        if st.button("＋ Add OR group", key=f"sr_{srid}_or_add"):
            if "div_banner_groups" not in st.session_state.rows[idx]["sub_rows"][si]:
                st.session_state.rows[idx]["sub_rows"][si]["div_banner_groups"] = []
            st.session_state.rows[idx]["sub_rows"][si]["div_banner_groups"].append({
                "division_ids": "", "div_mode": "IN",
                "banners": "", "banner_mode": "IN",
                "store_ids": "", "store_mode": "IN",
            })
            _save_from_session()
            st.rerun()

    # ---- Targeting notes ----
    with st.expander("📝 Targeting notes", expanded=False):
        current_notes = sub_row.get("targeting_notes", "")
        updated_notes = st.text_area(
            "Targeting instructions", value=current_notes,
            height=80, key=f"sr_{srid}_tnotes",
            placeholder="e.g. Include only customers from custom_audience WHERE segment = 'high_value'",
            label_visibility="collapsed",
        )
        if updated_notes != current_notes:
            st.session_state.rows[idx]["sub_rows"][si]["targeting_notes"] = updated_notes

    # ---- Custom JOINs ----
    cjoins = sub_row.get("custom_joins", [])
    cj_label = f"🔗 Custom JOINs ({len(cjoins)})" if cjoins else "🔗 Custom JOINs"
    with st.expander(cj_label, expanded=False):
        for ji, j in enumerate(cjoins):
            cur_mode = j.get("mode", "structured")
            mode_col, content_col, rm_col = st.columns([1, 6, 0.4])
            with mode_col:
                new_mode = st.selectbox("Mode", options=["structured", "freetext"], index=0 if cur_mode == "structured" else 1, key=f"sr_{srid}_cj_mode_{ji}", label_visibility="collapsed" if ji > 0 else "visible")
                j["mode"] = new_mode
            with content_col:
                if new_mode == "freetext":
                    j["raw_sql"] = st.text_area("SQL", value=j.get("raw_sql", ""), key=f"sr_{srid}_cj_raw_{ji}", height=100, label_visibility="collapsed" if ji > 0 else "visible")
                else:
                    sc1, sc2, sc3, sc4 = st.columns([1, 2.5, 0.7, 2.5])
                    with sc1:
                        j["join_type"] = st.selectbox("Type", options=_JOIN_TYPES, index=_JOIN_TYPES.index(j.get("join_type", "JOIN")) if j.get("join_type", "JOIN") in _JOIN_TYPES else 0, key=f"sr_{srid}_cj_type_{ji}", label_visibility="collapsed" if ji > 0 else "visible")
                    with sc2:
                        j["table_path"] = st.text_input("Table path", value=j.get("table_path", ""), key=f"sr_{srid}_cj_tbl_{ji}", label_visibility="collapsed" if ji > 0 else "visible")
                    with sc3:
                        j["alias"] = st.text_input("Alias", value=j.get("alias", ""), key=f"sr_{srid}_cj_alias_{ji}", label_visibility="collapsed" if ji > 0 else "visible")
                    with sc4:
                        j["on_clause"] = st.text_input("ON clause", value=j.get("on_clause", ""), key=f"sr_{srid}_cj_on_{ji}", label_visibility="collapsed" if ji > 0 else "visible")
            with rm_col:
                if ji == 0:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("✕", key=f"sr_{srid}_cj_rm_{ji}", help="Remove this JOIN"):
                    st.session_state.rows[idx]["sub_rows"][si]["custom_joins"].pop(ji)
                    _save_from_session()
                    st.rerun()
            cjoins[ji] = j

        if cjoins != sub_row.get("custom_joins", []):
            st.session_state.rows[idx]["sub_rows"][si]["custom_joins"] = cjoins
            _save_from_session()

        add_col1, add_col2 = st.columns(2)
        with add_col1:
            if st.button("＋ Add structured JOIN", key=f"sr_{srid}_cj_add"):
                if "custom_joins" not in st.session_state.rows[idx]["sub_rows"][si]:
                    st.session_state.rows[idx]["sub_rows"][si]["custom_joins"] = []
                st.session_state.rows[idx]["sub_rows"][si]["custom_joins"].append({
                    "mode": "structured", "join_type": "JOIN", "table_path": "", "alias": "", "on_clause": "",
                })
                _save_from_session()
                st.rerun()
        with add_col2:
            if st.button("＋ Add free-text JOIN", key=f"sr_{srid}_cj_addfree"):
                if "custom_joins" not in st.session_state.rows[idx]["sub_rows"][si]:
                    st.session_state.rows[idx]["sub_rows"][si]["custom_joins"] = []
                st.session_state.rows[idx]["sub_rows"][si]["custom_joins"].append({
                    "mode": "freetext", "raw_sql": "",
                })
                _save_from_session()
                st.rerun()

    # ---- SQL Template Picker (sub-rows) ----
    _sql_tpls = load_sql_templates()
    if _sql_tpls:
        _tpl_options = ["— None —"] + sorted(_sql_tpls.keys())
        _cur_tpl = sub_row.get("sql_template_name", "")
        # If the saved template was deleted from disk, keep it in the list so we don't auto-clear
        if _cur_tpl and _cur_tpl not in _tpl_options:
            _tpl_options.append(_cur_tpl)
        _effective_cur = _cur_tpl if _cur_tpl else "— None —"
        _tpl_idx = _tpl_options.index(_effective_cur)
        _new_tpl = st.selectbox(
            "🗄️ SQL Template",
            options=_tpl_options,
            index=_tpl_idx,
            key=f"sr_{srid}_sqltpl",
            help=(
                "Assign a pre-built SQL template to this sub-row. "
                "The template SQL replaces the standard INSERT at export. "
                "Row field values (theme, message, title, etc.) fill any "
                "Jinja2 {{ placeholders }} in the template. "
                "Select '— None —' to revert to standard form-row INSERT generation."
            ),
        )
        if _new_tpl != _effective_cur:
            if _new_tpl == "— None —":
                st.session_state.rows[idx]["sub_rows"][si]["custom_sql"] = ""
                st.session_state.rows[idx]["sub_rows"][si]["sql_template_name"] = ""
            else:
                st.session_state.rows[idx]["sub_rows"][si]["custom_sql"] = _sql_tpls[_new_tpl]
                st.session_state.rows[idx]["sub_rows"][si]["sql_template_name"] = _new_tpl
            _save_from_session()
            st.rerun()

    # ---- SQL template source (SQL sub-rows only) ----
    if sub_row.get("custom_sql"):
        with st.expander("🗄️ SQL template source (read-only)", expanded=False):
            st.code(sub_row["custom_sql"], language="sql")


def _render_row_form(idx: int, row: dict, is_dev: bool):
    """Render an expandable form for a single campaign row."""
    # RCS uses a fully separate form (SQL-name labels, nested cards editor, no PUSH fields).
    if _current_channel() == "rcs":
        _render_rcs_row_form(idx, row, is_dev)
        return

    rid = row.get("_row_id", str(idx))  # stable ID for widget keys
    row_label = row.get("campaign_name") or f"Row {idx + 1}"
    row_type = "sql" if row.get("custom_sql") else "form"
    is_multi = bool(row.get("multi_theme"))
    pri = row.get("priority", idx + 1)

    # ...existing code...

    # Expander label reflects multi-theme container status
    _exp_label = f"Row {pri} — {row_label}  [multi-theme]" if is_multi else f"Row {pri} — {row_label}  [{row_type}]"
    with st.expander(_exp_label, expanded=False):
        # ---- Handling time caption ----
        ht = row.get("handling_time", 0.0)
        st.caption(f"⏱️ Handling time: {_format_handling_time(ht)}")
        # Mark this row as active whenever any of its widgets fire
        _mark_row_active(rid)

        # ---- Multi Theme Campaign checkbox (form rows only) ----
        if row_type == "form":
            _mt_checked = st.checkbox(
                "Multi Theme Campaign",
                value=is_multi,
                key=f"frm_multi_theme_{rid}",
                help="Convert this row into a container with sub-rows that share the same priority.",
            )
            if _mt_checked != is_multi:
                if _mt_checked and any(row.get(f) for f in ("theme", "message", "title", "offer_type", "offer_id")):
                    # Row has data — defer until confirmation (Step 5 will add proper confirm)
                    st.session_state[f"_confirm_multi_theme_{rid}"] = True
                elif _mt_checked:
                    st.session_state.rows[idx]["multi_theme"] = True
                    st.session_state.rows[idx]["sub_rows"] = []
                    _save_from_session()
                    st.rerun()
                else:
                    # Unchecking — defer until confirmation (Step 5)
                    st.session_state[f"_confirm_revert_multi_{rid}"] = True

            # Confirmation for enabling multi-theme on a row with data
            if st.session_state.get(f"_confirm_multi_theme_{rid}"):
                st.warning("⚠️ Enabling Multi Theme Campaign will clear this row's form data and convert it to a container. Continue?")
                _cc1, _cc2 = st.columns(2)
                with _cc1:
                    if st.button("Yes, convert", key=f"confirm_mt_yes_{rid}"):
                        # Clear form fields, keep priority + campaign_name
                        for f in ("theme", "message", "title", "offer_type", "offer_id",
                                  "media_url", "pushsection", "param_q", "screentitle",
                                  "division_ids", "banners", "store_ids"):
                            st.session_state.rows[idx][f] = ""
                        st.session_state.rows[idx]["multi_theme"] = True
                        st.session_state.rows[idx]["sub_rows"] = []
                        st.session_state.pop(f"_confirm_multi_theme_{rid}", None)
                        _save_from_session()
                        st.rerun()
                with _cc2:
                    if st.button("Cancel", key=f"confirm_mt_no_{rid}"):
                        st.session_state.pop(f"_confirm_multi_theme_{rid}", None)
                        st.rerun()

            # Confirmation for reverting multi-theme back to normal row
            if st.session_state.get(f"_confirm_revert_multi_{rid}"):
                _sr_count = len(row.get("sub_rows", []))
                st.warning(f"⚠️ Disabling Multi Theme Campaign will **delete {_sr_count} sub-row(s)** and revert to a normal form row. Continue?")
                _rv1, _rv2 = st.columns(2)
                with _rv1:
                    _btn_color("red")
                    if st.button("Yes, revert", key=f"confirm_rv_yes_{rid}"):
                        st.session_state.rows[idx]["multi_theme"] = False
                        st.session_state.rows[idx]["sub_rows"] = []
                        st.session_state.pop(f"_confirm_revert_multi_{rid}", None)
                        _save_from_session()
                        st.rerun()
                with _rv2:
                    if st.button("Cancel", key=f"confirm_rv_no_{rid}"):
                        st.session_state.pop(f"_confirm_revert_multi_{rid}", None)
                        st.rerun()

        # ---- Multi-theme container view ----
        if is_multi:
            # Show only priority + campaign_name for the container
            _mc1, _mc2 = st.columns([1, 3], vertical_alignment="bottom")
            with _mc1:
                new_pri = st.number_input("Priority", value=int(pri), min_value=1, step=1, key=f"frm_pri_{rid}")
                if int(new_pri) != int(pri):
                    st.session_state.rows[idx]["priority"] = int(new_pri)
            with _mc2:
                new_cn = st.text_input("Campaign Name (group label)", value=row.get("campaign_name", ""), key=f"frm_cn_{rid}")
                if new_cn != (row.get("campaign_name") or ""):
                    st.session_state.rows[idx]["campaign_name"] = new_cn

            st.divider()
            st.markdown(f"**Sub-Rows** ({len(row.get('sub_rows', []))})")

            # Render existing sub-rows as nested expanders
            sub_rows = row.get("sub_rows", [])
            for si, sr in enumerate(sub_rows):
                sr_label = sr.get("campaign_name") or f"(empty)"
                _sr_type_tag = "sql" if sr.get("custom_sql") else "form"
                with st.expander(f"Row {pri}.{si + 1}: {sr_label}  [{_sr_type_tag}]", expanded=False):
                    _render_sub_row_form(idx, si, sr)
                    # ✕ Delete button for this sub-row
                    _btn_color("red")
                    if st.button(f"✕ Remove Sub-Row {pri}.{si + 1}", key=f"sr_rm_{rid}_{si}"):
                        st.session_state[f"_confirm_rm_sr_{rid}_{si}"] = True
                    if st.session_state.get(f"_confirm_rm_sr_{rid}_{si}"):
                        st.warning(f"⚠️ Remove **Row {pri}.{si + 1}: {sr_label}**?")
                        _rc1, _rc2 = st.columns(2)
                        with _rc1:
                            _btn_color("red")
                            if st.button("Yes, remove", key=f"sr_rm_yes_{rid}_{si}"):
                                st.session_state.rows[idx]["sub_rows"].pop(si)
                                st.session_state.pop(f"_confirm_rm_sr_{rid}_{si}", None)
                                _save_from_session()
                                st.rerun()
                        with _rc2:
                            if st.button("Cancel", key=f"sr_rm_no_{rid}_{si}"):
                                st.session_state.pop(f"_confirm_rm_sr_{rid}_{si}", None)
                                st.rerun()

            # Sub-row creation controls
            st.markdown("---")
            _sr_c1, _sr_c2 = st.columns([1, 2], vertical_alignment="bottom")
            with _sr_c1:
                sr_count = st.number_input("Sub-rows to create", min_value=1, max_value=50, value=1, step=1, key=f"sr_count_{rid}")
            with _sr_c2:
                if st.button("＋ Create Sub-Rows", key=f"sr_create_{rid}"):
                    for _ in range(int(sr_count)):
                        new_sr = {c: "" for c in _all_columns()}
                        new_sr["priority"] = int(pri)
                        new_sr["division_mode"] = "IN"
                        new_sr["banner_mode"] = "IN"
                        new_sr["store_mode"] = "IN"
                        new_sr["div_banner_groups"] = []
                        new_sr["custom_joins"] = []
                        new_sr["extra_themes"] = []
                        new_sr["rich_push_image"] = False
                        new_sr["targeting_notes"] = ""
                        new_sr["handling_time"] = 0.0
                        new_sr["_row_id"] = _new_row_id()
                        st.session_state.rows[idx]["sub_rows"].append(new_sr)
                    _save_from_session()
                    st.rerun()

            # ---- Split multi-theme back into separate rows ----
            if sub_rows:
                st.markdown("---")
                if st.button("↔ Split into separate rows", key=f"sr_split_{rid}",
                             help="Promote each sub-row to its own standalone row. Priorities will be renumbered sequentially."):
                    st.session_state[f"_confirm_split_{rid}"] = True
                if st.session_state.get(f"_confirm_split_{rid}"):
                    st.warning(f"⚠️ This will convert {len(sub_rows)} sub-row(s) into standalone rows and remove the multi-theme container. Continue?")
                    _sp1, _sp2 = st.columns(2)
                    with _sp1:
                        if st.button("Yes, split", key=f"confirm_split_yes_{rid}"):
                            # Remove the parent container and insert sub-rows in its place
                            split_rows = []
                            for sr in sub_rows:
                                sr["multi_theme"] = False
                                sr["sub_rows"] = []
                                if "_row_id" not in sr:
                                    sr["_row_id"] = _new_row_id()
                                split_rows.append(sr)
                            st.session_state.rows[idx:idx + 1] = split_rows
                            # Renumber priorities sequentially from the container's position
                            for i, r in enumerate(st.session_state.rows):
                                r["priority"] = i + 1
                            st.session_state.pop(f"_confirm_split_{rid}", None)
                            _clear_row_widget_state()
                            _save_from_session()
                            st.rerun()
                    with _sp2:
                        if st.button("Cancel", key=f"confirm_split_no_{rid}"):
                            st.session_state.pop(f"_confirm_split_{rid}", None)
                            st.rerun()

            if not sub_rows:
                st.info("No sub-rows yet. Use the controls above to create sub-rows.")
            return  # skip normal form rendering

        # ---- Top strip: priority, row_type, offer_type, offer_id ----
        # Detect Jinja2 placeholders in SQL template rows for caption hints
        _jinja_tpl_re = _re.compile(r"\{\{\s*(\w+)\s*\}\}")
        _CAPTION_FIELDS = {"offer_id", "theme", "message", "title"}
        template_placeholders = set(_jinja_tpl_re.findall(row.get("custom_sql", ""))) if row.get("custom_sql") else set()

        tc1, tc2, tc3, tc4 = st.columns([0.7, 0.7, 1.5, 1.5], vertical_alignment="bottom")
        with tc1:
            new_pri = st.number_input("Priority", value=int(pri), min_value=1, step=1, key=f"frm_pri_{rid}")
            if int(new_pri) != int(pri):
                st.session_state.rows[idx]["priority"] = int(new_pri)
        with tc2:
            st.text_input("Row Type", value=row_type, disabled=True, key=f"frm_rtype_{rid}")
        with tc3:
            offer_opts = _channel_offer_types()
            cur_offer = _row_offer_value(row)
            oi = offer_opts.index(cur_offer) if cur_offer in offer_opts else 0
            new_offer = st.selectbox(_offer_field_label(), options=offer_opts, index=oi, key=f"frm_otype_{rid}")
            if new_offer != cur_offer:
                st.session_state.rows[idx][_offer_field_name()] = new_offer
        with tc4:
            new_oid = st.text_input("Offer ID", value=row.get("offer_id", ""), key=f"frm_oid_{rid}")
            if new_oid != (row.get("offer_id") or ""):
                st.session_state.rows[idx]["offer_id"] = new_oid
        # Show placeholder caption outside the column row to avoid misalignment
        if template_placeholders and "offer_id" in template_placeholders and not (row.get("offer_id") or "").strip():
            st.caption("⚠️ **Offer ID** is used as a placeholder in the SQL template — fill this in.")
        # Check for numbered offer_id placeholders (offer_id_1, offer_id_2, ...)
        if template_placeholders:
            _numbered_offer_phs = sorted(p for p in template_placeholders if _re.match(r"^offer_id_\d+$", p))
            if _numbered_offer_phs:
                _offer_vals = [v.strip() for v in (row.get("offer_id") or "").split(",") if v.strip()]
                _missing = [p for p in _numbered_offer_phs if int(p.split("_")[-1]) > len(_offer_vals)]
                if _missing:
                    st.caption(f"⚠️ SQL template uses **{', '.join(_numbered_offer_phs)}** — enter comma-separated Offer IDs (e.g. `id1,id2`).")

        # ---- Required fields ----
        st.markdown("**Required Fields**")
        rc1, rc2, rc3 = st.columns(3)
        _unfilled_placeholders = []
        for col_widget, field in zip([rc1, rc2, rc3], REQUIRED_COLUMNS):
            with col_widget:
                # Use text_area for message and title so trailing spaces are preserved
                if field in ("message", "title"):
                    new_val = st.text_area(
                        f"{field} *",
                        value=row.get(field, ""),
                        key=f"frm_{field}_{rid}",
                        height=80,
                    )
                else:
                    new_val = st.text_input(
                        f"{field} *",
                        value=row.get(field, ""),
                        key=f"frm_{field}_{rid}",
                    )
                if new_val != (row.get(field) or ""):
                    st.session_state.rows[idx][field] = new_val
                if template_placeholders and field in _CAPTION_FIELDS and field in template_placeholders and not (row.get(field) or "").strip():
                    _unfilled_placeholders.append(field)
        # Show placeholder captions outside the column row to avoid misalignment
        if _unfilled_placeholders:
            st.caption("⚠️ **" + "**, **".join(_unfilled_placeholders) + "** used as placeholder(s) in the SQL template — fill in above.")

        # ---- 🎯 Theme Variants section ----
        st.markdown("**🎯 Theme Variants**")
        # Detect how many theme_N placeholders the SQL template uses
        _theme_n_phs: list[str] = []
        if row.get("custom_sql"):
            _theme_n_phs = sorted(
                (p for p in template_placeholders if _re.match(r"^theme_\d+$", p)),
                key=lambda x: int(x.split("_")[-1]),
            )
        # Build column layout: theme + theme_1 + theme_2 ... (all inline)
        _theme_cols_count = 1 + len(_theme_n_phs)
        _theme_cols = st.columns(_theme_cols_count)
        with _theme_cols[0]:
            _new_theme = st.text_input(
                "theme *",
                value=row.get("theme", ""),
                key=f"frm_theme_{rid}",
            )
            if _new_theme != (row.get("theme") or ""):
                st.session_state.rows[idx]["theme"] = _new_theme
            if template_placeholders and "theme" in template_placeholders and not (row.get("theme") or "").strip():
                st.caption("⚠️ **theme** is a placeholder in the SQL template — fill this in.")
        # Render auto-detected theme_N fields for SQL template rows
        for _ti, _th_ph in enumerate(_theme_n_phs):
            with _theme_cols[_ti + 1]:
                _th_idx = int(_th_ph.split("_")[-1])
                _extra_themes = row.get("extra_themes", [])
                _cur_val = _extra_themes[_th_idx - 1] if _th_idx - 1 < len(_extra_themes) else ""
                _new_th_val = st.text_input(
                    f"{_th_ph} *",
                    value=_cur_val,
                    key=f"frm_etheme_{rid}_{_th_idx - 1}",
                )
                if _new_th_val != _cur_val:
                    # Ensure extra_themes list is large enough
                    if "extra_themes" not in st.session_state.rows[idx]:
                        st.session_state.rows[idx]["extra_themes"] = []
                    et_list = st.session_state.rows[idx]["extra_themes"]
                    while len(et_list) < _th_idx:
                        et_list.append("")
                    et_list[_th_idx - 1] = _new_th_val
                if not _cur_val.strip():
                    st.caption(f"⚠️ **{_th_ph}** is required by the SQL template.")

        # ---- Rich Push Image toggle (PUSH channel only) ----
        if _current_channel() == "push":
            _rich_push = st.checkbox(
                "Rich Push Image",
                value=bool(row.get("rich_push_image", False)),
                key=f"frm_rich_push_{rid}",
                help="When checked, media_url is required for this row.",
            )
            if _rich_push != bool(row.get("rich_push_image", False)):
                st.session_state.rows[idx]["rich_push_image"] = _rich_push

        # ---- Optional fields (collapsed sub-expander) ----
        _paste_success_key = f"_paste_success_{rid}"
        _paste_just_applied = st.session_state.pop(_paste_success_key, False)
        if _paste_just_applied:
            st.success(f"✅ Pasted fields applied: {_paste_just_applied}")
        with st.expander("📎 Optional fields", expanded=bool(_paste_just_applied)):
            # Lay out optional fields in rows of 3
            _live_opt_cols = [c["name"] for c in _load_optional_columns_cfg() if c.get("ui_visible", True)]
            _opt_defs = {c["name"]: c for c in _load_optional_columns_cfg() if c.get("ui_visible", True)}
            for chunk_start in range(0, len(_live_opt_cols), 3):
                chunk = _live_opt_cols[chunk_start:chunk_start + 3]
                cols = st.columns(len(chunk))
                for col_widget, field in zip(cols, chunk):
                    with col_widget:
                        _fdef = _opt_defs.get(field, {})
                        _flabel = _fdef.get("label", field)
                        _fhelp = _fdef.get("help") or None
                        new_val = st.text_input(
                            _flabel,
                            value=row.get(field, ""),
                            key=f"frm_{field}_{rid}",
                            help=_fhelp,
                        )
                        if new_val != (row.get(field) or ""):
                            st.session_state.rows[idx][field] = new_val
                        # Inline guard: param_q must never contain underscores
                        if field == "param_q" and "_" in new_val:
                            st.warning("⚠️ `param_q` contains an underscore (`_`) — this field should not have underscores.")
                        # Inline guard: screentitle must never contain dashes
                        if field == "screentitle" and "-" in new_val:
                            st.warning("⚠️ `screentitle` contains a dash (`-`) — this field should not have dashes.")
                        # Inline guard: pushsection required when offer_type is PUSHSECTION
                        if field == "pushsection" and not new_val.strip() and (row.get("offer_type") or "").upper() == "PUSHSECTION":
                            st.warning("⚠️ `pushsection` should not be blank when Offer Type is PUSHSECTION.")
                        # Inline guard: media_url required when Rich Push Image is checked
                        if field == "media_url" and not new_val.strip() and row.get("rich_push_image"):
                            st.warning("⚠️ `media_url` should not be blank when Rich Push Image is checked.")

            # ---- Smart Paste parser ----
            st.markdown("---")
            st.caption("📋 **Paste deep-link params** — paste a `key=value` block copied from your source file to auto-fill the fields above.")
            _paste_ctr_key = f"_paste_ctr_{rid}"
            st.session_state.setdefault(_paste_ctr_key, 0)
            _paste_ta_key = f"frm_paste_{rid}_{st.session_state[_paste_ctr_key]}"
            pasted = st.text_area(
                "Paste key=value block",
                height=100,
                key=_paste_ta_key,
                placeholder="pushsection=aemLandingPage\nq=order/summer/fathers-day-ideas\nscreentitle=Father's_Day",
                label_visibility="collapsed",
            )
            if pasted.strip():
                _parsed, _unknown = _parse_key_value_block(pasted)
                for _k_raw in _unknown:
                    st.caption(f"⚠️ Unrecognised key: `{_k_raw}` — skipped.")
                if _parsed:
                    st.caption("**Preview — will be applied to this row:**")
                    _prev_cols = st.columns(min(len(_parsed), 3))
                    for _pi, (_fld, _val) in enumerate(_parsed.items()):
                        with _prev_cols[_pi % 3]:
                            st.caption(f"`{_fld}` → `{_val}`")
                    if st.button("✅ Apply", key=f"frm_paste_apply_{rid}", type="primary"):
                        _overrides = {}
                        for _fld, _val in _parsed.items():
                            st.session_state.rows[idx][_fld] = _val
                            _overrides[f"frm_{_fld}_{rid}"] = _val
                        # Schedule widget key pre-sets for next render (before widgets instantiate)
                        st.session_state["_pending_paste_overrides"] = _overrides
                        st.session_state[_paste_ctr_key] += 1  # resets text area
                        st.session_state[f"_paste_success_{rid}"] = ", ".join(_parsed.keys())
                        _save_from_session()
                        st.rerun()
                else:
                    st.caption("⚠️ No recognised fields found. Expected format: `key=value`, one per line.")

        # ---- Targeting (collapsed sub-expander) ----
        known_divs, known_banners = _load_targeting_hints()
        banner_options = _load_banner_options()
        division_options = _load_division_options()
        _render_row_targeting_ui(idx, row, rid, division_options, banner_options, known_divs)
        # ---- SQL Template Picker (all rows) ----
        _sql_tpls = load_sql_templates()
        if _sql_tpls:
            _tpl_options = ["— None —"] + sorted(_sql_tpls.keys())
            _cur_tpl = row.get("sql_template_name", "")
            # If the saved template was deleted from disk, keep it in the list so we don't auto-clear
            if _cur_tpl and _cur_tpl not in _tpl_options:
                _tpl_options.append(_cur_tpl)
            _effective_cur = _cur_tpl if _cur_tpl else "— None —"
            _tpl_idx = _tpl_options.index(_effective_cur)
            _new_tpl = st.selectbox(
                "🗄️ SQL Template",
                options=_tpl_options,
                index=_tpl_idx,
                key=f"frm_sqltpl_{rid}",
                help=(
                    "Assign a pre-built SQL template to this row. "
                    "The template SQL replaces the standard INSERT at export. "
                    "Row field values (theme, message, title, etc.) fill any "
                    "Jinja2 {{ placeholders }} in the template. "
                    "Select '— None —' to revert to standard form-row INSERT generation."
                ),
            )
            if _new_tpl != _effective_cur:
                if _new_tpl == "— None —":
                    st.session_state.rows[idx]["custom_sql"] = ""
                    st.session_state.rows[idx]["sql_template_name"] = ""
                else:
                    st.session_state.rows[idx]["custom_sql"] = _sql_tpls[_new_tpl]
                    st.session_state.rows[idx]["sql_template_name"] = _new_tpl
                _save_from_session()
                st.rerun()

        # ---- SQL template source (SQL rows only) ----
        if row.get("custom_sql"):
            with st.expander("🗄️ SQL template source (read-only)", expanded=False):
                st.code(row["custom_sql"], language="sql")
