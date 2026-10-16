"""Auto-grouping of duplicate-priority rows on CSV import."""
import io

from ui import _import_csv_rows

CSV_TEXT = (
    "priority,campaign_name,theme,message,title,offer_type,offer_id,store_ids\n"
    "1,Campaign A,theme_wk28_Fri_A,Hello A,Title A,,,\n"
    "1,Campaign A,theme_wk28_Fri_B,Hello B,Title B,,,\n"
    "2,Campaign B,theme_wk28_Fri_C,Hello C,Title C,,,\n"
)


def test_duplicate_priorities_grouped_into_multi_theme_container():
    rows, warnings = _import_csv_rows(io.BytesIO(CSV_TEXT.encode("utf-8")))

    assert len(rows) == 2
    assert rows[0]["multi_theme"] is True
    assert [sr["theme"] for sr in rows[0]["sub_rows"]] == ["theme_wk28_Fri_A", "theme_wk28_Fri_B"]
    assert rows[1]["multi_theme"] is False
    assert rows[1]["theme"] == "theme_wk28_Fri_C"
    assert len(warnings) == 1 and "Auto-grouped" in warnings[0]


def test_unique_priorities_stay_standalone():
    text = (
        "priority,campaign_name,theme\n"
        "1,A,t1\n"
        "2,B,t2\n"
    )
    rows, warnings = _import_csv_rows(io.BytesIO(text.encode("utf-8")))

    assert [r["multi_theme"] for r in rows] == [False, False]
    assert warnings == []
