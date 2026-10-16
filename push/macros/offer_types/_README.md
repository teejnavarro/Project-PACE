# Offer Type Templates

This folder contains editable Jinja2 SQL templates for each **offer type** used in the PUSH Campaign Builder. Instead of hardcoding the JOIN/WHERE logic in Python, each offer type has its own `.sql.j2` file that `compose.py` loads at render time.

## Files

| File | Offer Type | JOIN Alias | Description |
|------|-----------|------------|-------------|
| `store_coupon.sql.j2` | STORE COUPON | `b` | Joins `coupon_store_validity` for published store coupons |
| `personalized_deal.sql.j2` | PERSONALIZED DEAL | `bb` | Joins `OFFER_ALLOCATION_HISTORY` × `coupon_store_validity` for PD allocations |
| `pushsection.sql.j2` | PUSHSECTION | *(none)* | No JOIN — intentionally empty body |

## File Format

Each file has two parts:

### 1. Metadata Header (Jinja2 comment)

```
{#
  offer_type: STORE COUPON
  where_condition: cast(a.store_id as string) = b.store_id
  reserved_aliases: b
#}
```

| Key | Purpose |
|-----|---------|
| `offer_type` | Display name (must match the UI dropdown value) |
| `where_condition` | SQL fragment appended to the WHERE clause (references the JOIN alias) |
| `reserved_aliases` | Comma-separated aliases (e.g. `b` or `bb`) so custom JOINs don't collide |

### 2. JOIN SQL Body (Jinja2 template)

The SQL below the header is rendered through Jinja2 with these variables:

| Variable | Source |
|----------|--------|
| `{{ tables.coupon_store_validity }}` | Fully-qualified BigQuery table path from `config/tables.yaml` |
| `{{ tables.offer_allocation_history }}` | Fully-qualified BigQuery table path from `config/tables.yaml` |
| `{{ offer_clause }}` | Formatted offer ID filter (e.g. `= '12345'` or `IN ('111','222')`) |

## How to Edit

1. Open the `.sql.j2` file for the offer type you want to change.
2. Modify the JOIN SQL body as needed. Use `{{ tables.xxx }}` for table paths and `{{ offer_clause }}` for the offer ID filter.
3. If you change the JOIN alias, update `reserved_aliases` and `where_condition` in the header to match.
4. Save the file — changes take effect on the next SQL generation (no app restart needed).

## Adding a New Offer Type

1. Create a new file: `macros/offer_types/your_offer_type.sql.j2`
2. Add the metadata header and JOIN SQL body following the format above.
3. In `app/compose.py`, add a mapping entry to `_OFFER_TYPE_FILES` (e.g. `"YOUR OFFER TYPE": "your_offer_type"`).
4. In `app/ui.py`, add the new offer type to the `offer_opts` list in `_render_row_form()`.
