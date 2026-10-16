# app/views/analytics.py
"""Developer-only Build Analytics view."""

import math as _math
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from storage import list_campaigns
from ui import (
    _CHANNEL_LABELS, _DOW_ORDER, _DOW_SHORT, _channel_badge_html,
    _current_channel, _is_developer, _round_handling_time_total,
)


# ──────────────────────────────────────────────
# BUILD TIME ANALYTICS — DATA COMPUTATION
# ──────────────────────────────────────────────

def _compute_campaign_analytics(campaigns: list) -> pd.DataFrame:
    """Compute build time metrics for all campaigns and return as a DataFrame.

    Key metrics:
    - elapsed_to_submit_min : wall-clock minutes from Created → Submitted for Export
    - handling_min          : sum of per-row active-editing time (handling_time * 60)
    - open_count            : number of times the campaign was opened
    - save_count            : number of explicit save events
    - audit_changes         : number of audit log entries (granular row edits)
    """
    records = []
    for c in campaigns:
        wk_id = c.get("wk_id", "")
        send_date = c.get("send_date", "")
        send_day = (c.get("send_day") or "").upper()
        status = c.get("status", "Draft")
        rows = c.get("rows", [])
        num_rows = len(rows)

        # Per-row active editing time (raw hours) — rounding applied to the total
        raw_handling_hrs = sum(r.get("handling_time", 0.0) for r in rows)
        total_handling_hrs = _round_handling_time_total(raw_handling_hrs)

        # Parse activity_log for timestamps and counts
        activity_log = c.get("activity_log", [])
        created_ts = c.get("created_at", "")
        submitted_ts = None
        open_count = 0
        save_count = 0

        for event in activity_log:
            action = event.get("action", "")
            ts_str = event.get("ts", "")
            if action == "Submitted for Export" and submitted_ts is None:
                submitted_ts = ts_str
            if action in ("Saved", "Save as Pending Assets"):
                save_count += 1
            if action == "Opened":
                open_count += 1

        # Elapsed time: Created → first Submitted for Export
        elapsed_to_submit_min = None
        if created_ts and submitted_ts:
            try:
                t0 = datetime.fromisoformat(created_ts)
                t1 = datetime.fromisoformat(submitted_ts)
                elapsed_to_submit_min = max(0.0, (t1 - t0).total_seconds() / 60)
            except (ValueError, TypeError):
                pass

        # Audit granularity
        audit_count = len(c.get("audit", []))

        # Form vs SQL row split
        form_rows = sum(1 for r in rows if not r.get("custom_sql"))
        sql_rows = sum(1 for r in rows if r.get("custom_sql"))

        records.append({
            "id": c.get("id", ""),
            "wk_id": wk_id,
            "send_date": send_date,
            "send_day": send_day,
            "status": status,
            "num_rows": num_rows,
            "form_rows": form_rows,
            "sql_rows": sql_rows,
            "handling_hrs": round(total_handling_hrs, 3),
            "handling_min": round(total_handling_hrs * 60, 1),
            "elapsed_to_submit_min": (
                round(elapsed_to_submit_min, 1) if elapsed_to_submit_min is not None else None
            ),
            "created_at": created_ts,
            "open_count": open_count,
            "save_count": save_count,
            "audit_changes": audit_count,
        })
    return pd.DataFrame(records) if records else pd.DataFrame()


def render_analytics():
    """Developer-only Build Time Analytics dashboard."""
    if not _is_developer():
        st.warning("Build Time Analytics is available for Developers only.")
        if st.button("← Back to Dashboard", key="analytics_back_nodev"):
            st.session_state.view = "dashboard"
            st.rerun()
        return

    _ch_label = _CHANNEL_LABELS.get(_current_channel(), "PUSH")
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:14px;margin-bottom:2px;'>"
        f"<h2 style='margin:0;'>📊 {_ch_label} Build Time Analytics</h2>"
        f"{_channel_badge_html()}</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"{_ch_label} campaign build velocity, effort, and trends — "
        "derived from activity logs and per-row handling time. Use for business case and process improvement."
    )

    col_back, col_spacer = st.columns([1, 5])
    with col_back:
        if st.button("← Dashboard", key="analytics_back"):
            st.session_state.view = "dashboard"
            st.rerun()

    campaigns = list_campaigns()
    if not campaigns:
        st.info("No campaign data available yet.")
        return

    df_all = _compute_campaign_analytics(campaigns)
    if df_all.empty:
        st.info("Could not compute analytics — campaign data may be incomplete.")
        return

    all_weeks = sorted(df_all["wk_id"].unique().tolist())

    def _week_filter(key_suffix: str, df_in: pd.DataFrame) -> pd.DataFrame:
        """Render an inline week include/exclude filter and return filtered DataFrame."""
        fc1, fc2 = st.columns([1, 2])
        with fc1:
            mode = st.radio(
                "Mode", ["Include selected", "Exclude selected"],
                horizontal=True, key=f"fmode_{key_suffix}", label_visibility="collapsed",
            )
        with fc2:
            sel = st.multiselect(
                "Weeks", options=all_weeks, default=[],
                key=f"fweeks_{key_suffix}",
                format_func=lambda w: f"Wk{w[-2:]}" if len(w) >= 2 else w,
                placeholder="Filter weeks…",
            )
        if not sel:
            return df_in
        if mode == "Include selected":
            return df_in[df_in["wk_id"].isin(sel)]
        return df_in[~df_in["wk_id"].isin(sel)]

    # ── KPI Summary ──────────────────────────────────────
    st.divider()
    st.subheader("Summary")
    df = _week_filter("kpi", df_all)
    if df.empty:
        st.warning("No campaigns match the filter.")
    else:
        active_df = df[df["handling_min"] > 0].copy()
        k1, k2, k3, k4, k5 = st.columns(5)

        total_campaign_days = len(df)
        k1.metric("Campaign Days", total_campaign_days)

        avg_active_min = active_df["handling_min"].mean() if not active_df.empty else None
        k2.metric(
            "Avg Active Edit Time",
            f"{avg_active_min:.1f} min" if avg_active_min is not None else "—",
            help="Average active editing time per campaign day (5-min idle cap). Only days with tracked time included.",
        )

        median_active_min = active_df["handling_min"].median() if not active_df.empty else None
        k3.metric(
            "Median Active Edit Time",
            f"{median_active_min:.1f} min" if median_active_min is not None else "—",
        )

        total_campaigns = int(df["num_rows"].sum())
        k4.metric("Total Campaigns Built", total_campaigns, help="Each row = one individual campaign (push notification audience segment).")

        total_active_min = df["handling_min"].sum()
        k5.metric(
            "Total Active Edit Time",
            f"{total_active_min:.1f} min",
            help="Sum of per-campaign interaction time (handling_time). 0 for campaign days built before this feature.",
        )

    # ── Weekly Build Time Trend ───────────────────────────
    st.divider()
    st.subheader("Weekly Active Edit Time Trend")
    df = _week_filter("trend", df_all)
    if df.empty:
        st.warning("No campaigns match the filter.")
    else:
        active_df = df[df["handling_min"] > 0].copy()
        if not active_df.empty and "wk_id" in active_df.columns:
            weekly = (
                active_df.groupby("wk_id")
                .agg(
                    avg_min=("handling_min", "mean"),
                    campaigns=("id", "count"),
                )
                .reset_index()
                .sort_values("wk_id")
            )
            weekly["label"] = weekly["wk_id"].apply(
                lambda x: f"Wk{x[-2:]}" if len(x) >= 2 else x
            )
            label_order = weekly["label"].tolist()

            tab_trend, tab_count = st.tabs(["Avg Active Edit Time per Week", "Campaign Days per Week"])
            with tab_trend:
                chart = (
                    alt.Chart(weekly)
                    .mark_bar(color="#579bfc")
                    .encode(
                        x=alt.X("label:N", sort=label_order, title="Week"),
                        y=alt.Y("avg_min:Q", title="Avg Active Edit Time (min)"),
                        tooltip=["label", "avg_min"],
                    )
                    .properties(height=300)
                )
                st.altair_chart(chart, use_container_width=True)
                st.caption("Average active editing time per campaign day, aggregated by calendar week.")
            with tab_count:
                chart = (
                    alt.Chart(weekly)
                    .mark_bar(color="#00c875")
                    .encode(
                        x=alt.X("label:N", sort=label_order, title="Week"),
                        y=alt.Y("campaigns:Q", title="Campaign Days"),
                        tooltip=["label", "campaigns"],
                    )
                    .properties(height=300)
                )
                st.altair_chart(chart, use_container_width=True)
                st.caption("Number of campaign days built per calendar week.")
        else:
            st.info("No active edit data yet — trend data will appear after campaigns are built with time tracking.")

    # ── Campaign Day Timeline ─────────────────────────────
    st.divider()
    st.subheader("Campaign Day Timeline")
    df = _week_filter("timeline", df_all)
    if df.empty:
        st.warning("No campaigns match the filter.")
    else:
        day_df = df[df["send_date"].astype(str).str.len() >= 10].sort_values("send_date").copy()
        if day_df.empty:
            st.info("No campaign days with valid send dates.")
        else:
            day_df["date_label"] = day_df.apply(
                lambda r: (
                    f"Wk{str(r['wk_id'])[-2:]} "
                    f"{_DOW_SHORT.get(r['send_day'], r['send_day'][:3].capitalize() if r['send_day'] else '?')} "
                    f"{r['send_date'][5:].replace('-', '/')}"
                ),
                axis=1,
            )
            dupes = day_df["date_label"].duplicated(keep=False)
            if dupes.any():
                day_df.loc[dupes, "date_label"] = (
                    day_df.loc[dupes, "date_label"]
                    + " #"
                    + (day_df.groupby("date_label").cumcount() + 1).astype(str)
                )
            label_order = day_df["date_label"].tolist()

            tab_bt, tab_camps = st.tabs(["Active Edit Time per Day", "Campaigns per Day"])
            with tab_bt:
                active_df = day_df[day_df["handling_min"] > 0].copy()
                if active_df.empty:
                    st.info("No active edit time recorded yet. Data appears once campaigns are built with row-level time tracking.")
                else:
                    active_labels = active_df["date_label"].tolist()
                    chart = (
                        alt.Chart(active_df)
                        .mark_bar(color="#579bfc")
                        .encode(
                            x=alt.X("date_label:N", sort=active_labels, title="Campaign Day"),
                            y=alt.Y("handling_min:Q", title="Active Edit Time (min)"),
                            tooltip=["date_label", "handling_min"],
                        )
                        .properties(height=350)
                    )
                    st.altair_chart(chart, use_container_width=True)
                    st.caption(
                        "Total active editing time per campaign day (per-row interaction, 5-min idle cap). "
                        "Only days with recorded edit time are shown."
                    )
            with tab_camps:
                chart = (
                    alt.Chart(day_df)
                    .mark_bar(color="#00c875")
                    .encode(
                        x=alt.X("date_label:N", sort=label_order, title="Campaign Day"),
                        y=alt.Y("num_rows:Q", title="Campaigns"),
                        tooltip=["date_label", "num_rows"],
                    )
                    .properties(height=350)
                )
                st.altair_chart(chart, use_container_width=True)
                st.caption("Number of individual campaigns (rows) built per send date, ordered chronologically.")

    # ── Day-of-Week & Row Complexity ──────────────────────
    st.divider()
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Active Edit Time by Day of Week")
        df = _week_filter("dow", df_all)
        active_df = df[df["handling_min"] > 0].copy() if not df.empty else pd.DataFrame()
        if not active_df.empty:
            dow_avg = (
                active_df.groupby("send_day")["handling_min"]
                .agg(["mean", "count"])
                .reindex(_DOW_ORDER)
                .dropna(subset=["mean"])
            )
            dow_avg = dow_avg.reset_index()
            dow_avg["day_short"] = dow_avg["send_day"].map(_DOW_SHORT)
            day_order = [_DOW_SHORT[d] for d in _DOW_ORDER if _DOW_SHORT[d] in dow_avg["day_short"].values]
            chart = (
                alt.Chart(dow_avg)
                .mark_bar(color="#fdab3d")
                .encode(
                    x=alt.X("day_short:N", sort=day_order, title="Send Day"),
                    y=alt.Y("mean:Q", title="Avg Active Edit Time (min)"),
                    tooltip=["day_short", alt.Tooltip("mean:Q", format=".1f"), "count:Q"],
                )
                .properties(height=300)
            )
            st.altair_chart(chart, use_container_width=True)
            st.caption("Average active editing time by send day. Heavier send days may require more prep time.")
        else:
            st.info("No data.")

    with col_right:
        st.subheader("Adhoc vs Recurring Rows")
        df = _week_filter("rowsplit", df_all)
        if not df.empty:
            split_weekly = (
                df.groupby("wk_id")[["form_rows", "sql_rows"]]
                .sum()
                .reset_index()
                .sort_values("wk_id")
            )
            split_weekly["label"] = split_weekly["wk_id"].apply(
                lambda x: f"Wk{x[-2:]}" if len(x) >= 2 else x
            )
            label_order = split_weekly["label"].tolist()
            split_long = split_weekly.melt(
                id_vars=["label"], value_vars=["form_rows", "sql_rows"],
                var_name="type", value_name="count",
            )
            split_long["type"] = split_long["type"].map({"form_rows": "Adhoc", "sql_rows": "Recurring"})
            chart = (
                alt.Chart(split_long)
                .mark_bar()
                .encode(
                    x=alt.X("label:N", sort=label_order, title="Week"),
                    y=alt.Y("count:Q", title="Campaigns"),
                    color=alt.Color("type:N", scale=alt.Scale(
                        domain=["Adhoc", "Recurring"],
                        range=["#579bfc", "#a25ddc"],
                    )),
                    tooltip=["label", "type", "count"],
                )
                .properties(height=300)
            )
            st.altair_chart(chart, use_container_width=True)
            total_form = int(df["form_rows"].sum())
            total_sql = int(df["sql_rows"].sum())
            st.caption(
                f"Total: **{total_form}** adhoc rows · **{total_sql}** recurring rows. "
                "Shows how many campaigns are built from scratch each week vs reused templates."
            )

    # ── Campaign Handling Time Table (All Campaigns, Filterable) ──
    st.divider()
    st.subheader("Campaign Handling Time Table")
    st.caption("Each row = one campaign (row) with its campaign day, name, and handling time. Filter by week or day below.")
    # Build a lookup from campaign id → raw campaign data (for per-row detail)
    _camp_lookup = {c.get("id"): c for c in campaigns}
    all_row_records = []
    for _, day_row in df_all.iterrows():
        cid = day_row["id"]
        send_date = day_row["send_date"]
        send_day = day_row["send_day"]
        wk_id = day_row["wk_id"]
        raw_camp = _camp_lookup.get(cid)
        if not raw_camp:
            continue
        raw_rows = raw_camp.get("rows", [])
        for ri, rr in enumerate(raw_rows):
            ht_hrs = rr.get("handling_time", 0.0)
            ht_min = ht_hrs * 60
            ht_sec = ht_hrs * 3600
            all_row_records.append({
                "Send Date": send_date,
                "Day": _DOW_SHORT.get(send_day, send_day[:3]) if send_day else "—",
                "Wk": f"Wk{wk_id[-2:]}" if len(wk_id) >= 2 else wk_id,
                "_wk_id": wk_id,
                "_day_raw": send_day,
                "#": ri + 1,
                "Campaign Name": rr.get("campaign_name") or "(empty)",
                "Type": "sql" if rr.get("custom_sql") else "form",
                "Edit Time": (
                    f"{ht_min:.1f} min" if ht_min >= 1
                    else f"{ht_sec:.0f} sec" if ht_sec >= 1
                    else "—"
                ),
                "Active Edit (min)": _math.ceil(ht_min / 15) * 15 if ht_min > 0 else 0,
            })
    if not all_row_records:
        st.info("No campaign rows found.")
    else:
        row_df = pd.DataFrame(all_row_records)
        # Filters: week and day (show all when nothing selected)
        filter_cols = st.columns([1, 1])
        week_options = sorted(row_df["Wk"].dropna().unique().tolist())
        day_options = [d for d in _DOW_SHORT.values() if d in row_df["Day"].unique()]
        with filter_cols[0]:
            week_sel = st.multiselect("Week(s)", options=week_options, default=[], key="camp_ht_week", placeholder="All weeks")
        with filter_cols[1]:
            day_sel = st.multiselect("Day(s)", options=day_options, default=[], key="camp_ht_day", placeholder="All days")
        filtered_df = row_df.copy()
        if week_sel:
            filtered_df = filtered_df[filtered_df["Wk"].isin(week_sel)]
        if day_sel:
            filtered_df = filtered_df[filtered_df["Day"].isin(day_sel)]
        # Drop internal columns before display
        display_cols = ["Send Date", "Day", "Wk", "#", "Campaign Name", "Type", "Edit Time", "Active Edit (min)"]
        st.dataframe(
            filtered_df[display_cols].sort_values(["Send Date", "#"]),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Active Edit (min)": st.column_config.NumberColumn(format="%.1f"),
            },
        )
        total_row_min = filtered_df["Active Edit (min)"].sum()
        st.caption(f"Total: {total_row_min:.1f} min across {len(filtered_df)} campaign row(s)")

    # ── Active Editing Time (per-row handling_time) ───────
    if df_all["handling_min"].sum() > 0:
        st.divider()
        st.subheader("Active Edit Time Breakdown")
        df = _week_filter("active", df_all)
        st.caption(
            "Per-row handling time is tracked from when a row expander is active (up to 5-min idle cap). "
            "Only campaigns built after this feature was introduced will have non-zero values."
        )
        ht_df = df[df["handling_min"] > 0].copy() if not df.empty else pd.DataFrame()
        if not ht_df.empty:
            ht_weekly = (
                ht_df.groupby("wk_id")["handling_min"]
                .sum()
                .reset_index()
                .sort_values("wk_id")
            )
            ht_weekly["label"] = ht_weekly["wk_id"].apply(
                lambda x: f"Wk{x[-2:]}" if len(x) >= 2 else x
            )
            label_order = ht_weekly["label"].tolist()
            chart = (
                alt.Chart(ht_weekly)
                .mark_bar(color="#e2445c")
                .encode(
                    x=alt.X("label:N", sort=label_order, title="Week"),
                    y=alt.Y("handling_min:Q", title="Total Active Edit Time (min)"),
                    tooltip=["label", "handling_min"],
                )
                .properties(height=300)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No active edit data in filtered weeks.")

    # ── Full Campaign Build Table ─────────────────────────
    st.divider()
    st.subheader("Campaign Day Build Detail")
    df = _week_filter("table", df_all)
    st.caption("Each row = one campaign day. Click a column header to sort.")

    if df.empty:
        st.warning("No campaign days match the filter.")
    else:
        display_df = pd.DataFrame({
            "Send Date": df["send_date"],
            "Wk ID": df["wk_id"],
            "Day": df["send_day"].apply(lambda d: _DOW_SHORT.get(d.upper(), d.capitalize()[:3]) if d else "—"),
            "Campaigns": df["num_rows"].astype(int),
            "Wall-Clock (min)": df["elapsed_to_submit_min"],
            "Active Edit (hrs)": df["handling_hrs"],
            "Active Edit (min)": df["handling_min"],
            "Sessions": df["open_count"].astype(int),
            "Saves": df["save_count"].astype(int),
            "Edits": df["audit_changes"].astype(int),
            "Status": df["status"],
        })

        st.dataframe(
            display_df.sort_values("Send Date", ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Wall-Clock (min)": st.column_config.NumberColumn(format="%.1f", help="Created → Submitted (includes idle time)"),
                "Active Edit (hrs)": st.column_config.NumberColumn(format="%.3f"),
                "Active Edit (min)": st.column_config.NumberColumn(format="%.1f"),
                "Status": st.column_config.TextColumn(),
            },
        )

        # ── Export for Business Case ──────────────────────────
        st.divider()
        csv_bytes = display_df.sort_values("Send Date", ascending=False).to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 Export Analytics to CSV",
            data=csv_bytes,
            file_name="PACE_build_analytics.csv",
            mime="text/csv",
            help="UTF-8 with BOM — opens correctly in Excel",
        )

    # ── Business Case Insights ────────────────────────────
    st.divider()
    st.subheader("Business Case Snapshot")
    df = _week_filter("bcase", df_all)
    if not df.empty:
        active_df = df[df["handling_min"] > 0].copy()
        avg_campaigns_per_day = df["num_rows"].mean()
        n_with_tracking = len(active_df)
        total_campaigns_built = int(df["num_rows"].sum())
        total_active_hr = df["handling_min"].sum() / 60
        avg_active_min = active_df["handling_min"].mean() if not active_df.empty else 0
        median_active_min = active_df["handling_min"].median() if not active_df.empty else 0
        campaigns_per_week = total_campaigns_built / max(1, df["wk_id"].nunique())
        with st.container(border=True):
            st.markdown(f"""
| Metric | Value |
|--------|-------|
| Campaign days with tracked time | **{n_with_tracking}** |
| Total campaigns built | **{total_campaigns_built}** |
| Total active editing time | **{total_active_hr:.1f} hrs** |
| Avg active edit time per campaign day | **{avg_active_min:.1f} min** |
| Median active edit time per campaign day | **{median_active_min:.1f} min** |
| Avg campaigns per campaign day | **{avg_campaigns_per_day:.1f}** |
| Campaigns built per week (avg) | **{campaigns_per_week:.1f}** |
            """)
        st.caption(
            "Use these figures in your business case to quantify time invested in campaign builds "
            "and to project efficiency gains from tooling improvements."
        )

        # ── Glossary & Computation Notes ──────────────────────
        with st.expander("📖 Glossary & How These Numbers Are Computed"):
            st.markdown("""
**Terminology:**

| Term | Definition |
|------|------------|
| **Campaign Day** | A single send day (Monday through Sunday). One campaign day can contain multiple campaigns. Represented as one file in the system. |
| **Campaign** | An individual push notification audience segment — each row within a campaign day. One campaign day typically has multiple campaigns. |
| **Adhoc Campaign** | A campaign built from scratch using the form editor (custom audience, messaging, targeting). |
| **Recurring Campaign** | A campaign injected from the SQL template library — a pre-built query reused weekly with minimal edits. |
| **Active Editing Time** | The primary time metric. Counts only seconds a user is actively interacting with campaign row forms. A 5-minute idle cap prevents inflated numbers. Per-row values are raw (actual time). The **campaign day total** is rounded up to the nearest 15-minute increment (0.25 hrs); totals under 10 min round to 15 min. Campaign days built before this feature show 0. |
| **Wall-Clock Build Time** | Reference only. Time from campaign day Created until first Submitted for Export — includes meetings, waiting for assets, and idle time. Shown in the Build Detail table as "Wall-Clock (min)". |

---

**Metric Computations:**

| Metric | How It's Computed |
|--------|-------------------|
| **Campaign days with tracked time** | Count of campaign days where at least one row has recorded active editing time. |
| **Total campaigns built** | Sum of all individual campaigns (rows) across all campaign days. |
| **Total active editing time** | Sum of per-campaign-day totals. Each campaign day's raw row sum is rounded up to the nearest 15 min (0.25 hrs) before contributing to the grand total. Per-row values remain raw. |
| **Avg active edit time per campaign day** | Total active editing time ÷ number of campaign days with tracked time. |
| **Median active edit time per campaign day** | Middle value of active edit times — less sensitive to outliers. |
| **Avg campaigns per campaign day** | Total campaigns ÷ total campaign days. Indicates typical complexity. |
| **Campaigns built per week (avg)** | Total campaigns built ÷ number of distinct calendar weeks. Shows weekly throughput. |
| **Wall-Clock (min) in detail table** | Created → first Submitted timestamp difference. Includes all idle time. Shown for reference only. |
            """)
    else:
        st.info("No campaign days in the selected weeks.")
