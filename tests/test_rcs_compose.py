# tests/test_rcs_compose.py
"""Coverage for RCS-specific SQL generation helpers and end-to-end build."""

import sys
from pathlib import Path

import pytest

# Ensure app/ is importable
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "app"))

from renderer import create_jinja_env  # noqa: E402
from compose import (  # noqa: E402
    _rcs_expand_banner_in_url,
    _rcs_sso_url_sql,
    _rcs_targeting_conditions,
    _rcs_div_banner_or_clause,
    _rcs_build_custom_joins,
    _normalize_rcs_row,
    build_rcs_sql,
    _RCS_STORE_BANNER_EXPR,
    _RCS_SSO_URL_SQL,
)

RCS_MACROS = _ROOT / "rcs" / "macros"

RCS_TABLES_CFG = {
    "tables": {
        "rcs_adhoc_base": "orchard-demo.messaging",
        "rcs_adhoc_suffix": "_RCS_Adhoc",
        "sms_population": "orchard-demo.audience.eligible_message_audience",
        "outbound_message_log": "orchard-demo.messaging.outbound_message_log",
        "rcs_archive": "orchard-demo.messaging.rcs_message_archive",
        "send_day_blocker": "orchard-demo.audience.message_send_restrictions",
        "email_versions": "orchard-demo.customer.email_versions",
        "customer_preference_opt_choice": "orchard-demo.customer.messaging_preferences",
        "text_count_approval": "orchard-demo.messaging.message_count_approvals",
    },
    "runtime": {
        "goo_preference_definition_id": "72b69367-0b3c-4f90-b373-b544024c7109",
    },
}


# ─────────────────────────────────────────────────────────
# [BANNER] placeholder expansion
# ─────────────────────────────────────────────────────────

def test_expand_banner_empty():
    assert _rcs_expand_banner_in_url("") == "''"
    assert _rcs_expand_banner_in_url(None) == "''"


def test_expand_banner_no_placeholder():
    assert _rcs_expand_banner_in_url("https://example.com/x") == "'https://example.com/x'"


def test_expand_banner_apostrophe_escaped():
    # No [BANNER] but apostrophe must be escaped for the SQL literal.
    assert _rcs_expand_banner_in_url("O'Brien") == "'O\\'Brien'"


def test_expand_banner_single_placeholder():
    result = _rcs_expand_banner_in_url("https://[BANNER].com/x")
    assert result == f"'https://' ||{_RCS_STORE_BANNER_EXPR} ||'.com/x'"


def test_expand_banner_case_insensitive():
    # [banner] and [Banner] must both be recognised.
    for token in ("[banner]", "[Banner]", "[BANNER]", "[BaNnEr]"):
        r = _rcs_expand_banner_in_url(f"x{token}y")
        assert _RCS_STORE_BANNER_EXPR in r
        assert r.startswith("'x'")
        assert r.endswith("'y'")


def test_expand_banner_multiple_placeholders():
    r = _rcs_expand_banner_in_url("a[BANNER]b[BANNER]c")
    # Three literal segments and two banner expressions.
    assert r.count(_RCS_STORE_BANNER_EXPR) == 2
    assert r.startswith("'a'") and r.endswith("'c'")


def test_expand_banner_dotcom_shorthand():
    # Tail-only input starting with '.com' auto-prepends the standard boilerplate.
    r = _rcs_expand_banner_in_url(".com/shop/product-details.960109101.html")
    assert r == (
        f"'https://www.' ||{_RCS_STORE_BANNER_EXPR} "
        "||'.com/shop/product-details.960109101.html'"
    )


def test_expand_banner_dotcom_case_insensitive():
    # '.COM', '.Com', etc. all recognised.
    for prefix in (".com", ".COM", ".Com", ".cOm"):
        r = _rcs_expand_banner_in_url(f"{prefix}/weeklyad")
        assert _RCS_STORE_BANNER_EXPR in r
        assert r.startswith("'https://www.' ||")
        assert r.endswith("/weeklyad'")


def test_expand_banner_dotcom_leading_whitespace_stripped():
    # Users may paste with a stray leading space — strip it before matching.
    r = _rcs_expand_banner_in_url("   .com/weeklyad")
    assert r.startswith("'https://www.' ||")
    assert r.endswith("/weeklyad'")


def test_expand_banner_dotcom_requires_boundary():
    # '.compact' must NOT be treated as the '.com' shorthand — it doesn't start a URL tail.
    r = _rcs_expand_banner_in_url(".compact-thing")
    assert r == "'.compact-thing'"


def test_expand_banner_dotcom_bare():
    # Just '.com' by itself is still a valid tail.
    r = _rcs_expand_banner_in_url(".com")
    assert r == f"'https://www.' ||{_RCS_STORE_BANNER_EXPR} ||'.com'"


# ─────────────────────────────────────────────────────────
# SSO URL yes/no flag
# ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("flag", ["yes", "Yes", "YES", "y", "true", "1"])
def test_sso_url_yes_variants(flag):
    assert _rcs_sso_url_sql(flag) == _RCS_SSO_URL_SQL


@pytest.mark.parametrize("flag", ["", "no", "No", "false", None, "0", "  "])
def test_sso_url_no_variants(flag):
    assert _rcs_sso_url_sql(flag) == "''"


# ─────────────────────────────────────────────────────────
# Targeting conditions (all use `s.` alias for SMS_Population)
# ─────────────────────────────────────────────────────────

def test_targeting_uses_s_alias_for_single_division():
    clauses = _rcs_targeting_conditions({"division_ids": "29"})
    assert clauses == ["s.division_id = 29"]


def test_targeting_multi_division_uses_in():
    clauses = _rcs_targeting_conditions({"division_ids": "29,33,45"})
    assert clauses == ["s.division_id IN (29,33,45)"]


def test_targeting_division_not_in():
    clauses = _rcs_targeting_conditions(
        {"division_ids": "29,33", "division_mode": "NOT IN"}
    )
    assert clauses == ["s.division_id NOT IN (29,33)"]


def test_targeting_single_banner_uses_equality():
    clauses = _rcs_targeting_conditions({"banners": "pine_and_peak"})
    assert clauses == ["s.store_banner = 'pine_and_peak'"]


def test_targeting_stores_and_banners_combined():
    clauses = _rcs_targeting_conditions(
        {"store_ids": "1234,5678", "banners": "pine_and_peak,blueharbor"}
    )
    assert "s.store_banner IN ('pine_and_peak','blueharbor')" in clauses
    assert "s.store_id IN (1234,5678)" in clauses


def test_targeting_empty_row_yields_no_clauses():
    assert _rcs_targeting_conditions({}) == []


# ─────────────────────────────────────────────────────────
# OR groups — each group wrapped in its own parens, compound uses outer parens
# ─────────────────────────────────────────────────────────

def test_or_group_single_group_single_paren():
    row = {
        "div_banner_groups": [
            {"division_ids": "29", "banners": "pine_and_peak,blueharbor", "div_mode": "IN", "banner_mode": "IN"}
        ]
    }
    clause = _rcs_div_banner_or_clause(row)
    assert clause == "(s.division_id = 29 AND s.store_banner IN ('pine_and_peak','blueharbor'))"


def test_or_group_multiple_groups_outer_and_inner_parens():
    row = {
        "div_banner_groups": [
            {"division_ids": "29", "banners": "pine_and_peak"},
            {"division_ids": "33", "banners": "blueharbor"},
        ]
    }
    clause = _rcs_div_banner_or_clause(row)
    assert clause.startswith("(") and clause.endswith(")")
    assert " OR " in clause
    assert "(s.division_id = 29 AND s.store_banner = 'pine_and_peak')" in clause
    assert "(s.division_id = 33 AND s.store_banner = 'blueharbor')" in clause


def test_or_group_included_in_targeting_conditions():
    row = {
        "division_ids": "29",
        "div_banner_groups": [
            {"division_ids": "33", "banners": "blueharbor"},
        ],
    }
    clauses = _rcs_targeting_conditions(row)
    # Flat targeting and OR group both present as independent AND-joined clauses.
    assert "s.division_id = 29" in clauses
    assert any("OR" not in c and "s.division_id = 33" in c for c in clauses)


def test_or_group_empty_dict_is_dropped():
    row = {"div_banner_groups": [{}, {"division_ids": "29"}]}
    clause = _rcs_div_banner_or_clause(row)
    # Only the non-empty group survives → single-group form (no outer OR wrapping).
    assert clause == "(s.division_id = 29)"


# ─────────────────────────────────────────────────────────
# Custom JOINs
# ─────────────────────────────────────────────────────────

def test_custom_joins_structured():
    row = {
        "custom_joins": [
            {"mode": "structured", "join_type": "LEFT JOIN",
             "table_path": "proj.ds.tbl", "alias": "t", "on_clause": "t.id = s.id"}
        ]
    }
    sql = _rcs_build_custom_joins(row)
    assert sql == "LEFT JOIN proj.ds.tbl t\n  ON t.id = s.id"


def test_custom_joins_freetext_pass_through():
    row = {"custom_joins": [{"mode": "freetext", "raw_sql": "JOIN foo f ON f.x = s.x"}]}
    assert _rcs_build_custom_joins(row) == "JOIN foo f ON f.x = s.x"


def test_custom_joins_reserved_alias_warning():
    row = {
        "custom_joins": [
            {"mode": "structured", "join_type": "JOIN", "table_path": "proj.ds.tbl",
             "alias": "s", "on_clause": "s.id = s.id"}
        ]
    }
    sql = _rcs_build_custom_joins(row)
    assert "WARNING" in sql
    assert "'s'" in sql


def test_custom_joins_empty_row():
    assert _rcs_build_custom_joins({}) == ""


# ─────────────────────────────────────────────────────────
# Row normalization — pads structures + precomputes SQL fragments
# ─────────────────────────────────────────────────────────

def test_normalize_pads_cards_to_seven():
    norm = _normalize_rcs_row({"cards": [{"body": "hello"}]})
    assert len(norm["cards"]) == 7
    assert norm["cards"][0]["body"] == "hello"
    assert norm["cards"][6]["body"] == ""


def test_normalize_pads_buttons_to_four_and_general_buttons_to_three():
    norm = _normalize_rcs_row({"cards": [{"buttons": [{"title": "A"}]}]})
    assert len(norm["cards"][0]["buttons"]) == 4
    assert norm["cards"][0]["buttons"][0]["title"] == "A"
    assert len(norm["general_buttons"]) == 3


def test_normalize_precomputes_sql_value_and_sso_url():
    norm = _normalize_rcs_row({
        "cards": [{"buttons": [{"value": "https://[BANNER].com/x", "sso_url": "yes"}]}],
    })
    b = norm["cards"][0]["buttons"][0]
    assert _RCS_STORE_BANNER_EXPR in b["_sql_value"]
    assert b["_sql_sso_url"] == _RCS_SSO_URL_SQL


def test_normalize_captures_targeting_where_and_notes_comment():
    norm = _normalize_rcs_row({
        "division_ids": "29",
        "targeting_notes": "Exclude test stores",
    })
    assert norm["targeting_where"] == "s.division_id = 29"
    # Notes are emitted as a /* … */ comment block.
    assert "Exclude test stores" in norm["targeting_notes_comment"]
    assert norm["targeting_notes_comment"].strip().startswith("/*")


def test_normalize_does_not_mutate_input():
    original = {"cards": [{"body": "x"}]}
    snapshot = repr(original)
    _normalize_rcs_row(original)
    assert repr(original) == snapshot


# ─────────────────────────────────────────────────────────
# End-to-end build_rcs_sql — offer type dispatch + comments preserved
# ─────────────────────────────────────────────────────────

def _minimal_row(offer_type: str, **overrides):
    row = {
        "campaign_name": f"[RCS] Test {offer_type}",
        "channelsubtype": offer_type,
        "theme": f"rcs-test-{offer_type.lower()}",
        "priority": 1,
        # Fields from rcs/config/optional_columns.yaml — must be present because
        # the RCS templates use StrictUndefined and reference these directly.
        "bu_cc_id": "test-cc_",
        "fallback_message_body": "",
        "to_app_store": False,
        "canonical_campaign_id": "",
        # CAROUSEL-only: fixed card count (2-7).
        "carousel_card_count": 3,
        "cards": [
            {
                "body": "Hello!",
                "media_title": "Media",
                "media_url": "https://example.com/img.png",
                "buttons": [{"title": "Open", "value": "https://[BANNER].com/x",
                             "sso_url": "yes", "push_section": "landing"}],
            }
        ],
    }
    row.update(overrides)
    return row


@pytest.fixture(scope="module")
def rcs_env():
    return create_jinja_env(RCS_MACROS)


@pytest.mark.parametrize("offer_type", ["CHOICE", "CARD", "CAROUSEL"])
def test_build_rcs_sql_offer_type_dispatch(rcs_env, offer_type):
    sql = build_rcs_sql(
        rcs_env, RCS_TABLES_CFG, [_minimal_row(offer_type)],
        wk_id="202633", send_date="2026-08-31",  # Monday
    )
    assert "outbound_message_log" in sql
    assert "MON_RCS_Adhoc" in sql  # 2026-08-31 is a Monday
    # Every offer type stamps its own channelsubtype into the SET block.
    assert f"set channelsubtype = '{offer_type}'" in sql
    if offer_type == "CAROUSEL":
        # CAROUSEL bakes the card count into a literal template name.
        assert "RCS_CAROUSEL_3_CARDS_THEME" in sql
    else:
        # CHOICE and CARD build the template name via SQL concatenation.
        assert "'RCS_'||channelsubtype||'_THEME'" in sql


def test_build_rcs_sql_unknown_offer_type_raises(rcs_env):
    with pytest.raises(RuntimeError, match="Unknown or missing RCS offer_type"):
        build_rcs_sql(
            rcs_env, RCS_TABLES_CFG, [_minimal_row("BOGUS")],
            wk_id="202633", send_date="2026-08-31",
        )


def test_build_rcs_sql_falls_back_to_legacy_offer_type_key(rcs_env):
    # Rows saved before the channelsubtype rename used offer_type.
    row = _minimal_row("CHOICE")
    row.pop("channelsubtype")
    row["offer_type"] = "CHOICE"
    sql = build_rcs_sql(rcs_env, RCS_TABLES_CFG, [row], wk_id="202633", send_date="2026-08-31")
    assert "set channelsubtype = 'CHOICE'" in sql


def test_build_rcs_sql_preserves_production_comments(rcs_env):
    sql = build_rcs_sql(
        rcs_env, RCS_TABLES_CFG, [_minimal_row("CHOICE")],
        wk_id="202633", send_date="2026-08-31",
    )
    # A representative sample of the do-not-change contract comments.
    for marker in (
        "-- NEVER change the CMPID case statement on the row below",
        "--never change this",
        "--NEVER CHANGE THIS CASE STATEMENT",
        "--include the [BANNER] placeholder even if the CRF doesn't include it",
    ):
        assert marker in sql, f"Missing production comment: {marker!r}"


def test_build_rcs_sql_banner_expansion_reaches_output(rcs_env):
    sql = build_rcs_sql(
        rcs_env, RCS_TABLES_CFG, [_minimal_row("CHOICE")],
        wk_id="202633", send_date="2026-08-31",
    )
    # The store_banner REPLACE expression must be present because the button
    # value contained a [BANNER] placeholder.
    assert _RCS_STORE_BANNER_EXPR in sql


def test_build_rcs_sql_targeting_notes_comment_emitted(rcs_env):
    row = _minimal_row("CHOICE", targeting_notes="Exclude wave 2 stores")
    sql = build_rcs_sql(rcs_env, RCS_TABLES_CFG, [row], wk_id="202633", send_date="2026-08-31")
    assert "Exclude wave 2 stores" in sql
    assert "Custom Targeting Instructions" in sql


def test_build_rcs_sql_send_day_prefix_matches_weekday(rcs_env):
    # 2026-08-30 is a Sunday → SUN_RCS_Adhoc.
    sql = build_rcs_sql(
        rcs_env, RCS_TABLES_CFG, [_minimal_row("CHOICE")],
        wk_id="202633", send_date="2026-08-30",
    )
    assert "SUN_RCS_Adhoc" in sql
    assert "MON_RCS_Adhoc" not in sql
