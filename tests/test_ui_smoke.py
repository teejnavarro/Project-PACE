"""Smoke tests: every view renders without raising, against a throwaway data folder."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import storage

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")

FORM_ROW = {
    "_row_id": "r1", "priority": 1, "row_type": "form",
    "campaign_name": "Smoke Row", "theme": "smoke_theme_2026-10-05",
    "title": "Hello", "message": "World's best deal", "offer_type": "STORE COUPON", "offer_id": "123-D",
    "division_ids": "29", "division_mode": "IN", "banners": "pine_and_peak", "banner_mode": "IN",
    "store_ids": "", "store_mode": "IN", "div_banner_groups": [], "custom_joins": [],
    "targeting_notes": "note", "custom_sql": "", "multi_theme": False, "sub_rows": [], "handling_time": 0.0,
}
MULTI_ROW = {
    "_row_id": "r2", "priority": 2, "row_type": "form", "campaign_name": "Multi",
    "multi_theme": True, "custom_sql": "", "handling_time": 0.0, "div_banner_groups": [], "custom_joins": [],
    "sub_rows": [
        {**FORM_ROW, "_row_id": "s1", "theme": "multi_a_2026-10-05"},
        {**FORM_ROW, "_row_id": "s2", "theme": "multi_b_2026-10-05", "offer_type": "PUSHSECTION", "pushsection": "x"},
    ],
}


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_data_dir", lambda: tmp_path)
    c = storage.create_campaign(wk_id="202640", send_date="2026-10-05", send_day="MONDAY")
    c["rows"] = [FORM_ROW, MULTI_ROW]
    storage.save_campaign(c)
    return c


def _run(view, *, role="user", campaign_id=None):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["view"] = view
    at.session_state["role"] = role
    at.session_state["dev_unlocked"] = role == "developer"
    if campaign_id:
        at.session_state["active_campaign_id"] = campaign_id
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


@pytest.mark.parametrize("role", ["user", "developer"])
def test_dashboard(campaign, role):
    _run("dashboard", role=role)


@pytest.mark.parametrize("role", ["user", "developer"])
def test_detail(campaign, role):
    at = _run("detail", role=role, campaign_id=campaign["id"])
    assert at.session_state["campaign_status"] == "Draft"


def test_analytics(campaign):
    _run("analytics", role="developer")


def test_crf_converter(campaign):
    _run("crf_converter")


@pytest.mark.parametrize("seed", ["1", "2", "3"])
def test_division_order_preserved_across_hash_seeds(seed, tmp_path):
    import subprocess
    import sys

    code = (
        "from ui import _division_ids_to_display as f, _load_division_options as o;"
        "print(','.join(d.split(' - ')[0] for d in f('32,05,20,28,27,29,33,19,17', o())))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True,
        cwd=Path(APP).parent, env={**__import__("os").environ, "PYTHONHASHSEED": seed},
    ).stdout.strip().splitlines()[-1]
    assert out == "32,05,20,28,27,29,33,19,17"


def test_script_editor(campaign):
    _run("script_editor", role="developer")


def test_detail_flags_concurrent_external_save(campaign):
    at = _run("detail", campaign_id=campaign["id"])
    other = storage.load_campaign(campaign["id"])
    other["wk_id"] = "202699"
    storage.save_campaign(other)

    at.run()

    assert not at.exception
    assert at.session_state["_save_conflict"]["other"]["wk_id"] == "202699"
    assert any("modified elsewhere" in w.value for w in at.warning)


def test_restore_other_version_after_conflict(campaign):
    at = _run("detail", campaign_id=campaign["id"])
    other = storage.load_campaign(campaign["id"])
    other["wk_id"] = "202699"
    storage.save_campaign(other)
    at.run()
    assert storage.load_campaign(campaign["id"])["wk_id"] == "202640"  # autosave clobbered it

    at.button(key="save_conflict_restore").click().run()

    assert not at.exception
    assert "_save_conflict" not in at.session_state
    assert storage.load_campaign(campaign["id"])["wk_id"] == "202699"
    at.run()
    assert "_save_conflict" not in at.session_state
