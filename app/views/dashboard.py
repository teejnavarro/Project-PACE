# app/views/dashboard.py
"""Campaign Day Dashboard view."""

from datetime import datetime
from zoneinfo import ZoneInfo as _ZoneInfo

import streamlit as st

from storage import (
    STATUSES, create_campaign, delete_campaign, duplicate_campaign, list_campaigns,
    load_campaign, save_campaign,
)
from ui import (
    STATUS_COLORS, _btn_color, _channel_badge_html, _is_developer,
    _load_into_session, _pst_today, _sanitize_wk_id_key,
)


def render_dashboard():
    is_dev = _is_developer()
    _badge = _channel_badge_html()
    st.markdown(
        f"""
        <div style="margin:0 0 6px 0;">
            <div style="display:flex;align-items:center;gap:12px;">
                <div style="font-size:2.0em;line-height:1;">📋</div>
                <div style="font-size:2.0em;font-weight:800;letter-spacing:-0.02em;line-height:1.1;
                            background:linear-gradient(135deg,#e6edf3 0%,#8b95a7 100%);
                            -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                            background-clip:text;">
                    Campaign Dashboard
                </div>
                {_badge}
            </div>
            <div style="color:var(--pace-text-muted);font-size:0.95em;margin-top:4px;">
                Track campaign days from Draft to Exported. Click <b>Open</b> to edit a campaign day.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- Create new campaign day ----
    with st.expander("➕ Create New Campaign Day", expanded=False):
        nc_col1, nc_col2 = st.columns([1, 1])
        with nc_col1:
            new_wk_id = st.text_input(
                "Week ID (YYYYWW)",
                key="new_wk_id",
                max_chars=6,
                on_change=_sanitize_wk_id_key,
                args=("new_wk_id",),
                help="6 digits only (YYYYWW), e.g. 202629",
            )
        with nc_col2:
            _today_pst = _pst_today()
            new_send_date = st.date_input(
                "Send Date",
                value=_today_pst,
                min_value=_today_pst,
                key="new_send_date",
                help="Send Date must be today or later (PST). Past dates are blocked.",
            )
        if st.button("Create Campaign Day", type="primary"):
            new_wk_id = new_wk_id.strip()
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
            # --- Duplicate check ---
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
                    "Open the existing campaign instead of creating a duplicate."
                )
            else:
                campaign = create_campaign(
                    wk_id=new_wk_id,
                    send_date=str(new_send_date),
                    send_day=send_day,
                )
                save_campaign(campaign)
                st.success(f"Created campaign day for {new_send_date.strftime('%b %d, %Y')} ({send_day})")
                st.rerun()

    st.divider()

    # ---- List existing campaign days ----
    campaigns = list_campaigns()
    if not campaigns:
        st.info("No campaign days yet. Create one above to get started.")
        return

    # ---- Status summary strip ----
    status_counts = {}
    for c in campaigns:
        s = c.get("status", "Draft")
        status_counts[s] = status_counts.get(s, 0) + 1
    summary_parts = []
    for s in STATUSES:
        cnt = status_counts.get(s, 0)
        if cnt:
            color = STATUS_COLORS.get(s, "#787878")
            label = s if cnt == 1 else {
                "Draft": "Drafts",
                "Pending Assets": "Pending Assets",
                "In Progress": "In Progress",
                "Ready": "Ready",
                "Submitted": "Submitted",
                "Exported": "Exported",
                "Campaign Launched": "Campaigns Launched",
            }.get(s, s)
            summary_parts.append(
                f'<span style="display:inline-flex;align-items:center;gap:6px;'
                f'padding:5px 12px;border-radius:999px;'
                f'background:{color}22;border:1px solid {color}55;'
                f'color:{color};font-weight:700;font-size:0.85em;">'
                f'<span style="width:7px;height:7px;border-radius:50%;background:{color};'
                f'box-shadow:0 0 6px {color};"></span>{cnt} {label}</span>'
            )
    if summary_parts:
        st.markdown(
            "<div style='display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 4px 0;'>"
            + "".join(summary_parts) + "</div>",
            unsafe_allow_html=True,
        )

    # ---- Filter by status ----
    filter_col1, filter_col2 = st.columns([2, 4])
    with filter_col1:
        status_filter = st.multiselect(
            "Filter by status",
            options=STATUSES,
            default=[],
            key="dashboard_status_filter",
            placeholder="All statuses",
        )
    if status_filter:
        campaigns = [c for c in campaigns if c.get("status", "Draft") in status_filter]

    if not campaigns:
        st.info("No campaign days match the selected filter.")
        return

    st.markdown("<hr style='margin:4px 0'>", unsafe_allow_html=True)

    # User-visible statuses (users cannot manually set Exported or Campaign Launched)
    user_statuses = [s for s in STATUSES if s not in ("Exported", "Campaign Launched")]

    # ---- Dashboard table header ----
    if is_dev:
        col_widths = [0.3, 1.0, 0.9, 0.7, 0.4, 1.0, 1.4, 0.5, 0.4, 0.4]
        hdr_labels = [
            ("#", ""),
            ("Send Date", ""),
            ("Send Day", ""),
            ("Week ID", ""),
            ("Rows", ""),
            ("Last Modified", ""),
            ("Status", ""),
            ("", ""),
            ("", ""),
            ("", ""),
        ]
    else:
        col_widths = [0.3, 1.0, 0.9, 0.7, 0.4, 1.0, 1.4, 0.5, 0.4]
        hdr_labels = [
            ("#", ""),
            ("Send Date", ""),
            ("Send Day", ""),
            ("Week ID", ""),
            ("Rows", ""),
            ("Last Modified", ""),
            ("Status", ""),
            ("", ""),
            ("", ""),
        ]

    hdr_cols = st.columns(col_widths, vertical_alignment="center")
    for i, (col, (label, icon)) in enumerate(zip(hdr_cols, hdr_labels)):
        marker = '<span class="pace-dash-hdr-marker"></span>' if i == 0 else ""
        if not label:
            col.markdown(marker + "&nbsp;", unsafe_allow_html=True)
            continue
        icon_html = (
            f"<span style='color:#579bfc;margin-right:6px;font-size:0.9em;opacity:0.85;'>{icon}</span>"
            if icon else ""
        )
        col.markdown(
            f"{marker}<div class='pace-dash-hdr-cell'>{icon_html}"
            f"<span class='pace-dash-hdr-label'>{label}</span></div>",
            unsafe_allow_html=True,
        )

    # ---- Auto-transition: mark campaigns as "Campaign Launched" once 8 AM PST on send date ----
    _pst_now = datetime.now(_ZoneInfo("America/Los_Angeles"))
    _today_pst = _pst_now.date()
    _pst_hour = _pst_now.hour
    for c in campaigns:
        cur = c.get("status", "Draft")
        if cur == "Campaign Launched":
            continue
        try:
            send_dt = datetime.strptime(c["send_date"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        # Transition if send date is in the past, OR it's send day and already 8 AM+ PST
        if send_dt < _today_pst or (send_dt == _today_pst and _pst_hour >= 8):
            # Reload-and-merge so a concurrent editor's row edits are not clobbered.
            fresh = load_campaign(c["id"]) or c
            if fresh.get("status") == "Campaign Launched":
                c["status"] = "Campaign Launched"
                c["status_history"] = fresh.get("status_history", c.get("status_history", []))
                continue
            fresh["status"] = "Campaign Launched"
            history = fresh.get("status_history", [])
            history.append({"status": "Campaign Launched", "ts": _pst_now.isoformat()})
            fresh["status_history"] = history
            save_campaign(fresh)
            c["status"] = "Campaign Launched"
            c["status_history"] = history

    # ---- Pagination (state only; controls rendered below the rows) ----
    total_campaigns = len(campaigns)
    page_size_options = [25, 50, 100]
    if "dashboard_page_size" not in st.session_state:
        st.session_state.dashboard_page_size = 25
    if "dashboard_page" not in st.session_state:
        st.session_state.dashboard_page = 1

    page_size = st.session_state.dashboard_page_size
    total_pages = max(1, (total_campaigns + page_size - 1) // page_size)
    st.session_state.dashboard_page = min(max(1, st.session_state.dashboard_page), total_pages)
    current_page = st.session_state.dashboard_page

    page_start = (current_page - 1) * page_size
    page_end = page_start + page_size
    paged_campaigns = campaigns[page_start:page_end]

    # ---- Campaign rows ----
    for idx, c in enumerate(paged_campaigns, start=page_start + 1):
        row_cols = st.columns(col_widths, vertical_alignment="center")

        row_cols[0].markdown(f"{idx}")

        # Send Date
        try:
            d = datetime.strptime(c["send_date"], "%Y-%m-%d")
            row_cols[1].markdown(d.strftime('%b %d, %Y'))
        except (ValueError, KeyError):
            row_cols[1].markdown(c.get('send_date', '—'))

        # Send Day
        row_cols[2].markdown(c.get('send_day', '—'))
        # Week ID
        row_cols[3].markdown(c.get('wk_id', '—'))

        # Row count
        num_rows = len(c.get("rows", []))
        row_cols[4].markdown(f"{num_rows}")

        # Last Modified
        updated = c.get("updated_at", "")
        mod_str = "—"
        if updated:
            try:
                ts = datetime.fromisoformat(updated)
                mod_str = ts.strftime("%b %d %I:%M %p")
            except (ValueError, TypeError):
                pass
        row_cols[5].markdown(f"<span style='font-size:0.9em;'>{mod_str}</span>", unsafe_allow_html=True)

        # Status (color-coded selectbox, Monday.com style)
        cur_status = c.get("status", "Draft")
        avail_statuses = STATUSES if is_dev else user_statuses
        # Ensure the current status is always present so the selectbox
        # doesn't silently fall back to index 0 ("Draft") and overwrite it.
        if cur_status not in avail_statuses:
            avail_statuses = avail_statuses + [cur_status]
        idx_in_list = avail_statuses.index(cur_status)
        _status_bg = STATUS_COLORS.get(cur_status, "#787878")
        _status_cls = cur_status.lower().replace(" ", "-")
        row_cols[6].markdown(
            f'<span class="status-color status-{_status_cls}"></span>',
            unsafe_allow_html=True,
        )
        _launched = cur_status == "Campaign Launched"
        new_status = row_cols[6].selectbox(
            "status", options=avail_statuses,
            index=idx_in_list,
            key=f"status_{c['id']}",
            label_visibility="collapsed",
            disabled=_launched,
        )
        if new_status != cur_status and not _launched:
            c["status"] = new_status
            save_campaign(c)
            st.rerun()

        # Open button
        if row_cols[7].button("Open", key=f"open_{c['id']}"):
            # Log the open event in the activity log
            log = c.get("activity_log", [])
            log.append({"action": "Opened", "ts": datetime.now().isoformat()})
            c["activity_log"] = log
            save_campaign(c)
            _load_into_session(c)
            st.session_state.view = "detail"
            st.session_state.generated_sql = ""
            st.rerun()

        # Clone button (#4)
        if row_cols[8].button("📋", key=f"clone_{c['id']}", help="Duplicate this campaign day"):
            clone = duplicate_campaign(c["id"])
            if clone:
                st.success(f"Cloned → new draft for {clone.get('send_date', '')}")
                st.rerun()

        # Delete button — developer only (#9 confirmation)
        if is_dev:
            with row_cols[9]:
                _btn_color("red")
                if st.button("🗑️", key=f"del_{c['id']}"):
                    st.session_state[f"confirm_del_{c['id']}"] = True
            if st.session_state.get(f"confirm_del_{c['id']}"):
                st.warning(f"⚠️ Delete campaign day **{c.get('send_date', '')} ({c.get('send_day', '')})**? This cannot be undone.")
                ccol1, ccol2 = st.columns(2)
                with ccol1:
                    _btn_color("red")
                    if st.button("Yes, delete", key=f"confirm_yes_{c['id']}", type="primary"):
                        delete_campaign(c["id"])
                        st.session_state.pop(f"confirm_del_{c['id']}", None)
                        st.rerun()
                if ccol2.button("Cancel", key=f"confirm_no_{c['id']}"):
                    st.session_state.pop(f"confirm_del_{c['id']}", None)
                    st.rerun()

    # ---- Pagination controls (bottom of dashboard) ----
    st.markdown("<hr style='margin:12px 0 8px 0;border:none;border-top:1px solid rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
    pg_col1, pg_col2, pg_col3, pg_col4, pg_col5, pg_col6 = st.columns(
        [1.2, 0.5, 0.5, 1.0, 0.5, 0.5], vertical_alignment="center"
    )
    with pg_col1:
        new_size = st.selectbox(
            "Rows per page",
            options=page_size_options,
            index=page_size_options.index(page_size) if page_size in page_size_options else 0,
            key="dashboard_page_size_select",
            label_visibility="collapsed",
        )
        if new_size != page_size:
            st.session_state.dashboard_page_size = new_size
            st.session_state.dashboard_page = 1
            st.rerun()
    with pg_col2:
        if st.button("« First", key="pg_first", disabled=current_page <= 1, use_container_width=True):
            st.session_state.dashboard_page = 1
            st.rerun()
    with pg_col3:
        if st.button("‹ Prev", key="pg_prev", disabled=current_page <= 1, use_container_width=True):
            st.session_state.dashboard_page -= 1
            st.rerun()
    with pg_col4:
        start_i = (current_page - 1) * page_size + 1 if total_campaigns else 0
        end_i = min(current_page * page_size, total_campaigns)
        st.markdown(
            f"<div style='text-align:center;font-size:0.88em;color:var(--pace-text-muted);'>"
            f"Page <b style='color:var(--pace-text);'>{current_page}</b> of "
            f"<b style='color:var(--pace-text);'>{total_pages}</b> · "
            f"showing <b style='color:var(--pace-text);'>{start_i}–{end_i}</b> of "
            f"<b style='color:var(--pace-text);'>{total_campaigns}</b>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with pg_col5:
        if st.button("Next ›", key="pg_next", disabled=current_page >= total_pages, use_container_width=True):
            st.session_state.dashboard_page += 1
            st.rerun()
    with pg_col6:
        if st.button("Last »", key="pg_last", disabled=current_page >= total_pages, use_container_width=True):
            st.session_state.dashboard_page = total_pages
            st.rerun()
