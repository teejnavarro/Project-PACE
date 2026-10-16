"""Regression tests for CRF Push Section cell parsing.

Covers the failure modes discovered during the NorCal_HatchChile_AugustRoastingEvents
Wk32 Saturday report: outer-quote wrappings, single-line "soft-wrap" pastes with
plain spaces, semicolons/pipes/tabs/NBSP separators, and inner-quoted values.
"""
import pytest

from ui import _crf_clean_cell, _crf_expand_pushsection_cell

EXPECT = {"pushsection": "aemLandingPage", "param_q": "div/hatch-chiles", "screentitle": "Hatch_Chiles"}

CASES = {
    "user-reported outer quotes":         '"pushsection=aemLandingPage\nq=div/hatch-chiles\nscreentitle=Hatch_Chiles"',
    "crlf lines":                         '"pushsection=aemLandingPage\r\nq=div/hatch-chiles\r\nscreentitle=Hatch_Chiles"',
    "cr-only lines":                      '"pushsection=aemLandingPage\rq=div/hatch-chiles\rscreentitle=Hatch_Chiles"',
    "single-line spaces (soft-wrap)":     '"pushsection=aemLandingPage q=div/hatch-chiles screentitle=Hatch_Chiles"',
    "semicolons":                         '"pushsection=aemLandingPage; q=div/hatch-chiles; screentitle=Hatch_Chiles"',
    "commas":                             '"pushsection=aemLandingPage, q=div/hatch-chiles, screentitle=Hatch_Chiles"',
    "NBSP separators":                    '"pushsection=aemLandingPage\u00a0q=div/hatch-chiles\u00a0screentitle=Hatch_Chiles"',
    "inner-quoted values":                'pushsection="aemLandingPage"\nq="div/hatch-chiles"\nscreentitle="Hatch_Chiles"',
    "tabs between":                       '"pushsection=aemLandingPage\tq=div/hatch-chiles\tscreentitle=Hatch_Chiles"',
    "pipes between":                      '"pushsection=aemLandingPage | q=div/hatch-chiles | screentitle=Hatch_Chiles"',
    "smart double quotes outer":          '\u201cpushsection=aemLandingPage\nq=div/hatch-chiles\nscreentitle=Hatch_Chiles\u201d',
    "no outer quote (baseline)":          'pushsection=aemLandingPage\nq=div/hatch-chiles\nscreentitle=Hatch_Chiles',
    "mixed uppercase + underscores":      '"PushSection=aemLandingPage\nScreen_Title=Hatch_Chiles\nQ=div/hatch-chiles"',
}


@pytest.mark.parametrize("raw", list(CASES.values()), ids=list(CASES.keys()))
def test_pushsection_cell_variants(raw):
    parsed, unknown = _crf_expand_pushsection_cell(_crf_clean_cell(raw))

    assert parsed == EXPECT
    assert unknown == []


def test_plain_value_routes_to_pushsection():
    parsed, _ = _crf_expand_pushsection_cell(_crf_clean_cell("aemLandingPage"))

    assert parsed == {"pushsection": "aemLandingPage"}


def test_unknown_keys_surfaced_known_keys_still_parse():
    parsed, unknown = _crf_expand_pushsection_cell("pushsection=x\nfoo=bar\nq=y")

    assert parsed == {"pushsection": "x", "param_q": "y"}
    assert unknown == ["foo"]


def test_embedded_space_in_value_preserved():
    # Only split at whitespace immediately followed by `key=`.
    parsed, _ = _crf_expand_pushsection_cell("pushsection=aem q=my search screentitle=x")

    assert parsed == {"pushsection": "aem", "param_q": "my search", "screentitle": "x"}
