# app/compose.py
# Concatenates rendered Jinja2 sections into a single SQL file.
# Keep this separate from ui.py so it can be tested independently.

import re
from pathlib import Path
from jinja2 import Environment
from renderer import create_permissive_env
from functools import lru_cache
import yaml as _yaml
from storage import channel_dir

ROOT = Path(__file__).resolve().parents[1]

@lru_cache(maxsize=4)
def _load_optional_columns_from(cfg_path_str: str) -> tuple:
    """Load optional_columns.yaml at an explicit path. Cached per-path."""
    with open(cfg_path_str, "r", encoding="utf-8") as f:
        data = _yaml.safe_load(f)
    cols = data.get("optional_columns", []) or []
    # Return tuple so lru_cache can hash it; callers treat as sequence.
    return tuple(cols)


def _load_optional_columns() -> list:
    """Load optional_columns.yaml for the currently active channel."""
    cfg_path = channel_dir("config") / "optional_columns.yaml"
    return list(_load_optional_columns_from(str(cfg_path)))


# Back-compat: callers (detail.py) do _load_optional_columns.cache_clear() after schema edits.
_load_optional_columns.cache_clear = _load_optional_columns_from.cache_clear  # type: ignore[attr-defined]

# All form fields passed to the campaign INSERT template
REQUIRED_FIELDS = ["campaign_name", "title", "message", "media_url", "theme", "pushsection", "param_q", "screentitle"]
OPTIONAL_FIELDS = [
    "subtitle", "gameid", "product", "searchterm", "store", "seller",
    "category", "program", "pagname", "datasource", "modelconfigid",
    "partnerid", "media_type", "pushlinks", "autoimage",
]

# String fields that should have apostrophes escaped (\\') in SQL template output
_SQL_ESCAPE_FIELDS = {"title", "message"}

# Matches a single-quoted literal followed by `as CANONICALCAMPAIGNID` in rendered SQL
_CANONICALCAMPAIGNID_RE = re.compile(
    r"'[^']*'(\s+as\s+CANONICALCAMPAIGNID\b)", re.IGNORECASE
)


def _escape_sql_strings(ctx: dict) -> dict:
    """Return a copy of *ctx* with single quotes escaped in string fields."""
    out = dict(ctx)
    for key in _SQL_ESCAPE_FIELDS:
        val = out.get(key)
        if isinstance(val, str) and "'" in val:
            out[key] = val.replace("'", "\\'")
    return out


def _override_canonicalcampaignid(rendered_sql: str, row: dict) -> str:
    """Replace the literal preceding ``as CANONICALCAMPAIGNID`` with the row's value.

    SQL templates hard-code ``'' as CANONICALCAMPAIGNID``. When the row dict
    supplies a non-empty CANONICALCAMPAIGNID, swap the literal so the user's
    value wins over the template default.
    """
    val = (row.get("CANONICALCAMPAIGNID") or "").strip()
    if not val:
        return rendered_sql
    escaped = val.replace("'", "\\'")
    return _CANONICALCAMPAIGNID_RE.sub(
        lambda m: f"'{escaped}'{m.group(1)}", rendered_sql
    )


def _expand_offer_ids(ctx: dict) -> dict:
    """Expand comma-separated offer_id into numbered offer_id_1, offer_id_2, … for Jinja2.

    Also produces ``offer_id_list`` — a SQL-ready quoted string for IN clauses,
    e.g. ``'ABC123','DEF456','GHI789'``.
    """
    raw = (ctx.get("offer_id") or "").strip()
    if not raw:
        return ctx
    ids = [v.strip() for v in raw.split(",") if v.strip()]
    for i, oid in enumerate(ids, start=1):
        ctx[f"offer_id_{i}"] = oid
    ctx["offer_id_list"] = ",".join(f"'{oid}'" for oid in ids)
    return ctx


def _expand_extra_themes(ctx: dict) -> dict:
    """Inject numbered theme_1, theme_2, … from extra_themes list into context for Jinja2."""
    extra = ctx.get("extra_themes", [])
    if not extra:
        return ctx
    for i, theme_val in enumerate(extra, start=1):
        ctx[f"theme_{i}"] = theme_val
    return ctx


# Targeting fields for WHERE clause generation
TARGETING_FIELDS = ["division_ids", "division_mode", "banners", "banner_mode", "store_ids", "store_mode"]

# Offer type templates live in macros/offer_types/ as editable .sql.j2 files.
# Path resolves per channel (Phase 1: PUSH = ROOT/macros/offer_types).
def _offer_types_dir() -> Path:
    return channel_dir("macros") / "offer_types"

# Map offer type UI names to template file stems
_OFFER_TYPE_FILES = {
    "STORE COUPON": "store_coupon",
    "PERSONALIZED DEAL": "personalized_deal",
    "PUSHSECTION": "pushsection",
}


@lru_cache(maxsize=16)
def _load_offer_type_template(offer_type: str) -> dict:
    """Load offer type template from macros/offer_types/.

    Returns dict with keys:
        join_template:     str       — raw Jinja2 template text for the JOIN SQL
        where_condition:   str       — WHERE condition fragment
        reserved_aliases:  set[str]  — aliases reserved by this offer JOIN
    """
    stem = _OFFER_TYPE_FILES.get(offer_type)
    if not stem:
        return {"join_template": "", "where_condition": "", "reserved_aliases": set()}

    path = _offer_types_dir() / f"{stem}.sql.j2"
    if not path.exists():
        return {"join_template": "", "where_condition": "", "reserved_aliases": set()}

    text = path.read_text(encoding="utf-8")

    # Parse metadata from the first Jinja2 comment block {# ... #}
    header: dict[str, str] = {}
    header_match = re.match(r"\{#(.*?)#\}", text, re.DOTALL)
    if header_match:
        for line in header_match.group(1).splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                header[key.strip()] = val.strip()
        body = text[header_match.end():].strip()
    else:
        body = text.strip()

    where_cond = header.get("where_condition", "")
    aliases_raw = header.get("reserved_aliases", "")
    reserved = {a.strip() for a in aliases_raw.split(",") if a.strip()}

    return {
        "join_template": body,
        "where_condition": where_cond,
        "reserved_aliases": reserved,
    }

# ── Input sanitisation helpers ──────────────────────────────────────
_NUMERIC_RE = re.compile(r"^-?\d+$")

def _sanitize_numeric_ids(raw: str) -> list[str]:
    """Split comma-separated input and keep only tokens that are valid integers.
    Silently drops tokens like SQL keywords or punctuation."""
    return [v.strip() for v in raw.split(",") if v.strip() and _NUMERIC_RE.match(v.strip())]

def _sanitize_offer_ids(raw: str) -> list[str]:
    """Split comma-separated offer IDs and escape single quotes (safe for string literals)."""
    return [v.strip().replace("'", "''") for v in raw.split(",") if v.strip() and not re.search(r"[;\\]", v.strip())]

def _sanitize_banner_names(raw: str) -> list[str]:
    """Split comma-separated banners, lowercase, escape quotes, drop suspicious tokens."""
    return [
        b.strip().lower().replace("'", "''")
        for b in raw.split(",")
        if b.strip() and not re.search(r"[;\\]", b.strip())
    ]


def _build_or_group_sql(group: dict) -> str:
    """Build a single OR-group SQL fragment from a structured dict.

    Expected keys:
        division_ids: str  (comma-separated, e.g. "29" or "5,17")
        div_mode:     str  ("IN" or "NOT IN")
        banners:      str  (comma-separated, e.g. "cedar_market,blueharbor")
        banner_mode:  str  ("IN" or "NOT IN")
        store_ids:    str  (comma-separated, e.g. "100,200")
        store_mode:   str  ("IN" or "NOT IN")
    """
    conds = []

    # Division condition
    div_raw = (group.get("division_ids") or "").strip()
    if div_raw:
        ids = _sanitize_numeric_ids(div_raw)
        mode = group.get("div_mode", "IN").strip().upper()
        if mode not in ("IN", "NOT IN"):
            mode = "IN"
        if not ids:
            pass  # skip — no valid numeric IDs
        elif len(ids) == 1:
            op = "!=" if mode == "NOT IN" else "="
            conds.append(f"a.division_id {op} {ids[0]}")
        else:
            conds.append(f"a.division_id {mode} ({','.join(ids)})")

    # Banner condition
    ban_raw = (group.get("banners") or "").strip()
    if ban_raw:
        banners = _sanitize_banner_names(ban_raw)
        mode = group.get("banner_mode", "IN").strip().upper()
        if mode not in ("IN", "NOT IN"):
            mode = "IN"
        if banners:
            if len(banners) == 1:
                op = "!=" if mode == "NOT IN" else "="
                conds.append(f"a.store_banner {op} '{banners[0]}'")
            else:
                quoted = ",".join(f"'{b}'" for b in banners)
                conds.append(f"a.store_banner {mode} ({quoted})")

    # Store ID condition
    sid_raw = (group.get("store_ids") or "").strip()
    if sid_raw:
        ids = _sanitize_numeric_ids(sid_raw)
        mode = group.get("store_mode", "IN").strip().upper()
        if mode not in ("IN", "NOT IN"):
            mode = "IN"
        if ids:
            if len(ids) == 1:
                op = "!=" if mode == "NOT IN" else "="
                conds.append(f"a.store_id {op} {ids[0]}")
            else:
                conds.append(f"a.store_id {mode} ({','.join(ids)})")

    return " AND ".join(conds) if conds else ""


def _div_banner_or_clause(row: dict) -> str:
    """Build a compound OR clause from structured div_banner_groups.

    row["div_banner_groups"] is a list of dicts, each with:
        division_ids, div_mode, banners, banner_mode, store_ids, store_mode

    Example output:
                ((a.division_id = 25 AND a.store_banner IN ('cedar_market','blueharbor'))
                    OR (a.division_id = 34 AND a.store_banner IN ('redwood_fresh','meadowlane')))
    """
    groups = row.get("div_banner_groups") or []
    if not groups:
        return ""
    parts = []
    for g in groups:
        sql = _build_or_group_sql(g)
        if sql:
            parts.append(f"({sql})")
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return "(" + "\n  OR ".join(parts) + ")"


def _targeting_conditions(row: dict) -> list[str]:
    """Return a list of WHERE condition strings from targeting columns."""
    clauses = []

    # Division IDs — numeric
    div_raw = (row.get("division_ids") or "").strip()
    if div_raw:
        ids = _sanitize_numeric_ids(div_raw)
        mode = row.get("division_mode", "IN").strip().upper()
        if mode not in ("IN", "NOT IN"):
            mode = "IN"
        if not ids:
            pass  # skip — no valid numeric IDs
        elif len(ids) == 1 and mode == "IN":
            clauses.append(f"a.division_id = {ids[0]}")
        elif len(ids) == 1 and mode == "NOT IN":
            clauses.append(f"a.division_id != {ids[0]}")
        else:
            clauses.append(f"a.division_id {mode} ({','.join(ids)})")

    # Banners — string (always lowercase)
    ban_raw = (row.get("banners") or "").strip()
    if ban_raw:
        banners = _sanitize_banner_names(ban_raw)
        mode = row.get("banner_mode", "IN").strip().upper()
        if mode not in ("IN", "NOT IN"):
            mode = "IN"
        if banners:
            quoted = ",".join(f"'{b}'" for b in banners)
            if len(banners) == 1 and mode == "IN":
                clauses.append(f"a.store_banner = '{banners[0]}'")
            elif len(banners) == 1 and mode == "NOT IN":
                clauses.append(f"a.store_banner != '{banners[0]}'")
            else:
                clauses.append(f"a.store_banner {mode} ({quoted})")

    # Store IDs — numeric
    sid_raw = (row.get("store_ids") or "").strip()
    if sid_raw:
        ids = _sanitize_numeric_ids(sid_raw)
        mode = row.get("store_mode", "IN").strip().upper()
        if mode not in ("IN", "NOT IN"):
            mode = "IN"
        if not ids:
            pass  # skip — no valid numeric IDs
        elif len(ids) == 1 and mode == "IN":
            clauses.append(f"a.store_id = {ids[0]}")
        elif len(ids) == 1 and mode == "NOT IN":
            clauses.append(f"a.store_id != {ids[0]}")
        else:
            clauses.append(f"a.store_id {mode} ({','.join(ids)})")

    # Division+Banner OR pairs (e.g. 25:cedar_market,blueharbor | 34:redwood_fresh,meadowlane)
    or_clause = _div_banner_or_clause(row)
    if or_clause:
        clauses.append(or_clause)

    return clauses


def build_targeting_clause(row: dict) -> str:
    """Build full WHERE clause from targeting columns. Returns empty string if none."""
    clauses = _targeting_conditions(row)
    if not clauses:
        return ""
    return "WHERE " + "\n  AND ".join(clauses)


def _format_offer_ids(raw: str) -> str:
    """Format comma-separated offer IDs into = or IN clause value."""
    ids = _sanitize_offer_ids(raw)
    if not ids:
        return "= ''"
    if len(ids) == 1:
        return f"= '{ids[0]}'"
    quoted = ",".join(f"'{oid}'" for oid in ids)
    return f"IN ({quoted})"


def build_offer_join(row: dict, tables: dict) -> str:
    """Build the JOIN subquery for the row's offer type.

    Loads the offer type template from macros/offer_types/ and renders it
    with the table paths and formatted offer ID clause.
    """
    offer_type = (row.get("offer_type") or "").strip().upper()
    offer_raw = (row.get("offer_id") or "").strip()
    offer_clause = _format_offer_ids(offer_raw)

    config = _load_offer_type_template(offer_type)
    join_template = config["join_template"]
    if not join_template:
        return ""

    env = create_permissive_env()
    try:
        return env.from_string(join_template).render(tables=tables, offer_clause=offer_clause)
    except Exception as exc:
        raise RuntimeError(f"Failed to render offer type template for '{offer_type}': {exc}") from exc


def build_where_clause(row: dict) -> str:
    """Build the combined WHERE clause from offer type + targeting."""
    conditions = []

    offer_type = (row.get("offer_type") or "").strip().upper()
    config = _load_offer_type_template(offer_type)
    if config["where_condition"]:
        conditions.append(config["where_condition"])

    conditions.extend(_targeting_conditions(row))

    if not conditions:
        return ""
    return "WHERE " + "\n  AND ".join(conditions)


def _targeting_notes_comment(row: dict) -> str:
    """Return a /* ... */ SQL comment block for targeting notes, or empty string."""
    notes = (row.get("targeting_notes") or "").strip()
    if not notes:
        return ""
    # Neutralize */ so a user note cannot close the comment block and inject SQL.
    safe = notes.replace("*/", "* /")
    lines = safe.splitlines()
    body = "\n".join(f"   {line}" for line in lines)
    return f"/*\n   Custom Targeting Instructions:\n{body}\n*/\n"


_FROM_LINE_RE = re.compile(r"(^FROM\s+.*Eligible_Push_Audience\s+\w+.*$)", re.MULTILINE | re.IGNORECASE)


def _inject_notes_after_from(sql: str, notes_comment: str) -> str:
    """Insert targeting notes comment after the FROM Eligible_Push_Audience line.

    If no matching FROM line is found, prepend the notes before the SQL as fallback.
    """
    if not notes_comment:
        return sql
    m = _FROM_LINE_RE.search(sql)
    if m:
        insert_pos = m.end()
        return sql[:insert_pos] + "\n" + notes_comment + sql[insert_pos:]
    # Fallback: prepend
    return notes_comment + sql


def _build_custom_joins(row: dict) -> str:
    """Build SQL text for any custom JOINs attached to a row.

    Each entry in row["custom_joins"] is a dict with keys:
        join_type  – JOIN / LEFT JOIN / INNER JOIN / CROSS JOIN
        table_path – fully-qualified BigQuery table
        alias      – table alias (e.g. 'c', 'd')
        on_clause  – the ON condition text
    Returns empty string if no custom joins.
    """
    # Determine reserved aliases from the auto-generated offer JOIN
    offer_type = (row.get("offer_type") or "").strip().upper()
    config = _load_offer_type_template(offer_type)
    _reserved = {"a"} | config["reserved_aliases"]

    joins = row.get("custom_joins") or []
    parts = []
    for j in joins:
        mode = (j.get("mode") or "structured").strip().lower()
        if mode == "freetext":
            raw = (j.get("raw_sql") or "").strip()
            if raw:
                parts.append(raw)
            continue
        # Structured mode
        jt = (j.get("join_type") or "JOIN").strip().upper()
        tbl = (j.get("table_path") or "").strip()
        alias = (j.get("alias") or "").strip()
        on = (j.get("on_clause") or "").strip()
        if not tbl:
            continue  # skip empty entries
        # Warn on reserved alias collision (append comment so developer notices)
        if alias.lower() in _reserved:
            parts.append(f"-- ⚠️ WARNING: alias '{alias}' conflicts with the auto-generated offer JOIN alias")
        line = f"{jt} {tbl}"
        if alias:
            line += f" {alias}"
        if on:
            line += f"\n  ON {on}"
        parts.append(line)
    return "\n".join(parts)


def render_campaign_insert(env: Environment, tables: dict, row: dict) -> str:
    """Render a single campaign INSERT block from form fields."""
    tmpl = env.get_template("campaign_insert.sql.j2")
    # Build context: required + optional fields
    ctx = {field: row.get(field, "") for field in REQUIRED_FIELDS + OPTIONAL_FIELDS}
    # autoimage needs special handling (None vs True/False)
    ai = row.get("autoimage")
    ctx["autoimage"] = None if (ai is None or ai == "") else ai
    ctx["tables"] = tables
    ctx["offer_type_value"] = (row.get("offer_type") or "").strip().upper()
    # Offer type JOIN and combined WHERE clause
    ctx["offer_join"] = build_offer_join(row, tables)
    ctx["custom_joins"] = _build_custom_joins(row)
    ctx["where_clause"] = build_where_clause(row)
    ctx["targeting_notes_comment"] = _targeting_notes_comment(row)
    # Build optional_cols context for the Jinja2 loop (driven by YAML)
    _opt_col_defs = _load_optional_columns()
    optional_cols_ctx = []
    for _col in _opt_col_defs:
        if _col.get("sql_managed", "loop") == "hardcoded":
            continue
        _name = _col["name"]
        _alias = _col.get("sql_alias", _name)
        _sql_type = _col.get("sql_type", "text")
        if _sql_type == "static":
            optional_cols_ctx.append({
                "alias": _alias,
                "sql_type": "static",
                "sql_expr": _col["sql_expr"],
            })
        elif _sql_type == "bool":
            _raw = row.get(_name, "")
            if isinstance(_raw, bool):
                _bval = _raw
            elif isinstance(_raw, str) and _raw.strip().lower() == "true":
                _bval = True
            elif isinstance(_raw, str) and _raw.strip().lower() == "false":
                _bval = False
            else:
                _bval = ""
            optional_cols_ctx.append({
                "alias": _alias,
                "sql_type": "bool",
                "value": _bval,
            })
        else:
            _raw = row.get(_name, "") or ""
            if _col.get("sql_escape", False):
                _raw = _raw.replace("'", "\\\'")
            optional_cols_ctx.append({
                "alias": _alias,
                "sql_type": "text",
                "value": _raw,
            })
    ctx["optional_cols"] = optional_cols_ctx
    try:
        rendered = tmpl.render(**ctx)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to render campaign insert for theme='{row.get('theme', '?')}': {exc}"
        ) from exc
    return rendered


def build_priority_block(tables: dict, rows: list[dict]) -> str:
    """Generate the TRUNCATE + INSERT for push_priority in UI order.

    Each row's primary theme and any extra_themes share the same priority number.
    """
    def _escape(val: str) -> str:
        return val.replace("'", "''")

    # Build list of (priority, theme) tuples — extra themes share parent row priority
    priority_entries: list[tuple[int, str]] = []
    for i, r in enumerate(rows):
        pri = int(r.get("priority", i + 1))
        # Multi-theme container: sub-rows contribute themes at parent priority
        if r.get("multi_theme") and r.get("sub_rows"):
            for sr in r["sub_rows"]:
                priority_entries.append((pri, sr.get("theme", "")))
                for et in sr.get("extra_themes", []):
                    if et.strip():
                        priority_entries.append((pri, et))
        else:
            priority_entries.append((pri, r.get("theme", "")))
            for et in r.get("extra_themes", []):
                if et.strip():
                    priority_entries.append((pri, et))

    values = ",\n".join(
        f"({pri}, '{_escape(t)}')"
        for pri, t in priority_entries
    )
    return (
        f"\n--============= [ COUNTS ] ======================================\n\n"
        f"TRUNCATE TABLE {tables['push_priority']};\n\n"
        f"INSERT INTO {tables['push_priority']} (priority,theme)\n"
        f"VALUES\n{values};\n"
    )


def build_sql(
    env: Environment,
    tables: dict,
    rows: list[dict],
    wk_id: str,
    send_date: str,
    sql_overrides: dict | None = None,
) -> str:
    """Compose the full SQL file from templates, rows, and static tail.

    ``sql_overrides`` is an optional dict mapping row ID → edited SQL string.
    When a row has an override, the override is used verbatim instead of
    rendering the row through Jinja2 or the form template.
    """
    overrides = sql_overrides or {}
    try:
        preamble = env.get_template("preamble.sql.j2").render(
            wk_id=wk_id, send_date=send_date, tables=tables
        )
    except Exception as exc:
        raise RuntimeError(f"Preamble render failed: {exc}") from exc

    env_sql = create_permissive_env()

    inserts = []
    for idx, r in enumerate(rows):
        label = r.get("campaign_name") or r.get("theme") or "Custom SQL"
        rid = r.get("_row_id", str(idx))

        # If the developer edited this row's SQL in the preview, use that verbatim
        if rid in overrides:
            inserts.append(overrides[rid])
            continue

        # ---- Multi-theme container: render each sub-row as separate INSERT ----
        if r.get("multi_theme") and r.get("sub_rows"):
            parent_pri = int(r.get("priority", idx + 1))
            for si, sr in enumerate(r["sub_rows"]):
                sr_label = sr.get("campaign_name") or sr.get("theme") or f"Sub-Row {si + 1}"
                sr_rid = sr.get("_row_id", f"{rid}_{si}")
                # Check for per-sub-row override
                if sr_rid in overrides:
                    inserts.append(overrides[sr_rid])
                    continue
                # Ensure sub-row uses parent priority
                sr_copy = dict(sr)
                sr_copy["priority"] = parent_pri

                if sr_copy.get("custom_sql"):
                    # SQL template sub-row — render through Jinja2
                    tpl_ctx = {k: v for k, v in sr_copy.items() if k not in ("custom_sql", "_row_id", "handling_time")}
                    tpl_ctx["wk_id"] = wk_id
                    tpl_ctx["send_date"] = send_date
                    tpl_ctx["tables"] = tables
                    tpl_ctx = _expand_offer_ids(tpl_ctx)
                    tpl_ctx = _expand_extra_themes(tpl_ctx)
                    tpl_ctx = _escape_sql_strings(tpl_ctx)
                    try:
                        rendered_sql = env_sql.from_string(sr_copy["custom_sql"]).render(**tpl_ctx)
                    except Exception as exc:
                        raise RuntimeError(
                            f"Failed to render SQL template sub-row '{sr_label}': {exc}"
                        ) from exc
                    rendered_sql = _override_canonicalcampaignid(rendered_sql, sr_copy)
                    notes_comment = _targeting_notes_comment(sr_copy)
                    rendered_sql = _inject_notes_after_from(rendered_sql, notes_comment)
                    inserts.append(
                        f"--======================================================================\n"
                        f"-- {sr_label} (custom SQL)\n"
                        f"--======================================================================\n"
                        f"{rendered_sql}"
                    )
                else:
                    # Standard form sub-row
                    extra_themes = [t for t in sr_copy.get("extra_themes", []) if t.strip()]
                    inserts.append(render_campaign_insert(env, tables, sr_copy))
                    for et in extra_themes:
                        dup = dict(sr_copy)
                        dup["theme"] = et
                        inserts.append(render_campaign_insert(env, tables, dup))
            continue

        if r.get("custom_sql"):
            # SQL template row — render through Jinja2 for placeholder substitution
            # Build context from all row fields + campaign-level vars
            tpl_ctx = {k: v for k, v in r.items() if k not in ("custom_sql", "_row_id", "handling_time")}
            tpl_ctx["wk_id"] = wk_id
            tpl_ctx["send_date"] = send_date
            tpl_ctx["tables"] = tables
            tpl_ctx = _expand_offer_ids(tpl_ctx)
            tpl_ctx = _expand_extra_themes(tpl_ctx)
            tpl_ctx = _escape_sql_strings(tpl_ctx)
            try:
                rendered_sql = env_sql.from_string(r["custom_sql"]).render(**tpl_ctx)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to render SQL template '{label}': {exc}"
                ) from exc
            rendered_sql = _override_canonicalcampaignid(rendered_sql, r)
            notes_comment = _targeting_notes_comment(r)
            rendered_sql = _inject_notes_after_from(rendered_sql, notes_comment)
            inserts.append(
                f"--======================================================================\n"
                f"-- {label} (custom SQL)\n"
                f"--======================================================================\n"
                f"{rendered_sql}"
            )
        else:
            # Form row — duplicate INSERT for each extra theme
            extra_themes = [t for t in r.get("extra_themes", []) if t.strip()]
            inserts.append(render_campaign_insert(env, tables, r))
            for et in extra_themes:
                dup = dict(r)
                dup["theme"] = et
                inserts.append(render_campaign_insert(env, tables, dup))
    priority = build_priority_block(tables, rows)

    try:
        finalization = env.get_template("finalization.sql.j2").render(tables=tables)
    except Exception as exc:
        raise RuntimeError(f"Finalization render failed: {exc}") from exc

    tail_path = channel_dir("extras") / "finalization_static_tail.sql"
    if tail_path.exists():
        static_tail_raw = tail_path.read_text(encoding="utf-8")
        try:
            static_tail = env_sql.from_string(static_tail_raw).render(tables=tables)
        except Exception:
            static_tail = static_tail_raw
    else:
        static_tail = "-- (optional) Counts/QC/Archive tail — paste into extras/finalization_static_tail.sql\n"

    return "\n\n".join([preamble] + inserts + [priority, finalization, static_tail])


# ────────────────────────────────────────────────────────────────────
# RCS SQL generation
# ────────────────────────────────────────────────────────────────────

_RCS_OFFER_TYPE_FILES = {
    "CHOICE":   "offer_types/choice.sql.j2",
    "CARD":     "offer_types/card.sql.j2",
    "CAROUSEL": "offer_types/carousel.sql.j2",
}

_RCS_DAY_ABBR = {0: "MON", 1: "TUE", 2: "WED", 3: "THU", 4: "FRI", 5: "SAT", 6: "SUN"}

# Fixed store-banner expression injected wherever a URL contains [BANNER] or an SSO
# URL flag is set. Banner codes use underscores, which are not valid in domain names.
_RCS_STORE_BANNER_EXPR = "REPLACE(store_banner, '_', '')"
_RCS_SSO_URL_SQL = (
    "'https://www.' ||"
    f" {_RCS_STORE_BANNER_EXPR} "
    "||'.com/account/sso'"
)
# Case-insensitive [BANNER] placeholder — accepts [BANNER], [banner], [Banner], etc.
_RCS_BANNER_PLACEHOLDER_RE = re.compile(r"\[banner\]", re.IGNORECASE)

# Shorthand: when a URL fragment starts with `.com` (case-insensitive, optional leading
# whitespace stripped), the user is passing only the tail of a banner URL and the app
# auto-prepends the fixed `https://www.` + store-banner boilerplate.
_RCS_DOTCOM_PREFIX_RE = re.compile(r"^\.com(?=[/?#]|$)", re.IGNORECASE)


def _rcs_sql_quote(raw: str) -> str:
    """Escape apostrophes for a single-quoted SQL string literal."""
    return (raw or "").replace("'", "\\'")


def _rcs_expand_banner_in_url(raw: str) -> str:
    """Return a SQL fragment for a URL that may contain a [BANNER] placeholder
    or use the '.com/...' shorthand.

    Cases (checked in order):
      - Empty:                emit ''
      - Starts with '.com':   treat as banner-URL tail; emit
                              'https://www.' || <store_banner_expr> || '.com/...'
                              (equivalent to typing '[BANNER].com/...')
      - Contains [BANNER]:    emit 'prefix' || <store_banner_expr> || 'suffix' ...
      - Otherwise:            emit 'raw' (quoted string literal, apostrophes escaped)
    """
    if not raw:
        return "''"
    stripped = raw.lstrip()
    if _RCS_DOTCOM_PREFIX_RE.match(stripped):
        tail = _rcs_sql_quote(stripped)
        return f"'https://www.' ||{_RCS_STORE_BANNER_EXPR} ||'{tail}'"
    if not _RCS_BANNER_PLACEHOLDER_RE.search(raw):
        return f"'{_rcs_sql_quote(raw)}'"
    parts = _RCS_BANNER_PLACEHOLDER_RE.split(raw)
    frags: list[str] = []
    for i, seg in enumerate(parts):
        if seg != "":
            frags.append(f"'{_rcs_sql_quote(seg)}'")
        if i < len(parts) - 1:
            frags.append(_RCS_STORE_BANNER_EXPR)
    return " ||".join(frags) if frags else "''"


def _rcs_sso_url_sql(flag: str) -> str:
    """Return the SSO URL SQL fragment for a button.
    Yes → standard SSO expression using store_banner. No/empty → ''.
    """
    return _RCS_SSO_URL_SQL if str(flag or "").strip().lower() in ("yes", "y", "true", "1") else "''"


def _rcs_targeting_conditions(row: dict) -> list[str]:
    """RCS targeting WHERE fragments. Uses `s.` alias (SMS_Population source).
    Mirrors _targeting_conditions() but PUSH's `a.` alias is swapped for `s.`.
    """
    clauses: list[str] = []

    div_raw = (row.get("division_ids") or "").strip()
    if div_raw:
        ids = _sanitize_numeric_ids(div_raw)
        mode = row.get("division_mode", "IN").strip().upper()
        if mode not in ("IN", "NOT IN"):
            mode = "IN"
        if ids:
            if len(ids) == 1 and mode == "IN":
                clauses.append(f"s.division_id = {ids[0]}")
            elif len(ids) == 1 and mode == "NOT IN":
                clauses.append(f"s.division_id != {ids[0]}")
            else:
                clauses.append(f"s.division_id {mode} ({','.join(ids)})")

    ban_raw = (row.get("banners") or "").strip()
    if ban_raw:
        banners = _sanitize_banner_names(ban_raw)
        mode = row.get("banner_mode", "IN").strip().upper()
        if mode not in ("IN", "NOT IN"):
            mode = "IN"
        if banners:
            quoted = ",".join(f"'{b}'" for b in banners)
            if len(banners) == 1 and mode == "IN":
                clauses.append(f"s.store_banner = '{banners[0]}'")
            elif len(banners) == 1 and mode == "NOT IN":
                clauses.append(f"s.store_banner != '{banners[0]}'")
            else:
                clauses.append(f"s.store_banner {mode} ({quoted})")

    sid_raw = (row.get("store_ids") or "").strip()
    if sid_raw:
        ids = _sanitize_numeric_ids(sid_raw)
        mode = row.get("store_mode", "IN").strip().upper()
        if mode not in ("IN", "NOT IN"):
            mode = "IN"
        if ids:
            if len(ids) == 1 and mode == "IN":
                clauses.append(f"s.store_id = {ids[0]}")
            elif len(ids) == 1 and mode == "NOT IN":
                clauses.append(f"s.store_id != {ids[0]}")
            else:
                clauses.append(f"s.store_id {mode} ({','.join(ids)})")

    or_clause = _rcs_div_banner_or_clause(row)
    if or_clause:
        clauses.append(or_clause)

    return clauses


def _rcs_build_or_group_sql(group: dict) -> str:
    """Build one OR-group SQL fragment for RCS (mirror of _build_or_group_sql with `s.` alias)."""
    conds: list[str] = []

    div_raw = (group.get("division_ids") or "").strip()
    if div_raw:
        ids = _sanitize_numeric_ids(div_raw)
        mode = group.get("div_mode", "IN").strip().upper()
        if mode not in ("IN", "NOT IN"):
            mode = "IN"
        if ids:
            if len(ids) == 1:
                op = "!=" if mode == "NOT IN" else "="
                conds.append(f"s.division_id {op} {ids[0]}")
            else:
                conds.append(f"s.division_id {mode} ({','.join(ids)})")

    ban_raw = (group.get("banners") or "").strip()
    if ban_raw:
        banners = _sanitize_banner_names(ban_raw)
        mode = group.get("banner_mode", "IN").strip().upper()
        if mode not in ("IN", "NOT IN"):
            mode = "IN"
        if banners:
            if len(banners) == 1:
                op = "!=" if mode == "NOT IN" else "="
                conds.append(f"s.store_banner {op} '{banners[0]}'")
            else:
                quoted = ",".join(f"'{b}'" for b in banners)
                conds.append(f"s.store_banner {mode} ({quoted})")

    sid_raw = (group.get("store_ids") or "").strip()
    if sid_raw:
        ids = _sanitize_numeric_ids(sid_raw)
        mode = group.get("store_mode", "IN").strip().upper()
        if mode not in ("IN", "NOT IN"):
            mode = "IN"
        if ids:
            if len(ids) == 1:
                op = "!=" if mode == "NOT IN" else "="
                conds.append(f"s.store_id {op} {ids[0]}")
            else:
                conds.append(f"s.store_id {mode} ({','.join(ids)})")

    return " AND ".join(conds) if conds else ""


def _rcs_div_banner_or_clause(row: dict) -> str:
    """Compound OR clause across multiple div_banner_groups (mirror of _div_banner_or_clause, `s.` alias)."""
    groups = row.get("div_banner_groups") or []
    if not groups:
        return ""
    parts: list[str] = []
    for g in groups:
        sql = _rcs_build_or_group_sql(g)
        if sql:
            parts.append(f"({sql})")
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return "(" + "\n  OR ".join(parts) + ")"


def _rcs_build_custom_joins(row: dict) -> str:
    """Build SQL text for any custom JOINs on an RCS row.
    Same shape as PUSH's _build_custom_joins but there is no auto-offer JOIN, so
    the only reserved alias is `s` (SMS_Population source).
    """
    _reserved = {"s"}
    joins = row.get("custom_joins") or []
    parts: list[str] = []
    for j in joins:
        mode = (j.get("mode") or "structured").strip().lower()
        if mode == "freetext":
            raw = (j.get("raw_sql") or "").strip()
            if raw:
                parts.append(raw)
            continue
        jt = (j.get("join_type") or "JOIN").strip().upper()
        tbl = (j.get("table_path") or "").strip()
        alias = (j.get("alias") or "").strip()
        on = (j.get("on_clause") or "").strip()
        if not tbl:
            continue
        if alias.lower() in _reserved:
            parts.append(f"-- ⚠️ WARNING: alias '{alias}' conflicts with the SMS_Population source alias 's'")
        line = f"{jt} {tbl}"
        if alias:
            line += f" {alias}"
        if on:
            line += f"\n  ON {on}"
        parts.append(line)
    return "\n".join(parts)


def _rcs_targeting_where(row: dict) -> str:
    """Join RCS targeting conditions into an AND-joined fragment (no leading WHERE)."""
    parts = _rcs_targeting_conditions(row)
    return "\n  AND ".join(parts) if parts else "1=1"


def _normalize_rcs_row(row: dict) -> dict:
    """Fill in default nested structures so RCS Jinja2 templates never see missing keys.

    Ensures row.cards has exactly 7 entries (max CAROUSEL) — templates slice to their
    needed count. Each card has body/media_title/media_url/buttons[4], each button has
    title/value/sso_url/push_section AND pre-computed _sql_value + _sql_sso_url that
    the templates emit as raw SQL fragments (handling [BANNER] and yes/no flags).
    row.general_buttons has exactly 3 entries with the same _sql_* precomputes.
    Does not mutate input.
    """
    out = dict(row)

    def _empty_button() -> dict:
        return {"title": "", "value": "", "sso_url": "", "push_section": ""}

    def _empty_card() -> dict:
        return {"body": "", "media_title": "", "media_url": "", "message_footer": "", "buttons": [_normalize_button(_empty_button()) for _ in range(4)]}

    def _normalize_button(b: dict | None) -> dict:
        b = {**_empty_button(), **(b or {})}
        return {
            "title": b.get("title", "") or "",
            "value": b.get("value", "") or "",
            "sso_url": b.get("sso_url", "") or "",
            "push_section": b.get("push_section", "") or "",
            "_sql_value": _rcs_expand_banner_in_url(b.get("value", "") or ""),
            "_sql_sso_url": _rcs_sso_url_sql(b.get("sso_url", "") or ""),
        }

    def _normalize_card(c: dict | None, idx: int = 0) -> dict:
        if not c:
            return {**_empty_card(), "_sql_footer": (" Txt STOP 2 end" if idx == 0 else "")}
        btns = list(c.get("buttons") or [])
        while len(btns) < 4:
            btns.append(_empty_button())
        body = c.get("body", "") or ""
        # Card 1 is always the legal footer. For cards 2+, use the user's stored flag;
        # when the flag is missing (legacy data), fall back to "populated body = footer on".
        raw_flag = c.get("message_footer")
        if idx == 0:
            sql_footer = " Txt STOP 2 end"
        else:
            if raw_flag is None:
                on = bool(body.strip())
            else:
                on = str(raw_flag).strip().lower() in ("yes", "y", "true", "1")
            sql_footer = " Txt STOP 2 end" if on else ""
        return {
            "body": body,
            "media_title": c.get("media_title", "") or "",
            "media_url": c.get("media_url", "") or "",
            "message_footer": raw_flag if raw_flag is not None else ("yes" if (idx > 0 and body.strip()) else ""),
            "_sql_footer": sql_footer,
            "buttons": [_normalize_button(b) for b in btns[:4]],
        }

    raw_cards = list(out.get("cards") or [])
    normalized = [_normalize_card(c, i) for i, c in enumerate(raw_cards[:7])]
    while len(normalized) < 7:
        normalized.append(_normalize_card(None, len(normalized)))
    out["cards"] = normalized

    raw_gb = list(out.get("general_buttons") or [])
    while len(raw_gb) < 3:
        raw_gb.append(_empty_button())
    out["general_buttons"] = [_normalize_button(b) for b in raw_gb[:3]]

    out["targeting_where"] = _rcs_targeting_where(row)
    out["targeting_notes"] = (row.get("targeting_notes") or "").strip()
    out["targeting_notes_comment"] = _targeting_notes_comment(row)
    out["custom_joins_sql"] = _rcs_build_custom_joins(row)

    # Scalar defaults — templates reference row.bu_cc_id / fallback_message_body /
    # to_app_store / canonical_campaign_id / priority / theme / campaign_name under
    # StrictUndefined, so any missing key aborts rendering. Fresh rows created via
    # "Add blank row" (before the user opens Optional Fields) may not have these
    # keys, so backfill sensible defaults.
    out.setdefault("bu_cc_id", "")
    out.setdefault("fallback_message_body", "")
    out.setdefault("to_app_store", False)
    out.setdefault("canonical_campaign_id", "")
    out.setdefault("theme", "")
    out.setdefault("campaign_name", "")
    out.setdefault("priority", 1)
    return out


def render_rcs_campaign_insert(env: Environment, tables_cfg: dict, row: dict, send_date: str) -> str:
    """Render a single RCS row's INSERT block for developer preview.

    Mirror of `render_campaign_insert` for PUSH. Used by the per-row SQL Preview
    in the developer view. Uses the same offer-type dispatch and normalization
    as `build_rcs_sql`, so previewed SQL matches what full generation produces.
    """
    from datetime import date as _date

    tables = tables_cfg.get("tables", {}) if isinstance(tables_cfg, dict) else {}
    send_day_upper = _RCS_DAY_ABBR[_date.fromisoformat(send_date).weekday()]
    offer = str(row.get("channelsubtype") or row.get("offer_type") or "").strip().upper()
    tpl_name = _RCS_OFFER_TYPE_FILES.get(offer)
    if not tpl_name:
        raise RuntimeError(
            f"Unknown or missing RCS CHANNEL_SUB_TYPE: {offer!r} (row: {row.get('campaign_name', '?')})"
        )
    norm = _normalize_rcs_row(row)
    return env.get_template(tpl_name).render(row=norm, tables=tables, send_day_upper=send_day_upper)


def build_rcs_sql(env: Environment, tables_cfg: dict, rows: list, wk_id, send_date: str) -> str:
    """Assemble a complete RCS SQL script for a campaign day.

    Args:
        env:         Jinja2 environment loading from rcs/macros/.
        tables_cfg:  Full parsed rcs/config/tables.yaml (contains 'tables' + 'runtime' keys).
        rows:        List of RCS campaign row dicts (each has offer_type, theme, cards, etc.).
        wk_id:       Numeric week ID (e.g. 202633).
        send_date:   ISO date string 'YYYY-MM-DD'.

    Returns: Full RCS SQL script string.
    """
    from datetime import date as _date

    tables = tables_cfg.get("tables", {}) if isinstance(tables_cfg, dict) else {}
    runtime = tables_cfg.get("runtime", {}) if isinstance(tables_cfg, dict) else {}

    send_day_upper = _RCS_DAY_ABBR[_date.fromisoformat(send_date).weekday()]
    target_table = f"{tables.get('rcs_adhoc_base', '')}.{send_day_upper}{tables.get('rcs_adhoc_suffix', '')}"

    try:
        preamble = env.get_template("preamble.sql.j2").render(
            wk_id=wk_id, send_date=send_date, send_day_upper=send_day_upper, tables=tables,
        )
    except Exception as exc:
        raise RuntimeError(f"RCS preamble render failed: {exc}") from exc

    inserts: list[str] = []
    for r in rows:
        # RCS rows store the offer type under 'channelsubtype'; fall back to 'offer_type'
        # for rows saved before the Phase 4a rename.
        offer = str(r.get("channelsubtype") or r.get("offer_type") or "").strip().upper()
        tpl_name = _RCS_OFFER_TYPE_FILES.get(offer)
        if not tpl_name:
            raise RuntimeError(
                f"Unknown or missing RCS offer_type: {offer!r} (row: {r.get('campaign_name', '?')})"
            )
        norm = _normalize_rcs_row(r)
        try:
            block = env.get_template(tpl_name).render(row=norm, tables=tables, send_day_upper=send_day_upper)
        except Exception as exc:
            raise RuntimeError(
                f"RCS {offer} render failed for row '{r.get('campaign_name', '?')}': {exc}"
            ) from exc
        inserts.append(block)

    try:
        finalization = env.get_template("finalization.sql.j2").render(
            target_table=target_table, tables=tables, runtime=runtime,
        )
    except Exception as exc:
        raise RuntimeError(f"RCS finalization render failed: {exc}") from exc

    return "\n\n".join([preamble] + inserts + [finalization])

