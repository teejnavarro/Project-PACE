"""Persistence layer: CRUD, channel isolation, backups, atomic writes."""
import json
import threading

import pytest

import storage


@pytest.fixture
def tmp_channels(tmp_path, monkeypatch):
    monkeypatch.setitem(storage._CHANNEL_BASES, "push", tmp_path / "push")
    monkeypatch.setitem(storage._CHANNEL_BASES, "rcs", tmp_path / "rcs")
    storage.set_active_channel("push")
    yield tmp_path
    storage.set_active_channel("push")


def test_create_save_load_roundtrip(tmp_channels):
    c = storage.create_campaign(wk_id="202640", send_date="2026-10-05", send_day="MONDAY")
    storage.save_campaign(c)

    loaded = storage.load_campaign(c["id"])
    assert loaded["wk_id"] == "202640"
    assert loaded["status"] == "Draft"
    assert loaded["activity_log"][0]["action"] == "Created"
    assert (tmp_channels / "push" / "data" / f"{c['id']}.json").exists()


def test_load_missing_returns_none(tmp_channels):
    assert storage.load_campaign("doesnotexist") is None


def test_save_updates_updated_at(tmp_channels):
    c = storage.create_campaign()
    original = c["updated_at"]
    storage.save_campaign(c)

    assert storage.load_campaign(c["id"])["updated_at"] >= original


def test_list_campaigns_sorted_desc_and_skips_bad_json(tmp_channels):
    for d in ("2026-01-01", "2026-03-01", "2026-02-01"):
        storage.save_campaign(storage.create_campaign(send_date=d))
    (tmp_channels / "push" / "data" / "broken.json").write_text("{not json", encoding="utf-8")

    dates = [c["send_date"] for c in storage.list_campaigns()]
    assert dates == ["2026-03-01", "2026-02-01", "2026-01-01"]


def test_delete_moves_to_trash(tmp_channels):
    c = storage.create_campaign()
    storage.save_campaign(c)

    assert storage.delete_campaign(c["id"]) is True
    assert storage.load_campaign(c["id"]) is None
    trash = list((tmp_channels / "push" / "data" / "_trash").glob(f"{c['id']}_*.json"))
    assert len(trash) == 1
    assert storage.delete_campaign(c["id"]) is False


def test_duplicate_resets_lifecycle(tmp_channels):
    src = storage.create_campaign(wk_id="202640")
    src["status"] = "Exported"
    src["rows"] = [{"campaign_name": "A"}]
    src["audit"] = [{"action": "edit"}]
    storage.save_campaign(src)

    clone = storage.duplicate_campaign(src["id"])
    assert clone["id"] != src["id"]
    assert clone["status"] == "Draft"
    assert clone["audit"] == []
    # migrate_campaign backfills a stable _row_id on load, so the row carries one now.
    assert len(clone["rows"]) == 1
    assert clone["rows"][0]["campaign_name"] == "A"
    assert "_row_id" in clone["rows"][0]
    assert storage.load_campaign(clone["id"]) is not None
    assert storage.duplicate_campaign("missing") is None


def test_backups_rotate(tmp_channels, monkeypatch):
    monkeypatch.setattr(storage, "BACKUP_RETENTION", 3)
    c = storage.create_campaign()
    for i in range(6):
        c["wk_id"] = str(i)
        storage.save_campaign(c)

    backups = list((tmp_channels / "push" / "data" / "_backups" / c["id"]).glob("*.json"))
    assert len(backups) == 3


def test_backup_contains_previous_version(tmp_channels):
    c = storage.create_campaign(wk_id="old")
    storage.save_campaign(c)
    c["wk_id"] = "new"
    storage.save_campaign(c)

    backups = list((tmp_channels / "push" / "data" / "_backups" / c["id"]).glob("*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8"))["wk_id"] == "old"


def test_atomic_write_leaves_no_temp_files(tmp_channels):
    c = storage.create_campaign()
    storage.save_campaign(c)
    storage.save_campaign(c)

    data_dir = tmp_channels / "push" / "data"
    assert list(data_dir.glob("*.tmp")) == []
    assert list(data_dir.glob(".*")) == []


def test_failed_write_keeps_original_intact(tmp_channels, monkeypatch):
    c = storage.create_campaign(wk_id="good")
    storage.save_campaign(c)

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(storage.os, "replace", boom)
    c["wk_id"] = "bad"
    with pytest.raises(OSError):
        storage.save_campaign(c)

    assert storage.load_campaign(c["id"])["wk_id"] == "good"
    assert list((tmp_channels / "push" / "data").glob("*.tmp")) == []


def test_channel_isolation(tmp_channels):
    storage.set_active_channel("push")
    p = storage.create_campaign(wk_id="push")
    storage.save_campaign(p)

    storage.set_active_channel("rcs")
    r = storage.create_campaign(wk_id="rcs")
    storage.save_campaign(r)

    assert [c["wk_id"] for c in storage.list_campaigns()] == ["rcs"]
    assert storage.load_campaign(p["id"]) is None
    storage.set_active_channel("push")
    assert [c["wk_id"] for c in storage.list_campaigns()] == ["push"]


def test_unknown_channel_ignored(tmp_channels):
    storage.set_active_channel("rcs")
    storage.set_active_channel("email")
    assert storage.get_active_channel() == "rcs"


def test_active_channel_is_per_thread(tmp_channels):
    storage.set_active_channel("rcs")
    seen = {}

    def worker():
        seen["default"] = storage.get_active_channel()
        storage.set_active_channel("push")
        seen["after_set"] = storage.get_active_channel()

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert seen == {"default": "push", "after_set": "push"}
    assert storage.get_active_channel() == "rcs"
