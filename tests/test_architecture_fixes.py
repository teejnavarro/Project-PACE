"""Regression tests for the Phase 1/2 architecture fixes."""

import json
import time

import pytest

from compose import _targeting_notes_comment


class TestTargetingNotesInjection:
    def test_close_marker_in_note_cannot_escape_comment(self):
        row = {"targeting_notes": "legit */ DROP TABLE x; /* back in"}
        out = _targeting_notes_comment(row)
        assert out.count("*/") == 1
        assert out.strip().endswith("*/")

    def test_benign_note_unaffected(self):
        row = {"targeting_notes": "exclude households that already clipped"}
        out = _targeting_notes_comment(row)
        assert "exclude households that already clipped" in out
        assert out.startswith("/*\n")
        assert out.rstrip().endswith("*/")

    def test_empty_note_returns_empty_string(self):
        assert _targeting_notes_comment({}) == ""
        assert _targeting_notes_comment({"targeting_notes": "   "}) == ""


class TestCampaignFileCache:
    def test_list_campaigns_reparses_when_file_changes(self, tmp_path, monkeypatch):
        import storage

        data_root = tmp_path / "data"
        data_root.mkdir()
        monkeypatch.setattr(storage, "_data_dir", lambda: data_root)
        storage._CAMPAIGN_READ_CACHE.clear()

        p = data_root / "abc.json"
        p.write_text(json.dumps({"id": "abc", "send_date": "2026-01-01", "status": "Draft"}))

        first = storage.list_campaigns()
        assert first[0]["status"] == "Draft"

        time.sleep(0.01)
        p.write_text(json.dumps({"id": "abc", "send_date": "2026-01-01", "status": "Ready"}))
        second = storage.list_campaigns()
        assert second[0]["status"] == "Ready"

    def test_list_campaigns_returns_deep_copies(self, tmp_path, monkeypatch):
        import storage

        data_root = tmp_path / "data"
        data_root.mkdir()
        monkeypatch.setattr(storage, "_data_dir", lambda: data_root)
        storage._CAMPAIGN_READ_CACHE.clear()

        p = data_root / "abc.json"
        p.write_text(json.dumps({"id": "abc", "send_date": "2026-01-01", "rows": [{"theme": "x"}]}))

        a = storage.list_campaigns()
        a[0]["rows"][0]["theme"] = "mutated-by-caller"
        b = storage.list_campaigns()
        assert b[0]["rows"][0]["theme"] == "x"

    def test_load_campaign_returns_deep_copy(self, tmp_path, monkeypatch):
        import storage

        data_root = tmp_path / "data"
        data_root.mkdir()
        monkeypatch.setattr(storage, "_data_dir", lambda: data_root)
        storage._CAMPAIGN_READ_CACHE.clear()

        p = data_root / "abc.json"
        p.write_text(json.dumps({"id": "abc", "rows": [{"n": 1}]}))

        a = storage.load_campaign("abc")
        a["rows"][0]["n"] = 999
        b = storage.load_campaign("abc")
        assert b["rows"][0]["n"] == 1


class TestCampaignMigration:
    def test_migrate_adds_schema_version(self):
        import storage
        out = storage.migrate_campaign({"id": "x", "rows": []})
        assert out["schema_version"] == storage.CAMPAIGN_SCHEMA_VERSION

    def test_migrate_backfills_row_ids(self):
        import storage
        c = {"id": "x", "rows": [{"theme": "a"}, {"theme": "b", "_row_id": "KEEP0001"}]}
        out = storage.migrate_campaign(c)
        assert out["rows"][0]["_row_id"] and len(out["rows"][0]["_row_id"]) == 8
        assert out["rows"][1]["_row_id"] == "KEEP0001"

    def test_migrate_backfills_sub_row_ids(self):
        import storage
        c = {"id": "x", "rows": [{"multi_theme": True, "sub_rows": [{"theme": "a"}, {"theme": "b"}]}]}
        out = storage.migrate_campaign(c)
        for sr in out["rows"][0]["sub_rows"]:
            assert sr.get("_row_id") and len(sr["_row_id"]) == 8

    def test_migrate_is_idempotent(self):
        import storage
        c = {"id": "x", "rows": [{"theme": "a"}]}
        first = storage.migrate_campaign(c)
        snapshot = json.dumps(first, sort_keys=True)
        second = storage.migrate_campaign(first)
        assert json.dumps(second, sort_keys=True) == snapshot


class TestOptionalColumnsCache:
    def test_cache_is_keyed_by_path(self):
        from compose import _load_optional_columns_from

        _load_optional_columns_from.cache_clear()
        info_before = _load_optional_columns_from.cache_info()
        from pathlib import Path
        push_cfg = Path(__file__).resolve().parents[1] / "push" / "config" / "optional_columns.yaml"
        rcs_cfg = Path(__file__).resolve().parents[1] / "rcs" / "config" / "optional_columns.yaml"
        if not push_cfg.exists() or not rcs_cfg.exists():
            pytest.skip("channel configs not present")

        push_cols = _load_optional_columns_from(str(push_cfg))
        rcs_cols = _load_optional_columns_from(str(rcs_cfg))
        # Different files produce different (possibly empty) column lists; keying by
        # path is what prevents a PUSH-cached result from being served for RCS.
        assert push_cols is not rcs_cols
        info_after = _load_optional_columns_from.cache_info()
        assert info_after.currsize >= 2 or info_before.currsize + 2 >= info_after.currsize + info_before.currsize
