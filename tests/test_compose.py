# tests/test_compose.py
"""Snapshot-style test: render a known set of campaigns and verify output."""

import sys
from pathlib import Path

# Ensure app/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from renderer import create_jinja_env
from compose import build_sql

TABLES = {
    "push_allocation": "orchard-demo.messaging.push_allocation",
    "push_priority": "orchard-demo.messaging.push_priority",
    "push_priority_full": "orchard-demo.messaging.push_priority_full",
    "push_allocation_final": "orchard-demo.messaging.push_allocation_final",
    "push_allocation_final_archive": "orchard-demo.messaging.push_allocation_archive",
    "eligible_push_audience": "orchard-demo.audience.eligible_push_audience",
    "redemption_events": "orchard-demo.customer.redemption_events",
    "offer_allocation_history": "orchard-demo.offers.offer_allocation_history",
    "coupon_store_validity": "orchard-demo.offers.coupon_eligibility",
    "offer_catalog": "orchard-demo.offers.offer_catalog",
    "consolidated_offer_bank": "orchard-demo.offers.consolidated_offer_bank",
}

SAMPLE_ROWS = [
    {
        "campaign_name": "[Offer] Orchard Rewards Monthly Reminder",
        "theme": "orchard-rewards_monthly-reminder-pn_wk07_2026_Sun",
        "title": "Don't Forget! \U0001f388",
        "message": "A fresh offer is waiting for you. \U0001f381 Take a look this month!",
        "media_url": "https://cdn.example.com/push/sample-image.jpg",
        "pushsection": "",
        "param_q": "",
        "screentitle": "",
        "subtitle": "",
        "gameid": "",
        "product": "",
        "searchterm": "",
        "store": "",
        "seller": "",
        "category": "",
        "program": "",
        "pagname": "",
        "datasource": "",
        "modelconfigid": "",
        "partnerid": "",
        "autoimage": "",
        "priority": 1,
    },
    {
        "campaign_name": "[PD] FY26_Loyalty_Monthly Birthday Reminder | Push 2 2X Points",
        "theme": "loy-bday-crm_2x-points-t2-reminder-pn_wk07_2026_Sun",
        "title": "Don't Forget! \U0001f388",
        "message": "We have a birthday gift waiting for you to use all month long. \U0001f381",
        "media_url": "https://cdn.example.com/push/sample-image.jpg",
        "pushsection": "",
        "param_q": "",
        "screentitle": "",
        "subtitle": "",
        "gameid": "",
        "product": "",
        "searchterm": "",
        "store": "",
        "seller": "",
        "category": "",
        "program": "",
        "pagname": "",
        "datasource": "",
        "modelconfigid": "",
        "partnerid": "",
        "autoimage": "",
        "priority": 2,
    },
]


def test_build_sql_contains_all_sections():
    env = create_jinja_env()
    sql = build_sql(env, TABLES, SAMPLE_ROWS, wk_id="202607", send_date="2026-02-15")

    # Preamble markers
    assert "DECLARE wk_id BIGNUMERIC" in sql
    assert "SET wk_id = 202607" in sql
    assert "FROM orchard-demo.audience.eligible_push_audience" in sql

    # Campaign comment headers
    assert "[Offer] Orchard Rewards Monthly Reminder" in sql
    assert "[PD] FY26_Loyalty_Monthly Birthday Reminder | Push 2 2X Points" in sql

    # Campaign inserts (check themes appear)
    assert "orchard-rewards_monthly-reminder-pn_wk07_2026_Sun" in sql
    assert "loy-bday-crm_2x-points-t2-reminder-pn_wk07_2026_Sun" in sql

    # Dedup pattern
    assert "WHERE HHID NOT IN" in sql
    assert "GROUP BY all" in sql

    # Priority block
    assert "INSERT INTO orchard-demo.messaging.push_priority" in sql
    assert "(1, 'orchard-rewards_monthly-reminder-pn_wk07_2026_Sun')" in sql
    assert "(2, 'loy-bday-crm_2x-points-t2-reminder-pn_wk07_2026_Sun')" in sql

    # Finalization — redemption DELETE + push_allocation_final
    assert "FROM orchard-demo.customer.redemption_events" in sql
    assert "orchard-demo.messaging.push_allocation_final" in sql
    assert "AUTOIMAGE" in sql

    # autoimage rendered as NULL
    assert "CAST(NULL as BOOL) as autoimage" in sql


def test_priority_order_matches_row_order():
    env = create_jinja_env()
    # Reverse the rows and renumber priorities (mirrors the UI's "Sort by priority" step).
    reversed_rows = [dict(r) for r in reversed(SAMPLE_ROWS)]
    for i, r in enumerate(reversed_rows, start=1):
        r["priority"] = i
    sql = build_sql(env, TABLES, reversed_rows, wk_id="202607", send_date="2026-02-15")
    assert "(1, 'loy-bday-crm_2x-points-t2-reminder-pn_wk07_2026_Sun')" in sql
    assert "(2, 'orchard-rewards_monthly-reminder-pn_wk07_2026_Sun')" in sql


def test_no_legacy_space_concat():
    """Themes should appear as plain string literals — no CONCAT wrapper."""
    env = create_jinja_env()
    sql = build_sql(env, TABLES, SAMPLE_ROWS, wk_id="202607", send_date="2026-02-15")
    # Themes must NOT be wrapped in CONCAT(..., ' ') — legacy space feature is removed
    assert "CONCAT('orchard-rewards_monthly-reminder-pn_wk07_2026_Sun', ' ')" not in sql
    assert "CONCAT('loy-bday-crm_2x-points-t2-reminder-pn_wk07_2026_Sun', ' ')" not in sql
