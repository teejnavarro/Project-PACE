"""CSV export/import roundtrip preserves text-like IDs and literal NA/null strings."""
import io

import pandas as pd

from ui import _build_csv_bytes, _import_csv_rows

ROWS = [
    {
        "priority": 1,
        "store_ids": "100,200,300",
        "division_ids": "29,33",
        "offer_id": "5487201739180510",
        "campaign_name": "NA",
        "banners": "pine_and_peak,blueharbor",
        "rich_push_image": "Y",
        "theme": "null",
    },
    {
        "priority": 2,
        "store_ids": "007",
        "division_ids": "",
        "offer_id": "",
        "campaign_name": "Test",
        "banners": "",
        "rich_push_image": "N",
        "theme": "nan",
    },
]


def _roundtrip(rows):
    data = _build_csv_bytes(pd.DataFrame(rows))
    return data, _import_csv_rows(io.BytesIO(data))


def test_export_has_bom_and_excel_text_wrappers():
    data, _ = _roundtrip(ROWS)
    text = data.decode("utf-8-sig")

    assert data.startswith(b"\xef\xbb\xbf")
    assert '"=""5487201739180510"""' in text
    assert '"=""007"""' in text


def test_roundtrip_preserves_values():
    _, (rows, warnings) = _roundtrip(ROWS)

    assert warnings == []
    assert len(rows) == 2
    first, second = rows
    assert first["store_ids"] == "100,200,300"
    assert first["division_ids"] == "29,33"
    assert first["offer_id"] == "5487201739180510"
    assert first["campaign_name"] == "NA"
    assert first["theme"] == "null"
    assert first["banners"] == "pine_and_peak,blueharbor"
    assert first["rich_push_image"] is True
    assert second["store_ids"] == "007"
    assert second["offer_id"] == ""
    assert second["theme"] == "nan"
    assert second["rich_push_image"] is False
    assert [r["priority"] for r in rows] == [1, 2]


def test_save_path_writes_same_bytes(tmp_path):
    target = tmp_path / "sub" / "grid.csv"
    data = _build_csv_bytes(pd.DataFrame(ROWS), save_path=target)

    assert target.read_bytes() == data
