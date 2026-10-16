# app/audit.py
from datetime import datetime, timezone


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _friendly_ts(iso_ts: str) -> str:
    """Convert ISO timestamp to a friendlier display format."""
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %I:%M %p")
    except (ValueError, TypeError):
        return iso_ts


def diff_rows(before, after):
    """Return a list of per-row diffs: [{'row': idx, 'changes': {col: (old, new), ...}}, ...]"""
    diffs = []
    max_len = max(len(before or []), len(after or []))
    for i in range(max_len):
        b = before[i] if i < len(before) else None
        a = after[i] if i < len(after) else None
        if b is None and a is not None:
            diffs.append({"row": i, "changes": {"__added__": (None, a)}})
            continue
        if a is None and b is not None:
            diffs.append({"row": i, "changes": {"__removed__": (b, None)}})
            continue
        # compare fields
        change = {}
        for k in set((b or {}).keys()) | set((a or {}).keys()):
            if k in ("custom_sql", "row_type", "_row_id", "handling_time", "sql_template_name", "sub_rows", "multi_theme"):
                continue  # skip noisy fields
            if (b or {}).get(k) != (a or {}).get(k):
                change[k] = ((b or {}).get(k), (a or {}).get(k))
        if change:
            diffs.append({"row": i, "changes": change})
    return diffs


def _summarize_diffs(diffs: list) -> list[str]:
    """Turn diff_rows output into human-readable change descriptions."""
    lines = []
    for d in diffs:
        row_num = d["row"] + 1
        for col, (old, new) in d["changes"].items():
            if col == "__added__":
                name = (new or {}).get("campaign_name") or f"Row {row_num}"
                lines.append(f"Added row {row_num} ({name})")
            elif col == "__removed__":
                name = (old or {}).get("campaign_name") or f"Row {row_num}"
                lines.append(f"Removed row {row_num} ({name})")
            else:
                old_str = str(old)[:40] if old else "(empty)"
                new_str = str(new)[:40] if new else "(empty)"
                lines.append(f"Row {row_num}: **{col}** → {new_str}")
    return lines


_ACTION_LABELS = {
    "add_row": "Added blank row",
    "remove_row": "Removed row",
    "edit_rows": "Edited rows",
    "add_from_sql_template": "Added SQL template(s)",
    "duplicate_row": "Duplicated row",
}


def log_change(audit_store, action, before=None, after=None, details=None):
    """Append a compact, human-readable audit entry."""
    summary_parts = []

    # Build summary from action + details
    label = _ACTION_LABELS.get(action, action)

    if action == "add_from_sql_template" and details:
        templates = details.get("sql_templates", [])
        summary_parts.append(f"{label}: {', '.join(templates)}")
    elif action == "remove_row" and details:
        removed = details.get("removed", {})
        name = removed.get("campaign_name") or removed.get("theme") or "row"
        summary_parts.append(f"{label}: {name}")
    elif action == "edit_rows" and before is not None and after is not None:
        diffs = diff_rows(before, after)
        change_lines = _summarize_diffs(diffs)
        summary_parts.extend(change_lines) if change_lines else summary_parts.append(label)
    elif action == "duplicate_row" and details:
        summary_parts.append(f"{label}: from row {details.get('source_row', '?')}")
    else:
        summary_parts.append(label)

    entry = {
        "ts": timestamp(),
        "action": action,
        "summary": summary_parts,
    }
    audit_store.append(entry)
