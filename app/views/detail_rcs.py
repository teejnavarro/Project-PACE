# app/views/detail_rcs.py
"""RCS row form: cards, buttons, CHOICE/CARD/CAROUSEL editors."""

import streamlit as st
from ui import (
    _RCS_CARD_COUNTS, _channel_offer_types, _format_handling_time, _load_banner_options,
    _load_division_options, _load_optional_columns_cfg, _mark_row_active, _offer_field_label,
    _offer_field_name, _row_offer_value,
)
from views.detail_common import _load_targeting_hints, _render_row_targeting_ui


def _rcs_ensure_button(container: list, b_idx: int) -> None:
    """Grow a buttons[] list in-place so index b_idx is a valid entry."""
    while len(container) <= b_idx:
        container.append({"title": "", "value": "", "sso_url": "", "push_section": ""})


def _rcs_ensure_card(cards: list, c_idx: int) -> None:
    """Grow a cards[] list in-place so index c_idx is a valid entry."""
    while len(cards) <= c_idx:
        cards.append({"body": "", "media_title": "", "media_url": "", "message_footer": "", "buttons": []})


def _render_rcs_button_editor(idx: int, row: dict, rid: str, container_path: tuple, b_idx: int, prefix: str, n: int, key_ns: str, inline: bool = False):
    """Render one button. container_path is a tuple describing where to write the value
    inside st.session_state.rows[idx], e.g. ("cards", 0, "buttons") for card[0].buttons[b_idx],
    or ("general_buttons",) for row['general_buttons'][b_idx].
    When inline=True, render the fields directly (no per-button expander) — used when the
    caller already wraps them in an outer expander (Streamlit disallows double-nested expanders).
    """
    def _write(field: str, val):
        # Navigate down through container_path, then buttons[b_idx][field]
        target = st.session_state.rows[idx]
        for step in container_path:
            target = target[step] if isinstance(target, list) else target[step]
        _rcs_ensure_button(target, b_idx)
        target[b_idx][field] = val

    # Read current button dict from the row
    src = row
    for step in container_path:
        src = src[step] if isinstance(src, list) else src[step]
    _rcs_ensure_button(src, b_idx)
    btn = src[b_idx]

    def _render_fields():
        bc1, bc2 = st.columns(2)
        with bc1:
            new_title = st.text_input(f"{prefix}_BUTTON_TITLE_{n}", value=btn.get("title", ""), key=f"{key_ns}_ttl_{b_idx}")
            if new_title != btn.get("title", ""):
                _write("title", new_title)
        with bc2:
            new_ps = st.text_input(f"{prefix}_BUTTON_PUSH_SECTION_{n}", value=btn.get("push_section", ""),
                                    key=f"{key_ns}_ps_{b_idx}",
                                    help="Push section identifier, e.g. weeklyAd, aemLandingPage, Offer&pushOfferID=...&pushOfferType=CC")
            if new_ps != btn.get("push_section", ""):
                _write("push_section", new_ps)

        new_value = st.text_input(f"{prefix}_BUTTON_VALUE_{n}", value=btn.get("value", ""),
                                   key=f"{key_ns}_val_{b_idx}",
                                   help="Landing page URL. Shorthand supported: type `[BANNER]` inline as a placeholder for the store banner, OR paste just the tail starting with `.com/...` (e.g. `.com/shop/product-details.960109101.html`) and the `'https://www.' || REPLACE(...) ||` boilerplate is prepended automatically at export time.")
        if new_value != btn.get("value", ""):
            _write("value", new_value)

        sso_val = str(btn.get("sso_url", "")).strip().lower()
        sso_checked = sso_val in ("yes", "y", "true", "1")
        new_sso = st.checkbox(f"{prefix}_BUTTON_SSO_URL_{n}  (requires sign-in?)", value=sso_checked,
                               key=f"{key_ns}_sso_{b_idx}",
                               help="When checked, the canonical SSO URL expression is emitted. When unchecked, emits ''.")
        new_sso_val = "yes" if new_sso else ""
        if new_sso_val != btn.get("sso_url", ""):
            _write("sso_url", new_sso_val)

    if inline:
        _render_fields()
        return

    with st.expander(f"{prefix}_BUTTON_{n}  —  {btn.get('title') or '(empty)'}", expanded=(b_idx == 0)):
        _render_fields()


def _render_rcs_card_content(idx: int, row: dict, rid: str, card_idx: int, channelsubtype: str):
    """Render one card's editable content: MESSAGE_BODY_N, media (if CARD/CAROUSEL), 4 buttons."""
    n = card_idx + 1
    _rcs_ensure_card(row.setdefault("cards", []), card_idx)
    card = row["cards"][card_idx]

    def _write_card(field: str, val):
        st.session_state.rows[idx]["cards"][card_idx][field] = val

    # Card 1 pairs MESSAGE_BODY_1 with FALLBACK_MESSAGE_BODY side-by-side;
    # other cards render MESSAGE_BODY_N alone.
    if n == 1:
        bc1, bc2 = st.columns(2)
        with bc1:
            new_body = st.text_area(f"MESSAGE_BODY_{n}", value=card.get("body", ""), height=110,
                                     key=f"rcs_body_{rid}_{n}",
                                     help="RCS card message body. Up to ~122 chars per CRF convention.")
            if new_body != card.get("body", ""):
                _write_card("body", new_body)
        with bc2:
            cur_fb = str(row.get("fallback_message_body", ""))
            new_fb = st.text_area("FALLBACK_MESSAGE_BODY", value=cur_fb, height=110,
                                   key=f"rcs_opt_fallback_message_body_{rid}",
                                   help="SMS fallback text if RCS delivery fails. The `[BANNER]:` prefix is added automatically at export time.")
            if new_fb != cur_fb:
                st.session_state.rows[idx]["fallback_message_body"] = new_fb
            if cur_fb.strip().lower().startswith("[banner]:"):
                st.warning("⚠️ Remove the leading `[BANNER]:` — it is added automatically at export time.")
    else:
        new_body = st.text_area(f"MESSAGE_BODY_{n}", value=card.get("body", ""), height=90,
                                 key=f"rcs_body_{rid}_{n}",
                                 help="RCS card message body. Up to ~122 chars per CRF convention.")
        if new_body != card.get("body", ""):
            _write_card("body", new_body)

    # MESSAGE_FOOTER_1 is a legal constant for every subtype; cards 2+ are user-toggled
    # (only reachable in CARD / CAROUSEL — CHOICE has one card).
    if n == 1:
        st.caption("ℹ️ **MESSAGE_FOOTER_1** = `' Txt STOP 2 end'` (required legal footer — always included, cannot be changed).")
    elif channelsubtype in ("CARD", "CAROUSEL"):
        cur_flag = str(card.get("message_footer", "") or "").strip().lower()
        # Legacy default: if no explicit flag was ever set but the body was populated,
        # the pre-checkbox template auto-emitted the footer, so mirror that here.
        if "message_footer" not in card:
            default_checked = bool((card.get("body") or "").strip())
        else:
            default_checked = cur_flag in ("yes", "y", "true", "1")
        new_flag = st.checkbox(
            f"MESSAGE_FOOTER_{n}  — include legal footer `' Txt STOP 2 end'`",
            value=default_checked,
            key=f"rcs_footer_{rid}_{n}",
            help="When checked, emits ' Txt STOP 2 end' (with leading space) for this card. When unchecked, emits ''.",
        )
        new_val = "yes" if new_flag else ""
        if new_val != card.get("message_footer", ""):
            _write_card("message_footer", new_val)

    if channelsubtype in ("CARD", "CAROUSEL"):
        mc1, mc2 = st.columns(2)
        with mc1:
            new_mt = st.text_input(f"MEDIA_TITLE_{n}", value=card.get("media_title", ""), key=f"rcs_mt_{rid}_{n}")
            if new_mt != card.get("media_title", ""):
                _write_card("media_title", new_mt)
        with mc2:
            new_mu = st.text_input(f"MEDIA_URL_{n}", value=card.get("media_url", ""), key=f"rcs_mu_{rid}_{n}")
            if new_mu != card.get("media_url", ""):
                _write_card("media_url", new_mu)

    if channelsubtype == "CHOICE":
        with st.expander("Buttons", expanded=False):
            _render_rcs_button_editor(
                idx, row, rid,
                container_path=("cards", card_idx, "buttons"),
                b_idx=0, prefix="FIRST", n=n,
                key_ns=f"rcs_btn_{rid}_{n}",
                inline=True,
            )
    else:
        st.markdown("**Buttons**")
        for b_idx, pfx in enumerate(("FIRST", "SECOND", "THIRD", "FOURTH")):
            _render_rcs_button_editor(
                idx, row, rid,
                container_path=("cards", card_idx, "buttons"),
                b_idx=b_idx, prefix=pfx, n=n,
                key_ns=f"rcs_btn_{rid}_{n}",
            )


def _render_rcs_general_buttons(idx: int, row: dict, rid: str):
    """Render 3 GENERAL_BUTTON_* rows (CAROUSEL only — applies to all cards)."""
    row.setdefault("general_buttons", [])
    st.caption("GENERAL_BUTTON_* fields apply to **every** card in the carousel.")
    for gb_idx in range(3):
        n = gb_idx + 1
        _render_rcs_button_editor(
            idx, row, rid,
            container_path=("general_buttons",),
            b_idx=gb_idx, prefix="GENERAL", n=n,
            key_ns=f"rcs_gb_{rid}",
        )


def _render_rcs_cards_editor(idx: int, row: dict, rid: str, channelsubtype: str):
    """Render the card tabs + count controls for the current CHANNEL_SUB_TYPE."""
    row.setdefault("cards", [])
    min_c, max_c = _RCS_CARD_COUNTS.get(channelsubtype, (1, 1))

    if channelsubtype == "CHOICE":
        card_count = 1
    elif channelsubtype == "CARD":
        card_count = max(min_c, min(max_c, len(row["cards"]) or 1))
        col_a, col_b, col_c = st.columns([2, 1, 1], vertical_alignment="bottom")
        with col_a:
            st.markdown(f"**Cards: {card_count} / {max_c}**")
        with col_b:
            if st.button("＋ Add card", disabled=card_count >= max_c, key=f"rcs_add_card_{rid}"):
                row["cards"].append({"body": "", "media_title": "", "media_url": "", "message_footer": "", "buttons": []})
                st.session_state.rows[idx]["cards"] = row["cards"]
                st.rerun()
        with col_c:
            if st.button("－ Remove card", disabled=card_count <= min_c, key=f"rcs_rm_card_{rid}"):
                if len(row["cards"]) > min_c:
                    row["cards"].pop()
                    st.session_state.rows[idx]["cards"] = row["cards"]
                st.rerun()
    elif channelsubtype == "CAROUSEL":
        opts = [2, 3, 4, 5, 6, 7]
        cur = int(row.get("carousel_card_count") or 2)
        cur_idx = opts.index(cur) if cur in opts else 0
        card_count = st.selectbox("Number of cards", options=opts, index=cur_idx, key=f"rcs_carousel_cnt_{rid}")
        if card_count != cur:
            st.session_state.rows[idx]["carousel_card_count"] = card_count
    else:
        card_count = 1

    while len(row["cards"]) < card_count:
        row["cards"].append({"body": "", "media_title": "", "media_url": "", "message_footer": "", "buttons": []})
    st.session_state.rows[idx]["cards"] = row["cards"]

    # CHOICE has a single message — render inline with no tab strip or border wrapper.
    if channelsubtype == "CHOICE":
        _render_rcs_card_content(idx, row, rid, 0, channelsubtype)
        return

    tab_labels = [f"Card {i + 1}" for i in range(card_count)]
    if channelsubtype == "CAROUSEL":
        tab_labels.append("General Buttons")

    # Marker so CSS in main() can add extra spacing under the tab strip.
    st.markdown('<div class="rcs-card-tabs-scope"></div>', unsafe_allow_html=True)
    tabs = st.tabs(tab_labels)
    for i in range(card_count):
        with tabs[i]:
            with st.container(border=True):
                _render_rcs_card_content(idx, row, rid, i, channelsubtype)
    if channelsubtype == "CAROUSEL":
        with tabs[-1]:
            with st.container(border=True):
                _render_rcs_general_buttons(idx, row, rid)


def _render_rcs_row_form(idx: int, row: dict, is_dev: bool):
    """Render an expandable form for a single RCS campaign row.
    Fully independent of PUSH's _render_row_form — all labels use SQL column names.
    """
    rid = row.get("_row_id", str(idx))
    row_label = row.get("campaign_name") or f"Row {idx + 1}"
    pri = row.get("priority", idx + 1)
    channelsubtype = _row_offer_value(row) or ""
    _exp_label = f"Row {pri} — {row_label}  [{channelsubtype or 'no CHANNEL_SUB_TYPE'}]"

    with st.expander(_exp_label, expanded=False):
        ht = row.get("handling_time", 0.0)
        st.caption(f"⏱️ Handling time: {_format_handling_time(ht)}")
        _mark_row_active(rid)

        # ---- Top strip: priority, CHANNEL_SUB_TYPE, campaign_name ----
        tc1, tc2, tc3 = st.columns([1, 2, 3], vertical_alignment="bottom")
        with tc1:
            new_pri = st.number_input("Priority", min_value=1, value=int(pri), step=1, key=f"rcs_pri_{rid}")
            if int(new_pri) != int(pri):
                st.session_state.rows[idx]["priority"] = int(new_pri)
        with tc2:
            offer_opts = _channel_offer_types()
            cur = _row_offer_value(row)
            oi = offer_opts.index(cur) if cur in offer_opts else 0
            new_cst = st.selectbox(_offer_field_label(), options=offer_opts, index=oi, key=f"rcs_cst_{rid}")
            if new_cst != cur:
                st.session_state.rows[idx][_offer_field_name()] = new_cst
        with tc3:
            new_cn = st.text_input("campaign_name", value=row.get("campaign_name", ""), key=f"rcs_cn_{rid}")
            if new_cn != row.get("campaign_name", ""):
                st.session_state.rows[idx]["campaign_name"] = new_cn

        # BU_CC_ID and THEME sit at the top of the form (both are required-ish enough
        # that the CRF always populates them). BU_CC_ID renders first per team convention.
        th1, th2 = st.columns(2)
        with th1:
            cur_bu = str(row.get("bu_cc_id", ""))
            new_bu = st.text_input("BU_CC_ID", value=cur_bu, key=f"rcs_bu_cc_id_{rid}",
                                    help="Business-unit / campaign-code prefix. Must end in an underscore (e.g. `region-promo_`).")
            if new_bu != cur_bu:
                st.session_state.rows[idx]["bu_cc_id"] = new_bu
        with th2:
            new_theme = st.text_input("THEME", value=row.get("theme", ""), key=f"rcs_theme_{rid}")
            if new_theme != row.get("theme", ""):
                st.session_state.rows[idx]["theme"] = new_theme

        # BU_CC_ID + FALLBACK_MESSAGE_BODY are rendered outside this loop
        # (top-strip and Card 1 respectively) so skip them here.
        def _render_rcs_optional_fields():
            with st.expander("Optional Fields", expanded=False):
                for col_def in _load_optional_columns_cfg():
                    if not col_def.get("ui_visible", True):
                        continue
                    field = col_def["name"]
                    if field in ("fallback_message_body", "bu_cc_id"):
                        continue
                    label = col_def.get("label", field)
                    sql_type = col_def.get("sql_type", "text")
                    help_text = col_def.get("help", "")

                    if sql_type == "bool":
                        val = bool(row.get(field, False))
                        new_val = st.checkbox(label, value=val, key=f"rcs_opt_{field}_{rid}", help=help_text)
                        if new_val != val:
                            st.session_state.rows[idx][field] = new_val
                    else:
                        val = str(row.get(field, ""))
                        new_val = st.text_input(label, value=val, key=f"rcs_opt_{field}_{rid}", help=help_text)
                        if new_val != val:
                            st.session_state.rows[idx][field] = new_val

        # CHOICE mirrors the PUSH ordering: message + buttons come first, Optional Fields last.
        if channelsubtype != "CHOICE":
            _render_rcs_optional_fields()

        # ---- Cards editor (offer-type dependent) ----
        if channelsubtype and channelsubtype != "CHOICE":
            st.markdown("---")
            st.markdown(f"### 🎴 Cards  ({channelsubtype})")
        if channelsubtype:
            _render_rcs_cards_editor(idx, row, rid, channelsubtype)
        else:
            st.info("Pick a CHANNEL_SUB_TYPE above to enable the cards editor.")

        if channelsubtype == "CHOICE":
            _render_rcs_optional_fields()

        # ---- Targeting (shared with PUSH) ----
        known_divs, _known_banners = _load_targeting_hints()
        banner_options = _load_banner_options()
        division_options = _load_division_options()
        _render_row_targeting_ui(idx, row, rid, division_options, banner_options, known_divs)
