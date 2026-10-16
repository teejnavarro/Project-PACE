"""Unit coverage for PUSH targeting, offer JOIN, and custom JOIN SQL assembly."""
import pytest

import storage
from compose import (
    _build_custom_joins,
    _build_or_group_sql,
    _div_banner_or_clause,
    _format_offer_ids,
    _inject_notes_after_from,
    _sanitize_banner_names,
    _sanitize_numeric_ids,
    _targeting_conditions,
    _targeting_notes_comment,
    build_offer_join,
    build_targeting_clause,
    build_where_clause,
)

TABLES = {
    "coupon_store_validity": "proj.ds.coupon_store_validity",
    "offer_allocation_history": "proj.ds.OFFER_ALLOCATION_HISTORY",
}


@pytest.fixture(autouse=True)
def _push_channel():
    storage.set_active_channel("push")


# ── Sanitisation ───────────────────────────────────────────────

def test_numeric_ids_drop_non_numeric_tokens():
    assert _sanitize_numeric_ids("29, 33,abc, 1;DROP TABLE x,") == ["29", "33"]


def test_banner_names_lowercased_escaped_and_filtered():
    assert _sanitize_banner_names("Pine_And_Peak, O'Shea ,bad;drop, back\\slash") == ["pine_and_peak", "o''shea"]


# ── Flat targeting ─────────────────────────────────────────────

@pytest.mark.parametrize("mode, expected", [
    ("IN", "a.division_id = 29"),
    ("NOT IN", "a.division_id != 29"),
])
def test_single_division(mode, expected):
    assert _targeting_conditions({"division_ids": "29", "division_mode": mode}) == [expected]


def test_multi_division_not_in():
    row = {"division_ids": "29,33", "division_mode": "NOT IN"}
    assert _targeting_conditions(row) == ["a.division_id NOT IN (29,33)"]


def test_invalid_mode_falls_back_to_in():
    row = {"store_ids": "1,2", "store_mode": "LIKE"}
    assert _targeting_conditions(row) == ["a.store_id IN (1,2)"]


def test_banners_always_lowercase():
    row = {"banners": "Pine_And_Peak,BLUEHARBOR", "banner_mode": "IN"}
    assert _targeting_conditions(row) == ["a.store_banner IN ('pine_and_peak','blueharbor')"]


def test_all_non_numeric_ids_produce_no_clause():
    assert _targeting_conditions({"division_ids": "abc", "store_ids": "x,y"}) == []


def test_build_targeting_clause_joins_with_and():
    row = {"division_ids": "29", "banners": "pine_and_peak", "store_ids": "100,200"}
    assert build_targeting_clause(row) == (
        "WHERE a.division_id = 29\n"
        "  AND a.store_banner = 'pine_and_peak'\n"
        "  AND a.store_id IN (100,200)"
    )


def test_build_targeting_clause_empty():
    assert build_targeting_clause({}) == ""


# ── OR groups ─────────────────────────────────────────────────

def test_or_group_single_values_use_equality_operators():
    g = {"division_ids": "29", "div_mode": "NOT IN", "banners": "blueharbor", "banner_mode": "IN", "store_ids": "5", "store_mode": "NOT IN"}
    assert _build_or_group_sql(g) == "a.division_id != 29 AND a.store_banner = 'blueharbor' AND a.store_id != 5"


def test_or_group_empty():
    assert _build_or_group_sql({}) == ""


def test_or_clause_single_group_wrapped_once():
    row = {"div_banner_groups": [{"division_ids": "29", "banners": "cedar_market,blueharbor"}]}
    assert _div_banner_or_clause(row) == "(a.division_id = 29 AND a.store_banner IN ('cedar_market','blueharbor'))"


def test_or_clause_multiple_groups_each_parenthesised():
    row = {"div_banner_groups": [
        {"division_ids": "29", "banners": "cedar_market"},
        {"division_ids": "33", "banners": "redwood_fresh,meadowlane"},
        {},
    ]}
    assert _div_banner_or_clause(row) == (
        "((a.division_id = 29 AND a.store_banner = 'cedar_market')\n"
        "  OR (a.division_id = 33 AND a.store_banner IN ('redwood_fresh','meadowlane')))"
    )


def test_or_clause_appended_after_flat_targeting():
    row = {"store_ids": "1", "div_banner_groups": [{"division_ids": "29"}, {"division_ids": "33"}]}
    assert _targeting_conditions(row) == [
        "a.store_id = 1",
        "((a.division_id = 29)\n  OR (a.division_id = 33))",
    ]


# ── Offer JOIN / WHERE ────────────────────────────────────────

def test_format_offer_ids():
    assert _format_offer_ids("") == "= ''"
    assert _format_offer_ids("123-D") == "= '123-D'"
    assert _format_offer_ids("1-D, 2-D") == "IN ('1-D','2-D')"
    assert _format_offer_ids("O'Neil") == "= 'O''Neil'"


@pytest.mark.parametrize("offer_type", ["", "PUSHSECTION", "UNKNOWN"])
def test_offer_join_empty_for_non_join_types(offer_type):
    assert build_offer_join({"offer_type": offer_type, "offer_id": "1-D"}, TABLES) == ""


def test_store_coupon_join():
    sql = build_offer_join({"offer_type": "store coupon", "offer_id": "1-D,2-D"}, TABLES)
    assert "FROM proj.ds.coupon_store_validity" in sql
    assert "AND offer_id IN ('1-D','2-D')" in sql
    assert ") AS b" in sql


def test_personalized_deal_join():
    sql = build_offer_join({"offer_type": "PERSONALIZED DEAL", "offer_id": "9-D"}, TABLES)
    assert "FROM proj.ds.OFFER_ALLOCATION_HISTORY a" in sql
    assert "a.client_offer_id = '9-D'" in sql
    assert ") AS bb" in sql and ") AS cc" in sql


def test_where_clause_combines_offer_condition_and_targeting():
    row = {"offer_type": "STORE COUPON", "offer_id": "1-D", "division_ids": "29"}
    assert build_where_clause(row) == (
        "WHERE cast(a.store_id as string) = b.store_id\n"
        "  AND a.division_id = 29"
    )


def test_where_clause_empty_for_pushsection_without_targeting():
    assert build_where_clause({"offer_type": "PUSHSECTION"}) == ""


# ── Custom JOINs ──────────────────────────────────────────────

def test_structured_and_freetext_custom_joins():
    row = {"custom_joins": [
        {"mode": "structured", "join_type": "left join", "table_path": "p.d.t", "alias": "x", "on_clause": "a.id = x.id"},
        {"mode": "freetext", "raw_sql": "CROSS JOIN p.d.u y"},
        {"mode": "structured", "table_path": ""},
        {"mode": "freetext", "raw_sql": "   "},
    ]}
    assert _build_custom_joins(row) == "LEFT JOIN p.d.t x\n  ON a.id = x.id\nCROSS JOIN p.d.u y"


def test_custom_join_alias_collision_warns():
    row = {"offer_type": "STORE COUPON", "custom_joins": [
        {"table_path": "p.d.t", "alias": "b", "on_clause": "1=1"},
    ]}
    out = _build_custom_joins(row)
    assert out.startswith("-- ⚠️ WARNING: alias 'b' conflicts")
    assert "JOIN p.d.t b" in out


def test_custom_join_base_alias_a_always_reserved():
    out = _build_custom_joins({"custom_joins": [{"table_path": "p.d.t", "alias": "A"}]})
    assert "WARNING" in out


# ── Targeting notes ───────────────────────────────────────────

def test_targeting_notes_comment():
    assert _targeting_notes_comment({"targeting_notes": "  "}) == ""
    assert _targeting_notes_comment({"targeting_notes": "line1\nline2"}) == (
        "/*\n   Custom Targeting Instructions:\n   line1\n   line2\n*/\n"
    )


def test_notes_injected_after_from_line():
    sql = "SELECT 1\nFROM proj.ds.Eligible_Push_Audience a\nWHERE x"
    out = _inject_notes_after_from(sql, "/* n */\n")
    assert out == "SELECT 1\nFROM proj.ds.Eligible_Push_Audience a\n/* n */\n\nWHERE x"


def test_notes_prepended_when_no_from_line():
    assert _inject_notes_after_from("SELECT 1", "/* n */\n") == "/* n */\nSELECT 1"
    assert _inject_notes_after_from("SELECT 1", "") == "SELECT 1"
