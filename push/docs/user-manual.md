# P·A·C·E — Precision Audience Campaign Engine User Manual

> Portfolio edition for fictional retailer Orchard & Tide. Sample data and database settings are for demonstration only.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Getting Started](#2-getting-started)
3. [Project Structure](#3-project-structure)
4. [Roles & Access Control](#4-roles--access-control)
5. [Dashboard View](#5-dashboard-view)
   - [Status Pipeline](#51-status-pipeline)
   - [Creating a Campaign Day](#52-creating-a-campaign-day)
   - [Campaign Day Table](#53-campaign-day-table)
   - [Filtering & Searching](#54-filtering--searching)
   - [Cloning a Campaign Day](#55-cloning-a-campaign-day)
   - [Deleting a Campaign Day](#56-deleting-a-campaign-day)
6. [Campaign Detail View](#6-campaign-detail-view)
   - [Header Fields](#61-header-fields)
   - [Custom Targeting Instructions (per row)](#62-custom-targeting-instructions-per-row)
   - [Recurring SQL Template Library](#63-recurring-sql-template-library)
   - [Adding & Removing Rows](#64-adding--removing-rows)
   - [Importing Rows from CSV](#65-importing-rows-from-csv)
   - [Editing Campaign Rows](#66-editing-campaign-rows)
   - [Targeting (Division / Banner / Store ID)](#67-targeting-division--banner--store-id)
   - [Offer Type & JOIN Logic](#68-offer-type--join-logic)
   - [Exporting the Grid to CSV](#69-exporting-the-grid-to-csv)
   - [Division + Banner/Store OR Groups](#610-division--bannerstore-or-groups)
   - [Custom JOINs per Row](#611-custom-joins-per-row)
   - [Multiple Themes (Sub-Rows)](#612-multiple-themes-sub-rows)
7. [User Workflow — Submit for Export](#7-user-workflow--submit-for-export)
   - [Pre-Submit Validation](#71-pre-submit-validation)
   - [Save as Pending Assets](#72-save-as-pending-assets)
   - [Submitting](#73-submitting)
   - [Activity Log](#74-activity-log)
8. [Developer Workflow](#8-developer-workflow)
   - [Input Summary](#81-input-summary)
   - [SQL Preview (per row)](#82-sql-preview-per-row)
   - [Pre-Export Validation](#83-pre-export-validation)
   - [Generating SQL](#84-generating-sql)
   - [Export File Naming](#85-export-file-naming)
   - [Checksum & Diff](#86-checksum--diff)
   - [Audit Trail](#87-audit-trail)
   - [SQL Template Editor](#88-sql-template-editor)
   - [Script Editor](#89-script-editor)
   - [Optional Column Schema Editor](#810-optional-column-schema-editor)
9. [Build Time Analytics](#9-build-time-analytics)
   - [Terminology](#91-terminology)
   - [Charts & Metrics](#92-charts--metrics)
   - [Filtering Weeks](#93-filtering-weeks)
   - [Exporting Analytics](#94-exporting-analytics)
10. [Configuration Reference](#10-configuration-reference)
    - [tables.yaml](#101-tablesyaml)
    - [users.yaml](#102-usersyaml)
    - [targeting.yaml](#103-targetingyaml)
    - [campaign_templates.yaml](#104-campaign_templatesyaml)
    - [optional_columns.yaml](#105-optional_columnsyaml)
11. [SQL Template Library — Adding Files](#11-sql-template-library--adding-files)
12. [Column Reference](#12-column-reference)
13. [CRF Converter](#13-crf-converter)
    - [Uploading a CRF File](#131-uploading-a-crf-file)
    - [Expected Columns](#132-expected-columns)
    - [Parsed Output Preview](#133-parsed-output-preview)
    - [Downloading the CSV](#134-downloading-the-csv)
    - [Injecting Directly into a Campaign Day](#135-injecting-directly-into-a-campaign-day)
    - [Parser Rules Reference](#136-parser-rules-reference)
14. [Development Notes](#14-development-notes)

---

## 1. Overview

**P·A·C·E — Precision Audience Campaign Engine** helps fictional grocery retailer Orchard & Tide coordinate campaign requests, audience rules, message content, review, and script export. It supports mobile push notifications and richer RCS messages.

**Channel selection at launch:**

When the app opens (or after clicking **← Back to landing** in the sidebar), a **landing page** is shown with two large buttons:

| Button | Channel | Purpose |
|---|---|---|
| **📱 PUSH** | Mobile app push notifications | This manual |
| **💬 RCS** | Rich messaging | Card-based and carousel messages |

The selected channel is remembered for the browser session. To switch, use the **PUSH / RCS** toggle buttons in the sidebar, or click **← Back to landing** to return to the picker.

A small **channel badge** (icon + label pill) is shown next to the Dashboard header, next to the Analytics header, and inline in every sidebar breadcrumb so the active channel is always visible.

The app uses a **two-view, single-page layout**:

| View | Purpose |
|---|---|
| **Dashboard** | List all campaign days, track status, create/clone/delete campaigns |
| **Campaign Detail** | Edit campaign rows, configure targeting, submit or export SQL |

**Role-based access** separates User and Developer capabilities via two sidebar toggle buttons (**👤 User** / **🔧 Developer**). Users build campaign rows and submit for export; Developers review, generate SQL, and download the final `.sql` file.

---

## 2. Getting Started

### Prerequisites
- Python 3.10+
- Virtual environment (`.venv/`)

### Installation

```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### Running the App

From the project folder, start the local demo with:

```powershell
streamlit run app/streamlit_app.py
```

Open **http://localhost:8501** in a browser. The demo Developer passphrase is `demo`.

> **Note:** Only one person should edit a given campaign day at a time. The app saves campaign data as JSON files; simultaneous edits to the same campaign can cause data loss (last save wins).

---

## 3. Project Structure

The workspace is organized into **per-channel** subtrees (`push/`, `rcs/`) with a small set of shared assets at the root. Channel routing is driven by `app/storage.py::_CHANNEL_BASES` + `set_active_channel()` + `channel_dir(subfolder)`.

| Path | Scope | Purpose |
|---|---|---|
| `app/ui.py` | **Shared** | Streamlit UI (entry point) — channel-aware |
| `app/compose.py` | **Shared** | SQL composition — `build_sql()` for PUSH, `build_rcs_sql()` for RCS |
| `app/renderer.py` | **Shared** | Jinja2 environment |
| `app/storage.py` | **Shared** | JSON persistence + channel routing (`_CHANNEL_BASES`, `channel_dir()`) |
| `app/audit.py` | **Shared** | Change diff & logging |
| `config/users.yaml` | **Shared** | Developer passphrase (SHA-256) |
| `reference_data/banners.txt` | **Shared** | Valid banner names (one per line, lowercase) |
| `tests/` | **Shared** | Unit tests (`test_compose.py`, `test_rcs_compose.py`, paste/CSV suites) |
| `push/config/*.yaml` | **[PUSH]** | tables, targeting, campaign_templates, emojis, optional_columns |
| `push/config/optional_columns.yaml` | **[PUSH]** | Single source of truth for PUSH optional INSERT columns |
| `push/macros/*.sql.j2` | **[PUSH]** | Jinja2 SQL templates (preamble, campaign_insert, finalization, offer_types) |
| `push/extras/finalization_static_tail.sql` | **[PUSH]** | Static counts/QC/archive tail |
| `push/sql_templates/*.sql` | **[PUSH]** | Pre-built recurring `.sql` files |
| `push/data/*.json` | **[PUSH]** | Persisted PUSH campaign day JSON files |
| `push/exports/` | **[PUSH]** | UTF-8 BOM CSV grid exports |
| `push/sql_exports/` | **[PUSH]** | Generated `.sql` files (Developer downloads) |
| `push/Features/campaign-builder-features.md` | **[PUSH]** | Comprehensive end-user feature guide |
| `push/docs/user-manual.md` | **[PUSH]** | This document |
| `rcs/config/*.yaml` | **[RCS]** | fictional table settings and optional columns |
| `rcs/macros/**` | **[RCS]** | RCS Jinja2 templates for message types and finalization |
| `rcs/data/*.json` | **[RCS]** | Persisted RCS campaign day JSON files |
| `rcs/exports/` / `rcs/sql_exports/` | **[RCS]** | RCS CSV + SQL exports |
| `README.md` | — | Portfolio overview and local setup |

> **Legacy compatibility:** JSON files persisted before the `push/` file migration remain readable — `_load_into_session()` normalizes field defaults on load.

---

## 4. Roles & Access Control

The sidebar contains two side-by-side toggle buttons: **👤 User** and **🔧 Developer**. The active role is highlighted in green (primary style); the inactive role appears as a blue outline (secondary style).

| Role | Capabilities |
|---|---|
| **User** | Create/edit campaigns, add/remove rows, configure targeting, submit for export. Cannot generate SQL, download files, view audit trail, or delete campaign days. |
| **Developer** | Everything a User can do, plus: Input Summary, SQL Preview per row, pre-export validation, SQL generation, download, audit trail, Script Editor (in-app editing of core SQL/Jinja2 templates and `banners.txt`), Optional Column Schema Editor (add new optional INSERT columns via UI), Build Time Analytics, delete campaign days, set "Exported" status, and view the active session counter in the sidebar. |

**Switching roles:**
- Clicking **👤 User** always switches immediately — no credential required.
- Clicking **🔧 Developer** shows a **passphrase prompt** in the sidebar if not yet unlocked. Enter the correct passphrase and click **Unlock** to gain Developer access for the session. Click **Cancel** to abort.
- Once unlocked, the Developer role stays active for the rest of the browser session. Switching back to User and then back to Developer does not require re-entering the passphrase within the same session.

> **Demo passphrase:** `demo`. For local experimentation, set `PACE_DEV_PASSPHRASE_SHA256` to a hash you generate yourself:
> ```powershell
> python -c "import hashlib; print(hashlib.sha256(b'NEW_PASSPHRASE').hexdigest())"
> ```

---

## 5. Dashboard View

The Dashboard is the landing page. It lists all campaign days in a table format with status tracking.

### 5.1 Status Pipeline

Each campaign day progresses through a 7-stage pipeline:

| Stage | Color | Meaning |
|---|---|---|
| **Draft** | Grey | Newly created, not yet started |
| **Pending Assets** | Red | Saved with incomplete assets (title, media, etc.) |
| **In Progress** | Orange | User is actively editing |
| **Ready** | Green | User has finished, awaiting review |
| **Submitted** | Blue | User has submitted for export |
| **Exported** | Purple | Developer has generated and downloaded the SQL |
| **Campaign Launched** | Dark Green | Send date has passed 8 AM PST — campaign has gone live |

Status can be changed inline via the dropdown in each campaign row. Users cannot set "Exported" or "Campaign Launched" — these are controlled by Developers and automated logic respectively.

> **Auto-transition to "Campaign Launched":** Once the campaign's send date is reached and the clock passes **8:00 AM Pacific Time (PST/PDT)**, the status automatically switches to "Campaign Launched" the next time the dashboard is viewed. This transition is irreversible via the selectbox (the status is always preserved even when viewed as a User).

### 5.2 Creating a Campaign Day

1. Expand **"➕ Create New Campaign Day"**
2. Enter the **Week ID** (e.g. `202609`) and pick a **Send Date**
3. Click **"Create Campaign Day"**
4. The campaign appears in the table with "Draft" status

Each campaign is persisted as an individual JSON file in `data/`.

> **Duplicate prevention** — If a campaign day with the same Week ID and Send Date already exists, an error is shown listing the existing entry's status. Open the existing campaign instead of creating a duplicate.

### 5.3 Campaign Day Table

Each row in the dashboard table displays:

| Column | Description |
|---|---|
| **#** | Row number |
| **Send Date** | Formatted send date |
| **Send Day** | Day of week (auto-derived) |
| **Week ID** | Year + week number |
| **Rows** | Number of campaign rows in this day |
| **Last Modified** | Timestamp of last save |
| **Status** | Dropdown to change status |
| **Open** | Button to open the campaign detail editor |
| **📋** | Clone button (duplicate this campaign day) |
| **🗑️** | Delete button (Developer only, with confirmation) |

A **status summary strip** at the top shows counts per status (e.g. "2 Draft · 1 In Progress · 3 Ready").

### 5.4 Filtering & Searching

Use the **"Filter by status"** multiselect above the table to show only campaign days matching the selected statuses. Leave blank to show all.

### 5.5 Cloning a Campaign Day

Click the **📋** button on any campaign row to create a duplicate. The clone:
- Gets a new unique ID
- Resets to "Draft" status
- Copies all rows (including per-row targeting instructions) and header fields
- Clears the audit trail

### 5.6 Deleting a Campaign Day

**Developer only.** Click **🗑️** on a campaign row. A confirmation prompt appears:
- Click **"Yes, delete"** to permanently remove the campaign day JSON file
- Click **"Cancel"** to abort

---

## 6. Campaign Detail View

Click **"Open"** on a campaign day in the dashboard to enter the detail editor. Click **"← Dashboard"** to save and return.

### 6.1 Header Fields

| Field | Description | Example |
|---|---|---|
| **Week ID (YYYYWW)** | Year + ISO week number | `202609` |
| **Send Date** | Date picker for the campaign send date | `2026-02-27` |
| **Send Day** | Auto-derived from Send Date (read-only) | `FRIDAY` |

A **💾 Last saved** timestamp appears below the header fields, showing when the campaign was last persisted.

### 6.2 Custom Targeting Instructions (per row)

> Consolidated into each row’s expander under **📝 Targeting notes** (see Section 6.6). Stored in `targeting_notes`; emitted as `/* ... */` SQL comment blocks below the campaign title header. Developer Input Summary lists all rows with instructions.

### 6.3 Recurring SQL Template Library

Use **"Load from Recurring SQL Template Library"** to inject pre-built `.sql` files as custom rows:

1. Expand the section
2. Select SQL templates from the multiselect
3. Click **"Add selected SQL templates"**
4. SQL template rows appear in the **unified data editor** alongside form-based rows
5. SQL template rows have `row_type = sql`; all metadata columns (campaign_name, theme, message, title, etc.) are editable — values feed Jinja2 placeholder substitution at export time

You can also **upload new `.sql` files** directly via the file uploader in this section.

#### Jinja2 Placeholder Substitution

SQL template `.sql` files can contain **Jinja2 placeholders** like `{{ theme }}`, `{{ message }}`, `{{ title }}`, etc. At export time, these placeholders are automatically replaced with the values entered in the row’s metadata columns.

Available placeholders include all row-level fields (e.g. `{{ campaign_name }}`, `{{ theme }}`, `{{ message }}`, `{{ title }}`, `{{ pushsection }}`) plus campaign-level fields (`{{ wk_id }}`, `{{ send_date }}`) and BigQuery table paths from `tables.yaml`.

**Numbered offer ID placeholders** — when `offer_id` contains multiple comma-separated IDs, the following additional variables are automatically generated at render time:

| Variable | Description | Example (`offer_id = A,B,C,D`) |
|---|---|---|
| `{{ offer_id_1 }}` | First offer ID | `A` |
| `{{ offer_id_2 }}` | Second offer ID | `B` |
| `{{ offer_id_N }}` | Nth offer ID | `D` (for N=4) |
| `{{ offer_id_list }}` | All IDs as a SQL-ready quoted list | `'A','B','C','D'` |

Use `{{ offer_id_list }}` in `IN` clauses and `{{ offer_id_1 }}` / `{{ offer_id_2 }}` etc. for per-offer logic like CASE statements. If a template references `{{ offer_id_3 }}` but fewer than 3 IDs are entered, a caption warning appears in the UI.

Unfilled placeholders (where the corresponding field is empty) resolve to an empty string. Pre-export validation flags rows that still contain unfilled `{{ var }}` tokens.

#### In-Row SQL Template Picker

Every row expander contains a **"🗄️ SQL Template"** selectbox at the bottom of the form. This lets you assign (or change) a template on any row, including blank form rows, without using the top multiselect:

1. Open the row expander
2. Choose a template from the **"🗄️ SQL Template"** dropdown — the template SQL is copied into `custom_sql` and the row becomes `row_type = sql`
3. Select **"— None —"** to clear the template and revert the row to standard form-row INSERT generation

The picker pre-selects the currently assigned template on every re-render. If a template file is deleted from disk after assignment, the missing name is appended to the options list so no silent auto-clear occurs.

> **Intended CSV roundtrip workflow:** Fill row metadata (theme, message, title, etc.) in Excel → import CSV → open each row and select the appropriate template → generate SQL (Jinja2 substitutes row field values into the template at export).

#### Reload SQL from Library

If a SQL template file is edited on disk (e.g. via the in-app template editor), click **"🔄 Reload SQL from library"** to refresh the `custom_sql` for all existing SQL template rows from disk. The button matches by `sql_template_name` first, falling back to `campaign_name` for legacy rows, and backfills `sql_template_name` on refresh.

> **Note:** Campaign templates defined in `config/campaign_templates.yaml` are retained for reference but no longer loaded via the UI.

### 6.4 Adding & Removing Rows

Two buttons appear side by side:

| Action | How |
|---|---|
| **Add blank row** | Click "Add blank row" — inserts an empty form row at the next priority |
| **Remove a row** | Select the row from the dropdown, click "Remove selected row", then confirm in the prompt |

Priorities are auto-renumbered after removal. **Row removal requires confirmation** — a warning prompt appears with "Yes, remove" and "Cancel" buttons.

### 6.5 Importing Rows from CSV

A **"📤 Import CSV"** file uploader appears directly below the Add/Remove buttons and is always visible, even when the grid has no rows.

**Steps:**
1. Click **"Browse files"** and select a CSV file (exported grid format, UTF-8 with or without BOM)
2. Click **"📤 Import rows from CSV"** to confirm the import

**Behaviour:**
- **Empty or blank grid** — any rows where `campaign_name`, `theme`, `message`, and `custom_sql` are all empty are cleared first; the CSV rows replace them starting at priority 1
- **Grid with existing data** — imported rows are appended after existing rows with auto-numbered priorities
- **Duplicate prevention** — importing the same file a second time shows "This file has already been imported" and is skipped

> **Tip:** The exported CSV format (`PUSH_Wk{WW}_{Day}_grid.csv`) is the standard import format. All columns are preserved, including emojis in title and message fields.

### 6.6 Editing Campaign Rows

Each campaign row is displayed as an individual **collapsible expander** labeled with the row's priority, campaign name (or theme), and row type (`[form]` or `[sql]`). Open an expander to edit that row's fields — all sections for that row are self-contained.

#### Top Strip
Each row expander starts with a 4-column header row:

| Field | Description |
|---|---|
| **Priority** | Editable number; type a new value then click "Sort by priority" to reorder |
| **Row Type** | Read-only; `form` (generated SQL) or `sql` (from template library) |
| **Offer Type** | Dropdown: blank / `PERSONALIZED DEAL` / `STORE COUPON` / `PUSHSECTION` |
| **Offer ID** | Single or comma-separated offer IDs |

#### Required Fields
Three text inputs displayed in a row: **campaign_name \***, **title \***, **message \***.

#### 🎯 Theme Variants
A separate section immediately below Required Fields containing the **theme \*** input. Theme is still required for all form rows before submitting.

For **SQL template rows**, the section automatically scans the assigned template SQL for `{{ theme_1 }}`, `{{ theme_2 }}`, etc. and renders the corresponding required input boxes inline (horizontal) next to the main `theme` field. The number of boxes matches exactly how many `theme_N` placeholders appear in the template. A caption warning appears beneath any that are left blank.

#### Rich Push Image
A checkbox between Required Fields and Optional Fields. When checked, `media_url` is required for this row — an inline warning appears inside the Optional Fields expander if `media_url` is left blank.

#### 📎 Optional Fields
A collapsed sub-expander containing all 17 optional columns (media_url, pushsection, param_q, screentitle, subtitle, gameid, product, searchterm, store, seller, category, program, pagname, datasource, modelconfigid, partnerid, autoimage) laid out in rows of 3.

**Inline field guards inside Optional Fields:**
- **`param_q`** — warns if the value contains an underscore (`_`)
- **`screentitle`** — warns if the value contains a dash (`-`)
- **`pushsection`** — warns if blank when the row's Offer Type is `PUSHSECTION`
- **`media_url`** — warns if blank when the **Rich Push Image** checkbox is checked

#### 🎯 Targeting
A collapsed sub-expander with flat targeting fields (division_ids, banners, store_ids each with an INCLUDE/EXCLUDE mode dropdown) plus the Division + Banner/Store OR groups controls (see Section 6.10).

#### 📝 Targeting Notes
A collapsed sub-expander with a free-text area for custom targeting instructions for the Developer (see Section 6.2).

#### 🔗 Custom JOINs
A collapsed sub-expander for adding structured or free-text JOIN clauses to this row (see Section 6.11).

#### 🗄️ SQL Template
A selectbox listing all `.sql` files from `sql_templates/`, plus a **"— None —"** option. Selecting a template assigns it to this row (copies SQL into `custom_sql`, sets `row_type = sql`). Selecting "— None —" reverts to standard form-row INSERT generation. See [§6.3](#63-recurring-sql-template-library) for the in-row picker workflow.

#### 🗄️ SQL Template Source *(SQL rows only)*
A collapsed sub-expander showing the raw `custom_sql` for the row (read-only).

**General behaviour:**
- All edits are **auto-saved** on every interaction
- Form rows and SQL template rows share the same expander layout — all metadata columns are editable for SQL rows (values feed Jinja2 placeholder substitution at export time)
- Click **"Sort by priority"** to reorder all row expanders by priority number

### 6.7 Targeting (Division / Banner / Store ID)

Each row supports optional targeting via three dimensions, each with an `IN` or `NOT IN` mode:

| Column | Format | SQL Output |
|---|---|---|
| `division_ids` | Comma-separated numbers | `WHERE a.division_id IN (19,20)` |
| `banners` | **Multiselect dropdown** (see below) | `WHERE a.store_banner IN ('pine_and_peak','cedar_market')` |
| `store_ids` | Comma-separated numbers | `WHERE a.store_id IN (1,2,3)` |

**Mode selectors** toggle between `INCLUDE` (SQL: `IN`) and `EXCLUDE` (SQL: `NOT IN`). The friendly labels are display-only — the generated SQL always uses standard `IN` / `NOT IN` syntax.

**Banners multiselect:** The Banners field is a **clickable dropdown multiselect** populated from `reference_data/banners.txt`. Select one or more banners from the list rather than typing them manually. Selected banners appear as chips and can be removed individually. If `banners.txt` is not found, the field falls back to a plain text input.

**Paste a store list:** Directly below the Store IDs field, a **"📋 Paste a store list"** expander lets you paste a vertical column of store numbers copied from an Excel file — no manual reformatting needed. Paste the column (with or without a header row), preview the parsed IDs, then click **Replace Store IDs** or **Append to Store IDs**.

- Non-numeric tokens (column headers, banner names, stray text) are safely ignored and listed in a warning caption
- Duplicate store IDs are silently removed
- **Replace Store IDs** overwrites the current field; **Append to Store IDs** merges the new list with existing IDs, removing duplicates
- A success message confirms how many store IDs were injected
- No practical limit — supports 2,000+ store IDs without issue

Multiple dimensions are combined with `AND`:
```sql
WHERE a.division_id IN (19,20)
  AND a.store_banner IN ('cedar_market','pine_and_peak')
  AND a.store_id NOT IN (1,2,3)
```

> **Note:** Banner values are always **lowercased** in the generated SQL output.

### 6.8 Offer Type & JOIN Logic

Each row supports an optional **Offer Type** to generate JOIN clauses in the SQL:

| Column | Values | Description |
|---|---|---|
| `offer_type` | `PERSONALIZED DEAL`, `STORE COUPON`, `PUSHSECTION`, or blank | Selects the JOIN pattern |
| `offer_id` | Single or comma-separated IDs | Offer identifiers for the WHERE clause |

**PERSONALIZED DEAL** generates:
```sql
JOIN OFFER_ALLOCATION_HISTORY × coupon_store_validity ON household_id + offer_id
```

**STORE COUPON** generates:
```sql
JOIN coupon_store_validity ON store_id
```

**PUSHSECTION or blank (no offer type)** — no JOIN is generated:
```sql
,'' AS pushoffertype
,NULL AS pushofferid
```

> **Warning:** Leaving `offer_type` blank produces the same output as PUSHSECTION (`pushoffertype = ''`, `pushofferid = NULL`). The Developer pre-export validation will flag these rows with an advisory warning. Always set an explicit offer type when offer data is required.

**Multiple offer IDs** (comma-separated) produce an `IN` clause:
```sql
WHERE b.offer_id IN ('12345','67890')
```

**Jinja2 variables for SQL template rows** — when a SQL template row has multiple comma-separated offer IDs, the following variables are available inside the `.sql` template file:

| Variable | Description | Example (`offer_id = A,B,C,D`) |
|---|---|---|
| `{{ offer_id }}` | Raw comma-separated string (unchanged) | `A,B,C,D` |
| `{{ offer_id_1 }}` | First offer ID | `A` |
| `{{ offer_id_2 }}` | Second offer ID | `B` |
| `{{ offer_id_N }}` | Nth offer ID | `D` (for N=4) |
| `{{ offer_id_list }}` | SQL-ready quoted list for `IN` clauses | `'A','B','C','D'` |

Example template usage:
```sql
-- IN clause (any number of IDs):
AND a.req_id IN ({{ offer_id_list }})

-- Per-offer CASE statement:
CASE
  WHEN req_id = '{{ offer_id_1 }}' THEN '6'
  WHEN req_id = '{{ offer_id_2 }}' THEN '8'
END
```

Offer WHERE conditions are combined with targeting WHERE conditions via `AND`.

### 6.9 Exporting the Grid to CSV

After adding rows, click **"📥 Export Grid to CSV"** (below the data editor) to save the grid as a CSV file.

- The file is saved to **`exports/PUSH_Wk{WW}_{Day}_grid.csv`** in the project folder
- Encoded as **UTF-8 with BOM** — emojis (🎉 🍷 🔥 etc.) render correctly when opened in Excel
- All visible columns are included: priority, `row_type`, `rich_push_image` (exported as **Y** or **N**), offer fields, required/optional/targeting columns
- A success message confirms the save location
- **Numeric-text columns protected:** `store_ids`, `division_ids`, and `offer_id` are wrapped as `="value"` formula literals in the CSV. Excel displays them as plain text (no scientific-notation or precision loss). The import step strips this wrapper automatically.

> **`rich_push_image` roundtrip:** On CSV re-import, a value of `Y` (case-insensitive) restores the checkbox to checked; any other value defaults to unchecked.

> **Multi-theme containers:** On export, containers are flattened — each sub-row becomes its own row with the parent's priority. On re-import, rows sharing the same priority are automatically re-grouped into a multi-theme container. If grouping was unintentional, use **"↔ Split into separate rows"** inside the container.

> **Note:** The file uploader in [section 6.5](#65-importing-rows-from-csv) accepts this exact format for round-trip import.

### 6.10 Division + Banner/Store OR Groups

The **"🔗 Division + Banner/Store OR groups"** section (now inside each row's **🎯 Targeting** sub-expander — see Section 6.6) lets you build compound OR-based targeting conditions that combine `division_id`, `store_banner`, and `store_id` filters within the same row.

This is distinct from the flat targeting columns in Section 6.7: flat columns always combine with `AND`; OR groups let you express logic like *"(division 29 AND cedar_market/blueharbor) OR (division 33 AND redwood_fresh)"*.

#### Adding an OR Group

1. Expand **"🔗 Division + Banner/Store OR groups"**
2. Find the row you want to configure (rows are listed one per expander)
3. Click **"＋ Add OR group"** — a new group row appears with 6 editable fields:

| Field | Description |
|---|---|
| **Division IDs** | Comma-separated numbers (e.g. `29,30`) |
| **Div mode** | `INCLUDE` or `EXCLUDE` (maps to SQL `IN` / `NOT IN`) |
| **Banners** | **Multiselect dropdown** — pick from the list in `reference_data/banners.txt` (always lowercased in SQL) |
| **Banner mode** | `INCLUDE` or `EXCLUDE` (maps to SQL `IN` / `NOT IN`) |
| **Store IDs** | Comma-separated numbers (e.g. `1004,2051`) |
| **Store mode** | `INCLUDE` or `EXCLUDE` (maps to SQL `IN` / `NOT IN`) |

4. Repeat to add more groups — each group is combined with `OR`
5. Click **✕** on any group to remove it

#### SQL Output

Each group's active fields are combined with `AND`; multiple groups are combined with `OR`. Each individual group is wrapped in its own parentheses, and the entire compound clause is wrapped in an outer set — ensuring correct `AND`/`OR` precedence:

```sql
AND (
      (a.division_id IN (29) AND a.store_banner IN ('cedar_market','coastwise','blueharbor'))
   OR (a.division_id IN (33) AND a.store_banner IN ('redwood_fresh','meadowlane'))
)
```

A group with all fields blank contributes no SQL. Fields left empty within a group are simply omitted from that group's clause.

OR groups are appended to the regular targeting conditions from Section 6.7 via `AND`:

```sql
WHERE a.division_id IN (19,20)     -- from flat targeting columns (Section 6.7)
  AND (                             -- from OR groups
        (a.division_id IN (29) AND a.store_banner IN ('cedar_market','blueharbor'))
     OR (a.division_id IN (33) AND a.store_banner IN ('redwood_fresh'))
  )
```

#### Storage & CSV Roundtrip

OR groups are stored as `div_banner_groups` (a JSON list) inside each row's data. In the data editor grid the column is **read-only** (disabled) and shows the JSON representation — use the expander to edit, not the grid cell.

When exporting the grid to CSV (Section 6.9), `div_banner_groups` is serialized as a JSON string in the CSV. When importing that CSV back (Section 6.5), the column is automatically parsed back into the structured list. Rows missing the column default to an empty list.

---

### 6.11 Custom JOINs per Row

The **"🔗 Custom JOINs"** section (now inside each row's **🔗 Custom JOINs** sub-expander — see Section 6.6) lets you add custom JOIN clauses to each row's SQL. JOINs are injected after the `FROM` clause and before the `WHERE` clause.

Each JOIN entry supports two modes:

#### Structured
Filled-in form fields that auto-generate the JOIN SQL:

| Field | Description |
|---|---|
| **Type** | `JOIN`, `LEFT JOIN`, `INNER JOIN`, or `CROSS JOIN` |
| **Table path** | Fully-qualified BigQuery table (e.g. `project.dataset.my_table`) |
| **Alias** | Table alias (e.g. `b`, `c`) |
| **ON clause** | Join condition (e.g. `a.household_id = b.household_id`) |

#### Free Text
A text area where you paste raw SQL exactly as it should appear in the output. Whatever you enter is injected verbatim — useful for complex multi-line JOINs.

```sql
JOIN project.dataset.exclusion_list d
  ON a.store_id = d.store_id
WHERE d.exclude_flag = TRUE
```

#### Adding JOINs
- Click **"＋ Add structured JOIN"** — opens a new entry in Structured mode
- Click **"＋ Add free-text JOIN"** — opens a new entry in Free text mode
- Click **✕** to remove a JOIN

The **Mode** dropdown on each entry lets you switch between Structured and Free text after creation.

#### SQL Output
JOINs appear in the generated SQL after the existing offer-type JOIN (PD/CC) and before the WHERE clause:

```sql
FROM orchard-demo.audience.eligible_push_audience a
JOIN project.dataset.my_table b
  ON a.household_id = b.household_id
LEFT JOIN project.dataset.exclusions d
  ON a.store_id = d.store_id
WHERE ...
```

#### Storage & CSV Roundtrip
`custom_joins` is stored as a JSON list inside each row's data. The grid column is read-only (disabled) — use the expander to edit. CSV export serializes as JSON string; import parses it back.

---

### 6.12 Multiple Themes — Multi Theme Campaign (Sub-Rows)

The **Multi Theme Campaign** feature converts a standard form row into a **multi-theme container** — a grouping of sub-rows that all share the same priority. Each sub-row generates its own full INSERT block in the SQL export.

**Use case:** Multiple audience segments (different divisions, banners, offer IDs) that belong to the same priority slot and should be built and reviewed together.

#### Enabling Multi Theme Campaign

1. Open a form row expander
2. Check **"Multi Theme Campaign"** at the top of the form
   - If the row already has data filled in, a confirmation dialog appears before clearing the form fields
3. The row converts to a **container** showing only Priority and Campaign Name (group label)

> **Only available on form rows.** SQL template rows (`sql` type) cannot be multi-theme containers.

#### Creating Sub-Rows

Inside the container:
1. Set the count in the **"Sub-rows to create"** number input
2. Click **＋ Create Sub-Rows**

Sub-rows appear as nested expanders labeled **`Row {priority}.{n}: {campaign_name}`** (e.g. `Row 3.1: Summer Sale`).

#### Sub-Row Form Layout

Each sub-row expander contains a full form identical to a standard form row:

| Section | Contents |
|---|---|
| **Top strip** | Row Type (read-only: `form`), Offer Type, Offer ID |
| **Required Fields** | `campaign_name *`, `title *`, `message *` (3-column row) |
| **🎯 Theme Variants** | `theme *` field in its own section below Required Fields |
| **Rich Push Image** | Checkbox + inline `media_url` warning |
| **📎 Optional Fields** | All 17 optional columns with inline guards + **Paste deep-link params** parser |
| **🎯 Targeting** | Division IDs, Banners, Store IDs (INCLUDE/EXCLUDE) + OR Groups (§6.10) |
| **📝 Targeting Notes** | Free-text targeting instructions → emitted as `/* ... */` SQL comment |
| **🔗 Custom JOINs** | Structured or free-text JOIN clauses (§6.11) |

**Paste deep-link params** is available in every sub-row’s **📎 Optional fields** expander — paste a `key=value` block (e.g. `pushsection=deals\nparam_q=summer/sale`) to auto-fill optional fields across the sub-row.

#### Removing a Sub-Row

Click the red **✕ Remove Sub-Row N.n** button inside the sub-row expander. Confirm in the dialog.

#### Disabling Multi Theme Campaign

Uncheck **"Multi Theme Campaign"** — a confirmation dialog warns that all sub-rows will be deleted before reverting the row to a normal empty form row.

#### Splitting a Container Back Into Separate Rows

Click **"↔ Split into separate rows"** (appears below the sub-row creation controls when sub-rows exist). A confirmation dialog shows how many sub-rows will be promoted. On confirm:

- Each sub-row becomes its own standalone form row
- The multi-theme container is removed
- All priorities are renumbered sequentially from that position

This is fully reversible — if the split was accidental, re-enable **Multi Theme Campaign** on one of the rows and move the others in as sub-rows manually. The split button is also the recovery path when rows are accidentally auto-grouped during CSV import.

#### SQL Output

Each sub-row generates an independent INSERT block. All sub-rows share the **parent container's priority number**.

**Priority table entries:**
```sql
INSERT INTO push_priority (priority, theme) VALUES
(3, 'Wk16_Mon_Sale_Div29'),
(3, 'Wk16_Mon_Sale_Blueharbor');
```

#### CSV Export/Import Behavior

| Item | Behavior |
|---|---|
| **Container row** | Not exported — has no form data |
| **Sub-rows** | Exported as flat rows inheriting the parent's priority |
| **CSV import** | Rows sharing the same priority are **automatically grouped** into a multi-theme container on import (container structure is restored) |

#### Pre-QC Validation

`_run_preqc()` flattens multi-theme containers into their sub-rows before running all checks. Error messages use decimal labels (e.g. `Row 3.1 (Summer Sale): missing theme`). Duplicate-priority warnings are suppressed for sub-rows since sharing a priority is intentional.

#### SQL Preview (Developer)

In the SQL Preview section, a multi-theme container appears as a grouped expander. Each sub-row's rendered INSERT SQL is shown in its own editable text area with an independent **Reset to generated** button.

---

## 7. User Workflow — Submit for Export

When viewing as **User**, section 2 of the detail view shows **"Submit for Export"**.

### 7.1 Pre-Submit Validation

Before submission, the app automatically checks all form rows (non-SQL) for required fields:

- `campaign_name`, `theme`, `message`, `title`

Fields like `media_url`, `pushsection`, `param_q`, and `screentitle` are optional and do not block submission.

If required fields are missing, an expandable warning panel lists the issues:

> ⚠️ 1 validation issue(s)
> - Row 3 (empty): missing **campaign_name, theme, message**

Clicking **"Submit for Export"** with outstanding validation issues shows an error. Fix all issues first, then submit.

In addition to required-field blockers, the User view also displays the full pre-QC advisory scorecard — including content warnings (apostrophes, `[Banner]` placeholders, whitespace), title/message swap detection, banner spelling, and theme mismatch. These are advisory and do not block submission, but should be reviewed before clicking Submit.

> **Note:** The Pre-QC scorecard shows only blockers and advisory warnings. A summary of passed checks is not displayed.

### 7.2 Save as Pending Assets

If a campaign is incomplete (e.g. awaiting creative assets like titles or media URLs), click **"💾 Save as Pending Assets"** to:
- Set status to **Pending Assets**
- Save the campaign to disk
- Redirect back to the dashboard

This lets you come back later to finish the campaign.

### 7.3 Submitting

On successful submission:
- Status changes to **Submitted**
- A confirmation message appears: "Campaign day has been submitted for export!"
- You are automatically redirected back to the dashboard

### 7.4 Activity Log

The User view displays a collapsible **"📝 Activity Log"** expander showing a reverse-chronological list of lifecycle events for the campaign day:

| Event | When it is recorded |
|---|---|
| **Created** | When a new campaign day is created |
| **Created (cloned)** | When a campaign day is duplicated from another |
| **Opened** | Each time the campaign is opened from the dashboard |
| **Saved** | When "Save as Pending Assets" is clicked, or when navigating back to the dashboard |
| **Submitted for Export** | When "Submit for Export" is clicked |

Example:
```
Saved — Mar 03, 10:45 AM
Opened — Mar 03, 10:30 AM
Created — Mar 03, 09:15 AM
```

The activity log is stored as `activity_log` in the campaign JSON and is separate from the `status_history` (which tracks status pipeline transitions). Older campaign days without an `activity_log` will display "No activity recorded yet."

---

## 8. Developer Workflow

When viewing as **Developer**, the detail view shows additional sections after the row editor.

> **Active session counter:** While in Developer mode, the sidebar displays `🟢 N active session(s)` below the breadcrumb, showing the number of browser sessions currently connected to the app. Updates on every page interaction.

> **PST clock:** The sidebar always displays the current Pacific Time (🕐 HH:MM AM/PM · Mon DD, YYYY) above the breadcrumb, visible to all roles. Used to quickly verify whether the 8 AM launch threshold has been crossed.

### 8.1 Input Summary

Section **"Input Summary"** provides:

- **Targeting Instructions** — If any rows have custom targeting instructions, a collapsible panel lists them with the row number, campaign name, and full text
- **Summary table** — A read-only dataframe showing key columns for all rows (priority, campaign_name, theme, offer_type, targeting fields, etc.)
- **Quick stats** — Four metric cards:
  - Total Rows
  - Form / SQL count
  - With Targeting (rows using division/banner/store filters)
  - With Offer JOIN (rows using PD/CC offer type)

### 8.2 SQL Preview (per row)

Section **"SQL Preview"** shows collapsible expanders for each campaign row:

- **Form rows** — Renders the full INSERT SQL using the Jinja2 template, exactly as it will appear in the final export. Useful for validating individual rows before generating the full script.
- **SQL template rows** — Shows the SQL content rendered through Jinja2 with all placeholder substitutions applied.

Each expander is labeled with the row number, campaign name, and row type (`[form]` or `[sql]`).

**Editable preview:** The SQL for each row is displayed in an editable text area. You can modify the SQL directly — edits are stored as overrides and used verbatim in the final export (marked `(edited)` in the SQL comment header). Click **"Reset to generated"** on any row to discard your override and revert to the auto-generated SQL. Modified rows show a "✏️ Modified" indicator.

### 8.3 Pre-Export Validation

Section **"Review & Export"** includes automatic validation warnings:

| Check | Applies to | Warning |
|---|---|---|
| Missing `campaign_name`, `theme`, `message`, or `title` | Form rows only | "Row N: missing **campaign_name**" |
| Duplicate priorities | **All rows** (form + SQL template) | "Row N: duplicate priority **3**" |
| Duplicate themes | **All rows** (form + SQL template) | "Row N: duplicate theme **'my_theme'**" |
| No offer type set | Form rows only | "Row N: no offer type set — `pushoffertype` and `pushofferid` will be **NULL / empty**" |
| Theme missing `pn_wkNN_YYYY_Day` tracking token | **All rows** (form + SQL template) | "theme is missing the `pn_wkNN_YYYY_Day` tracking token" |
| Theme token week number mismatch | **All rows** (form + SQL template) | "theme token week number **33** does not match campaign Week ID **34**" |
| Theme token year mismatch | **All rows** (form + SQL template) | "theme token year **2025** does not match expected **2026**" |
| Theme token send day mismatch | **All rows** (form + SQL template) | "theme token day **Mon** does not match send day **Wednesday**" |
| Title longer than message, or abnormal length ratio | **All rows** (form + SQL template) | "title (108 chars) is **longer** than message (26 chars) — these fields may be swapped (avg title ~26, avg message ~95)" |

Warnings are displayed in an expandable panel. They are advisory — you can still generate SQL with warnings present.

> **Passed checks are not shown.** Only warnings and blockers are displayed in the Pre-QC scorecard — there is no "✅ N check(s) passed" summary.

> **Note:** Duplicate priority and duplicate theme checks, as well as theme mismatch (week/day token) checks, apply to **all rows** including SQL template rows. Required-field and offer-type warnings only apply to form rows since SQL template rows source their content from pre-built `.sql` files. The title/message swap detection check also applies to all rows.

### 8.4 Generating SQL

1. Click **"Generate SQL"**

> **Auto-invalidation:** If any offer-type template file in `macros/offer_types/` was modified on disk since SQL was last generated (detected via file modification timestamps), the previously-cached SQL output is automatically cleared and you must click "Generate SQL" again. This ensures the download always reflects the current template — you cannot accidentally download stale SQL after editing `personalized_deal.sql.j2` or other offer-type templates.

3. The composed SQL includes:
   - Preamble (variable declarations, truncate)
   - Campaign INSERT blocks (form-based rows via Jinja2 template)
   - Custom SQL blocks (SQL template rows rendered through Jinja2 with placeholder substitution)
   - Priority block (TRUNCATE + INSERT for push_priority table)
   - Finalization queries
   - Static tail (counts / QC / archive queries)

   All four table names (`push_allocation`, `push_allocation_final`, `push_priority`, `push_priority_full`) automatically include the send-day suffix (e.g. `_SAT`) derived from the campaign's Send Date. See [§10.1](#101-tablesyaml) for details.

If any rows have been manually edited in the SQL Preview, those overrides are used verbatim in place of the auto-generated SQL.

### 8.5 Export File Naming

The download filename follows the format:

```
PUSH_Wk{WW}_{Day}.sql
```

Example: `PUSH_Wk09_Mon.sql` (for week 09, Monday)

Clicking **"Download .sql"** automatically sets the campaign status to **Exported** and also saves a copy to **`sql_exports/PUSH_Wk{WW}_{Day}.sql`** on the server.

### 8.6 Checksum & Diff

> ⚠️ **Archived** — The Checksum & Diff vs Baseline section has been removed from the Developer UI. The underlying `checksum.py` module (`compute_sha256`, `diff_sql`) remains on disk for potential future re-use.

### 8.7 Audit Trail

All changes are logged as **compact, human-readable summaries**:
- Row additions, edits, and removals
- SQL template loads

Each log entry shows a timestamp and a concise description of what changed (e.g. "Row 1: theme → Wk09_promo"). The change history is displayed as a **reverse-chronological markdown list** at the bottom of the developer section under **"Change History"**.

> **Note:** The audit trail skips `custom_sql` and `row_type` fields when computing diffs to reduce noise.

### 8.8 SQL Template Editor

**Developer only.** The **"🔧 Edit SQL Template Library"** expander provides an in-app editor for modifying SQL template files on disk.

#### Find & Replace Converter

1. Select a SQL template file from the dropdown
2. Pick a **placeholder token** from the selectbox (e.g. `{{ theme }}`, `{{ message }}`)
3. Paste the **hardcoded value** that should be replaced with the placeholder
4. Click **"Apply"** — all occurrences of the hardcoded value are replaced with the Jinja2 token in the file
5. A read-only preview shows the updated file content
6. Click **"Save"** to persist changes to disk, or **"Revert"** to discard

This is the recommended way to convert existing SQL files into Jinja2-ready templates. A help note lists all available placeholder tokens.

### 8.9 Script Editor

**Developer only.** Click **"📝 Script Editor"** in the sidebar to open the Script Editor view. This provides direct in-app read/write access to the core SQL and Jinja2 template files that drive all SQL generation — without needing to open a file system editor or restart the app.

#### Files available to edit

| Label | File path |
|---|---|
| Campaign INSERT | `macros/campaign_insert.sql.j2` |
| Preamble | `macros/preamble.sql.j2` |
| Finalization | `macros/finalization.sql.j2` |
| Finalization Static Tail | `extras/finalization_static_tail.sql` |
| Offer — Personalized Deal | `macros/offer_types/personalized_deal.sql.j2` |
| Offer — Store Coupon | `macros/offer_types/store_coupon.sql.j2` |
| Offer — PUSHSECTION | `macros/offer_types/pushsection.sql.j2` |
| Store Banners | `reference_data/banners.txt` |

#### Workflow

1. Select a file from the **"Select script to edit"** dropdown
2. The file's current content loads into a 500px text editor
3. Make edits directly in the text area
4. Click **"💾 Save"** — writes changes to disk immediately
5. Click **"↩️ Revert"** — discards all unsaved edits and reloads the on-disk version

Both Save and Revert are disabled when there are no unsaved changes. An `ℹ️ You have unsaved changes` notice appears below the buttons whenever the editor contains unwritten edits.

#### Diff preview

Expand **"📄 Show diff"** (visible when edits are pending) to see a unified diff comparing the disk version to your current editor content — useful for reviewing before committing a change.

#### Editing `banners.txt`

The `reference_data/banners.txt` file lists valid store banner names (one per line, lowercase). Edits made here affect:
- The **Banners multiselect dropdown** in flat targeting (§6.7) and OR groups (§6.10)
- The **banner spelling check** advisory warnings (§7.1 and §8.3)

> **Cache note:** The banner list is cached for **5 minutes** (`@st.cache_data(ttl=300)`). Changes take effect on the next page load after the TTL expires, or immediately on a fresh browser session.

#### Editing Jinja2 templates

Changes to `.sql.j2` files take effect for the **next** SQL generation. If SQL was already generated and cached before the edit, click **"Generate SQL"** again to rebuild with the updated template. The offer-type template auto-invalidation mechanism (§8.4) covers `macros/offer_types/` edits automatically.

> **Note:** The Script Editor does not validate SQL or Jinja2 syntax. After saving, verify the output by generating SQL in a Campaign Detail view. This editor is distinct from the **SQL Template Editor** (§8.8), which modifies files in `sql_templates/` (the recurring campaign library) — not the core generation templates.

### 8.10 Optional Column Schema Editor

**Developer only.** Inside the Campaign Detail view, expand **"⚙️ Optional Column Schema (Developer)"** (located in the Campaign Rows section, between the SQL Template Library and the SQL Template Editor).

This tool lets you add new optional INSERT columns without editing code or restarting the app.

#### Viewing the current schema

A read-only dataframe lists all loop-managed optional columns with their field name, UI label, SQL alias, SQL type, and escape flag.

#### Adding a new column

Fill in the **"Add new column"** form:

| Field | Description |
|---|---|
| **Field name** | Python identifier (e.g. `eventid`) — validated for identifier format and checked for duplicates |
| **UI label** | Display label shown in the Optional Fields expander (e.g. `Event ID`) |
| **SQL alias** | Column name in the INSERT SELECT list (e.g. `eventid`) |
| **SQL type** | `text` (string value, single-quoted) or `bool` (NULL / TRUE / FALSE) |
| **Apostrophe escape** | Whether apostrophes in the value should be auto-escaped to `\'` (recommended for text fields) |
| **Help tooltip** | Optional caption shown below the field in the UI |

Click **"Add column"** to:
1. Append the new entry to `config/optional_columns.yaml` on disk
2. Clear the `_load_optional_columns` LRU cache in `compose.py`
3. Trigger a page rerun — the new field appears immediately in every row's **📎 Optional Fields** expander

> **No restart required.** The new column is available in the UI, SQL export, CSV roundtrip, and the paste deep-link parser immediately after saving.

> **To remove or modify a column**, edit `config/optional_columns.yaml` directly (see [§10.5](#105-optional_columnsyaml)) and restart the app or let the cache expire.

---

## 9. Build Time Analytics

**Developer only.** Click **"📊 Build Analytics"** in the sidebar (visible when in Developer role) to open the analytics view. It provides a retrospective view of campaign build effort and throughput across all saved campaign days — useful for business case preparation and process improvement.

### 9.1 Terminology

| Term | Definition |
|------|------------|
| **Campaign Day** | A single send day (Monday through Sunday). One campaign day contains multiple campaigns. |
| **Campaign** | An individual push notification audience segment — each row within a campaign day. |
| **Adhoc Campaign** | A campaign built from scratch using the form editor. |
| **Recurring Campaign** | A campaign injected from the SQL template library — reused weekly with minimal edits. |
| **Wall-Clock Build Time** | Time from when a campaign day is created until it is first submitted for export. Includes idle time (meetings, waiting for assets). Reference only — shown in the Build Detail table but not used in charts. |
| **Active Editing Time** | **(Primary metric.)** Only the seconds a user is actively interacting with campaign form fields. Capped at 5-minute idle gaps to prevent inflated numbers from open-but-inactive sessions. Powers all analytics charts. |

### 9.2 Charts & Metrics

Each section has an independent **week filter** (see [§9.3](#93-filtering-weeks)) so testing weeks can be excluded from individual charts without affecting others.

| Section | Description |
|---------|-------------|
| **Summary** | Five KPI cards: Campaign Days, Avg Active Edit Time, Median Active Edit Time, Total Campaigns Built, Total Active Edit Time |
| **Weekly Active Edit Time Trend** | Tabbed bar charts — avg active edit time per calendar week and campaign days per calendar week |
| **Campaign Day Timeline** | Bar chart of active edit time per individual campaign day, labeled `Wk{NN} {Day} MM/DD`. Only days with recorded edit time are shown. |
| **Active Edit Time by Day of Week** | Average active edit time per send day (Mon–Sun, in day order) |
| **Adhoc vs Recurring Rows** | Stacked bar chart — adhoc (form-built) vs recurring (SQL template) campaigns per week |
| **Active Edit Time Breakdown** | Weekly total active editing minutes (only shown when tracking data exists) |
| **Campaign Day Build Detail** | Full sortable table with all metrics per campaign day. Wall-Clock (min) column shows reference-only elapsed time; Active Edit (min) is the primary metric. |
| **Business Case Snapshot** | Summary metrics table (all figures use Active Editing Time) + **📖 Glossary & How These Numbers Are Computed** expander |

### 9.3 Filtering Weeks

Each chart section has its own filter row with two controls:

- **Mode**: `Include selected` or `Exclude selected`
- **Weeks multiselect**: pick one or more `Wk{NN}` week labels

Leaving the multiselect empty shows all weeks (no filter applied). Use **Exclude selected** to remove testing or incomplete weeks from specific charts without affecting others.

### 9.4 Exporting Analytics

The **Campaign Day Build Detail** section includes a **"📥 Export Analytics to CSV"** button. The file is saved as UTF-8 with BOM (opens correctly in Excel) and contains all filtered data with the following columns: Send Date, Wk ID, Day, Campaigns, Wall-Clock (min), Active Edit (min), Sessions, Saves, Edits, Status.

---

## 10. Configuration Reference

### 10.1 tables.yaml

BigQuery table paths. Switch `env` between `prod` and `dev`:

```yaml
env: prod
datasets:
  prod:
    push_allocation: project.dataset.PUSH_Allocation
    push_priority: dataset.push_priority
    # ...
  dev:
    push_allocation: dev-project.dataset.PUSH_Allocation
    # ...
```

#### Day-of-Week Table Suffixes

When a campaign day's **Send Date** is set, the tool automatically appends a 3-letter uppercase day abbreviation to the four allocation and priority table names:

| Base table name (in `tables.yaml`) | Resolved name in SQL (e.g. Saturday send) |
|---|---|
| `…PUSH_Allocation` | `…PUSH_Allocation_SAT` |
| `…PUSH_Allocation_Final` | `…PUSH_Allocation_Final_SAT` |
| `…push_priority` (unqualified) | `…push_priority_SAT` |
| `…push_priority` (fully-qualified) | `…push_priority_SAT` |

Day abbreviations: **MON, TUE, WED, THU, FRI, SAT, SUN**.

The suffix is applied by `load_tables()` at export time and flows through all Jinja2 templates — preamble, campaign INSERTs, SQL template rows, finalization, and the static counts/QC tail. The `PUSH_Allocation_Final_archive` table is **not** suffixed.

> To use this feature your BigQuery environment must have the day-specific tables created in advance (e.g. `PUSH_Allocation_MON` through `PUSH_Allocation_SUN`).

### 10.2 users.yaml

Developer passphrase (SHA-256) and optional RBAC user entries. Update `developer_passphrase_sha256` to change the passphrase:

```powershell
python -c "import hashlib; print(hashlib.sha256(b'NEW_PASS').hexdigest())"
```

### 10.3 targeting.yaml

Optional lookup lists for targeting validation. When populated, values appear as help text in the data editor:

```yaml
divisions:
  - 19
  - 20

banners:
  - cedar_market
  - pine_and_peak
```

### 10.4 campaign_templates.yaml

Recurring campaign definitions retained for reference. Not loaded in the UI.

### 10.5 optional_columns.yaml

Single source of truth for every optional column that appears in the campaign INSERT `SELECT` list. Adding an entry here automatically:
- Creates the field in every row's **📎 Optional Fields** expander (with the configured label and help text)
- Adds the column to the Jinja2 `optional_cols` loop in `macros/campaign_insert.sql.j2`
- Makes the field injectable via **Paste deep-link params** and the CRF Push Section parser
- Includes the column in CSV export/import

**Entry structure:**

```yaml
- name: param_q          # Python / PACE field name
  sql_alias: param_q     # Column name in the INSERT SELECT
  sql_escape: true       # Escape apostrophes with \'
  sql_type: text         # text | bool | static
  sql_managed: loop      # loop (auto-rendered) | hardcoded (rendered manually in template)
  ui_visible: true       # Show in Optional Fields UI
  label: Param Q         # Display label
  help: "Deep-link query parameter"  # Tooltip (optional)
```

**SQL types:**

| Type | SQL output |
|---|---|
| `text` | `'value'` (single-quoted; escaped if `sql_escape: true`) |
| `bool` | `NULL` (blank), `TRUE`, or `FALSE` |
| `static` | Raw SQL expression injected verbatim (used for hardcoded fields like `update_dt`) |

> **To add a new column via the UI** without editing YAML directly, use the **⚙️ Optional Column Schema Editor** (§8.10).

---

## 11. SQL Template Library — Adding Files

### Method 1: Drop files into the folder
Place `.sql` files directly in `sql_templates/`. They appear in the UI on next refresh.

### Method 2: Upload via the UI
Use the file uploader in **"Load from Recurring SQL Template Library"** → saves to `sql_templates/` automatically.

### File conventions
- One complete SQL block per file
- The filename (without `.sql`) becomes the display name
- Use descriptive names: `fed_promo_insert.sql`, `weekly_deals_reminder.sql`

---

## 12. Column Reference

### Required Columns

| Column | Description |
|---|---|
| `campaign_name` | Display name for the campaign |
| `theme` | Theme identifier used in priority table |
| `message` | Push notification body text |
| `title` | Push notification title text |

### Common Optional Columns

| Column | Description |
|---|---|
| `media_url` | URL for push notification media |
| `pushsection` | App section the push links to |
| `param_q` | Query parameter for deep linking |
| `screentitle` | Screen title displayed in-app |

### Other Optional Columns

| Column | Description |
|---|---|
| `subtitle` | Push notification subtitle |
| `gameid` | Game identifier |
| `product` | Product identifier |
| `searchterm` | Search term parameter |
| `store` | Store parameter |
| `seller` | Seller parameter |
| `category` | Category parameter |
| `program` | Program parameter |
| `pagname` | Page name parameter |
| `datasource` | Data source identifier |
| `modelconfigid` | Model config identifier |
| `partnerid` | Partner identifier |
| `autoimage` | Auto-image flag (NULL / TRUE / FALSE) |

### JOIN / Offer Columns

| Column | Description |
|---|---|
| `offer_type` | `PERSONALIZED DEAL`, `STORE COUPON`, `PUSHSECTION`, or blank — determines JOIN pattern |
| `offer_id` | Single or comma-separated offer IDs — filterable in WHERE clause |

### Targeting Columns

| Column | Description |
|---|---|
| `division_ids` | Comma-separated division IDs |
| `division_mode` | `IN` or `NOT IN` |
| `banners` | Comma-separated banner names (always lowercased in SQL output) |
| `banner_mode` | `IN` or `NOT IN` |
| `store_ids` | Comma-separated store IDs |
| `store_mode` | `IN` or `NOT IN` |
| `div_banner_groups` | JSON list of OR-group dicts (edit via the "🔗 Division + Banner/Store OR groups" expander, not the grid) |
| `custom_joins` | JSON list of custom JOIN dicts (edit via the "🔗 Custom JOINs" sub-expander, not the grid) |

---

## 13. CRF Converter

**All roles.** Click **"📋 CRF Converter"** in the sidebar to open the CRF Converter view.

The CRF Converter parses a manually-prepared Campaign Request Form (`.xlsx` file) into PACE row data. It handles multi-row Excel layouts where Push Section parameters, targeting notes, and Rich Push flags are spread across continuation rows rather than a single data row per campaign.

### 13.1 Uploading a CRF File

1. Click **"Browse files"** and select an `.xlsx` file (first sheet, row 1 = headers)
2. The parser automatically runs on upload — results appear below
3. Parsed output is **cached** for the session; re-uploading the same file (same name + size) skips re-parsing

> The parse cache is keyed on file name, file size, and a **parser version string** (`v7-ps-continuation-merge`). Any parser update automatically invalidates old caches.

### 13.2 Expected Columns

Header matching is **case- and whitespace-insensitive**. Only recognised columns are used; others are silently ignored.

| CRF Column | Maps to PACE Field |
|---|---|
| Campaign Name | `campaign_name` |
| Theme Name | `theme` |
| Priority | `priority` |
| Type | `offer_type` |
| Offer ID | `offer_id` |
| Store ID | `store_ids` |
| Push Section | `pushsection` (and optionally `param_q`, `screentitle`, etc.) |
| Targeting | `targeting_notes` |
| Rich Push Image URL | `media_url` |
| Title/Headline | `title` |
| Copy/Message | `message` |
| Row Type *(optional)* | `row_type` (`sql` or `form`) |

### 13.3 Parsed Output Preview

After upload, the converter shows:
- **Warnings** — non-fatal issues (dropped offer IDs, unrecognised Push Section keys, missing content, etc.)
- **Preview table** — all parsed campaigns in a dataframe with key fields visible
- **Row count** — total PACE rows that would be created

### 13.4 Downloading the CSV

Click **"📥 Download CSV"** to export the parsed rows as a UTF-8 BOM CSV file (`PUSH_Wk{WW}_{Day}_crf.csv`). This file is compatible with the **"📤 Import CSV"** feature in the Campaign Detail view (§6.5).

> **Note:** Downloading the CSV does not create a campaign day in PACE. Use the Inject panel (§13.5) to skip the CSV roundtrip entirely.

### 13.5 Injecting Directly into a Campaign Day

Below the download button, the **"🎯 Inject directly into a campaign day"** panel lets you push parsed rows straight into an existing campaign.

**Eligible targets:** Only campaigns in **Draft** or **Pending Assets** status appear in the selectbox. Campaigns in In Progress, Ready, Submitted, Exported, or Campaign Launched are excluded to prevent accidentally modifying already-deployed content.

**Injection modes:**

| Mode | Behaviour |
|---|---|
| **Append to existing rows** | Parsed rows are appended after existing rows; priorities are renumbered starting after the last existing row |
| **Replace all existing rows** | All existing rows are deleted first, then parsed rows are inserted from priority 1. Requires explicit checkbox confirmation: "Yes, replace all rows" |

**After injection:**
- A `crf_inject` entry is added to the campaign's audit trail
- An activity log event is recorded (`CRF Injected (N row(s), append/replace)`)
- The app navigates automatically to the Campaign Detail view for the target campaign

### 13.6 Parser Rules Reference

#### Offer ID validation
Only tokens matching the format `NNNNNNNNN-X` (digits, dash, single letter — e.g. `71980463-D`) are accepted. Free-text notes, sentences, bare numbers, and other non-conforming tokens are **silently dropped** and reported as warnings. Comma-separated lists are supported; each token is validated independently.

#### Rich Push detection
When the CRF `Type` column contains any of: `Rich Push`, `Rich Push Image`, `RichPush`, `rich-push` (case-insensitive, extra whitespace ignored), the parser:
- Clears `offer_type` for the campaign (Rich Push is not a valid PACE offer type)
- Sets `rich_push_image = True` on every sub-row, multi-theme parent row, and SQL standalone row emitted for that campaign

Real offer types (`PERSONALIZED DEAL`, `STORE COUPON`, `PUSHSECTION`) pass through unchanged.

#### Push Section parsing
CRF Push Section cells may contain either:

1. **A plain value** (no `=` sign) — treated as the `pushsection` field verbatim:
   ```
   weeklyAd
   ```

2. **A `key=value` block** (one pair per line) — each line is parsed into the corresponding PACE field:
   ```
   pushsection=aemLandingPage
   q=fast-grocery-delivery
   Screen Title=Flash_Delivery
   ```

Key matching is **liberal**: spaces, dashes, and underscores are stripped and the key is lowercased before lookup. All of these resolve to the same field:
- `Screen Title` → `screentitle`
- `screen_title` → `screentitle`
- `SCREEN-TITLE` → `screentitle`
- `ModelConfigID` → `modelconfigid`
- `q` → `param_q`

#### Continuation-row merging
In many CRF files, Push Section parameters are spread across multiple Excel rows beneath the content row (no title/message on those follow-on rows). The parser automatically merges these fragments into the most-recently-emitted sub-row, filling only empty fields (never overwriting). If Push Section fragments arrive before any content row for the campaign, they are buffered and applied to the first content row that follows.

#### Targeting notes
Any `Targeting` column cell that is not a theme-name placeholder is accumulated as `targeting_notes` for the campaign. Notes are broadcast to every sub-row and emitted as `/* ... */` SQL comment blocks in the export.

#### SQL campaigns
Set the optional **Row Type** column to `sql` on a campaign's priority row to flag it as a SQL template campaign. The parser skips the title/message/media_url/pushsection classifier for those rows; only campaign metadata and targeting notes are retained. `rich_push_image` and `offer_type` rules still apply.

#### Paste deep-link params (in-form)
The same liberal key-normalization rules apply in the **"📋 Paste deep-link params"** text area inside each row's **📎 Optional Fields** expander (and in every sub-row). Paste any `key=value` block — keys with spaces, dashes, underscores, or mixed case are all resolved using the same `_PASTE_FIELD_ALIASES` lookup as the CRF parser.

All optional columns defined in `config/optional_columns.yaml` are automatically injectable via paste — adding a new column to the YAML registry makes it available in both parsers with no further code changes.

---

## 14. Development Notes

The notes below summarize how the demo's workflow and validation features evolved.

**v4.0 (Aug 28, 2026) — RCS Channel Expansion:**
- App supports **PUSH** and **RCS** through separate channel workflows and templates, with shared navigation, storage patterns, and tests. Export filenames are prefixed by channel (`PUSH_Wk##_Day.sql` / `RCS_Wk##_Day.sql`).
- PUSH runtime is **unchanged** by RCS work — `build_sql()`, PUSH templates, PUSH row schema, PUSH Pre-QC all preserved byte-identical. RCS is a fully independent code path.

**v3.40 (Aug 17, 2026):**
- **Optional Column Registry** — `config/optional_columns.yaml` is now the single source of truth for every optional INSERT column. The Jinja2 template (`macros/campaign_insert.sql.j2`) was refactored to render optional columns via a `{% for col in optional_cols %}` loop instead of 22 hardcoded lines. `app/compose.py` builds the `optional_cols` context list from YAML (with LRU cache); `app/ui.py` derives `OPTIONAL_COLUMNS` at import from YAML. Adding one YAML entry now automatically provides: the UI field, row default, SQL SELECT column, CSV roundtrip, and paste-injectable alias — no code changes needed. See [§10.5](#105-optional_columnsyaml).
- **In-app Optional Column Schema Editor** — New Developer-only **"⚙️ Optional Column Schema (Developer)"** expander in the Campaign Detail view. Shows current loop-managed columns in a dataframe; provides an Add New Column form (field name, label, SQL alias, type, escape flag, help). Saves directly to `optional_columns.yaml`, clears LRU cache, and reruns — new field appears immediately. See [§8.10](#810-optional-column-schema-editor).
- **Theme mismatch check rewritten** — `_check_theme_mismatch()` now uses `pn_wk(\d{1,2})_(\d{4})_([A-Za-z]+)` regex to extract the canonical `pn_wkNN_YYYY_Day` tracking token from the theme string. If the token is absent, the advisory warns "theme is missing the `pn_wkNN_YYYY_Day` tracking token". If present, week number, year, and day abbreviation are validated independently. Replaces the previous whole-string scan that used `\b(20\d{2})\b` — which failed when a year was surrounded by underscores (e.g. `_2027_`). Applies to all rows (form and SQL template).
- **Whitespace trim covers multi-theme sub-rows** — `_trim_whitespace_fields()` now descends into `sub_rows` for multi-theme containers. Previously only top-level rows were trimmed; sub-row fields with leading/trailing spaces were silently skipped.

**v3.37 (Aug 7, 2026):**
- **Store list paste box** — New **"📋 Paste a store list"** expander in each row's targeting section (below Store IDs). Paste a vertical Excel column of store numbers; non-numeric tokens (headers, banner names) are rejected with a named warning; duplicates are silently removed. Two action buttons: **Replace Store IDs** (overwrites) and **Append to Store IDs** (merges, deduplicates). Preview shows count and first 10 IDs before committing. Supports 2,000+ store IDs with no performance impact. See [§6.7](#67-targeting-division--banner--store-id).

**v3.36 (Aug 6, 2026):**
- **CRF Converter added** — New `📋 CRF Converter` view accessible from the sidebar (all roles). Upload a CRF `.xlsx` file to parse it into PACE rows; download as CSV or inject directly into a campaign day. See [Section 13](#13-crf-converter).
- **CRF — Offer ID validation** — Only tokens in `NNNNNNNNN-X` format (digits + dash + single letter, e.g. `71980463-D`) are accepted. Sentences, notes, and bare numbers are dropped with a per-row advisory warning.
- **CRF — Direct injection** — "🎯 Inject directly into a campaign day" panel below the download button. Selectbox shows only **Draft** and **Pending Assets** campaigns; deployed or submitted campaigns are excluded. Append or Replace mode; Replace requires explicit confirmation. Injects rows, renumbers priorities, records audit + activity log entry, and navigates to the detail view.
- **CRF — Push Section continuation-row merge** — Push Section fragments spread across multiple CRF Excel rows (no title/message on those rows) are now merged into the most-recently-emitted sub-row. Fields are only set if empty (never overwrites). Parser version `v7-ps-continuation-merge`.
- **CRF — Rich Push detection** — When the CRF `Type` column contains `Rich Push` / `Rich Push Image` / `RichPush` / `rich-push` (case-insensitive), `offer_type` is cleared and `rich_push_image = True` is set on all emitted rows. Real offer types pass through unchanged. Parser version `v6-rich-push-flag`.
- **Universal paste-parser key normalization** — Keys in the CRF Push Section cell parser and in both in-form "Paste deep-link params" text areas are now normalized by stripping non-alphanumeric characters and lowercasing before lookup. `Screen Title`, `screen_title`, `SCREEN-TITLE`, `ModelConfigID`, `EVENT_ID`, etc. all resolve to the correct PACE field automatically.
- **Paste-parser coverage from YAML registry** — `_PASTE_FIELD_MAP`, `_PASTE_FIELD_ALIASES`, and `_CRF_DEEP_LINK_EXTRAS` are now auto-derived from `config/optional_columns.yaml`. Adding a new optional column to the YAML automatically makes it paste-injectable in both parsers with no code change.
- **CRF Converter sidebar position** — `📋 CRF Converter` button moved above `📊 Build Analytics` and `📝 Script Editor` in the sidebar. Visible to all roles.

**v3.34 (Jul 10, 2026):**
- **Fixed** emoji/symbol display — `app/ui.py` was double-encoded during a file edit (UTF-8 bytes misread as CP1252 then re-encoded as mojibake, plus CRLF line endings doubled on every line). All emoji icons and special characters (↔, 📱, 🔧, ─, etc.) fully restored via byte-level reversal. No UI behavior changes.
- **Internal** offer-type template caching — `@lru_cache(maxsize=16)` added to `_load_offer_type_template()` in `compose.py`; cache cleared automatically when template files change on disk. Reduces up to 30 disk reads per SQL generation to 3. No impact on SQL output.
- **Internal** dead code removed — `_check_suspect_chars()` function and `_SUSPECT_CHARS` dict fully removed from `app/ui.py` (call had been removed in v3.33; function body now also deleted).
- **Internal** `streamlit-authenticator` dependency removed from `requirements.txt` (was never imported). `config/users.yaml` cleaned — unused `credentials:` and `cookie:` blocks removed. `developer_passphrase_sha256` key unaffected.
- **Fixed** broken test — `test_legacy_space_toggle` replaced with `test_no_legacy_space_concat` in `tests/test_compose.py` (was calling `build_sql()` with a non-existent parameter, causing `TypeError` on every test run).

**v3.33 (Jul 02, 2026):**
- **Fixed** targeting notes for SQL template rows — SQL template rows now emit `/* Custom Targeting Instructions: ... */` comment blocks in the export, matching form row behaviour. Previously only form rows emitted targeting notes in the SQL output.
- **Removed** hidden/paste-artifact character check from Pre-QC scorecard — em-dash and non-breaking space advisory warnings no longer shown.
- **Removed** "✅ N check(s) passed" collapsible panel from Pre-QC scorecard — only blockers and advisory warnings are now displayed.

**v3.32 (Jun 30, 2026):**
- **Multiple Themes (Sub-Rows)** — New feature allowing any standard form row to be converted into a multi-theme container holding multiple sub-rows that share the same priority. Each sub-row is a full form row (Required Fields, Offer Type, targeting, OR groups, custom JOINs, targeting notes) and generates its own INSERT block in the SQL export at the parent priority. Sub-row creation uses a number input + **＋ Create Sub-Rows** button; individual sub-rows can be removed with a confirmation prompt. Toggling off "Multiple Themes" deletes all sub-rows with a confirmation dialog. `build_sql()` and `build_priority_block()` in `compose.py` updated for multi-theme containers. All pre-QC validation checks flatten sub-rows and display decimal labels (`Row 3.1`, `Row 3.2`); duplicate-priority warnings suppressed for sub-rows. CSV export flattens sub-rows as individual rows (container excluded); import brings rows in as flat form rows. Developer SQL Preview shows per-sub-row editable text areas in a grouped expander. Data model fields `multi_theme` and `sub_rows` backfilled to existing campaign JSON on load. See [§6.12](#612-multiple-themes-sub-rows).

**v3.31 (Jun 12, 2026):**
- **Script Editor** *(Developer only)* — New `📝 Script Editor` view accessible from the sidebar. Provides in-app read/write access to 8 core files: `campaign_insert.sql.j2`, `preamble.sql.j2`, `finalization.sql.j2`, `finalization_static_tail.sql`, `personalized_deal.sql.j2`, `store_coupon.sql.j2`, `pushsection.sql.j2`, and `reference_data/banners.txt`. Features a 500px text editor with 💾 Save, ↩️ Revert, and unified diff preview. Edits to `.sql.j2` templates take effect on next SQL generation; `banners.txt` edits propagate to the banner multiselect and spelling check within 5 minutes. See [§8.9](#89-script-editor).
- **Store Banners editable in Script Editor** — `reference_data/banners.txt` added to the Script Editor file list, allowing Developers to add/remove valid banner names without file system access.

**v3.30 (Jun 8, 2026):**
- **In-row SQL Template Picker** — Every row expander now includes a `🗄️ SQL Template` selectbox. Selecting a template copies its SQL into `custom_sql` and promotes `row_type` to `sql`; selecting `"— None —"` reverts the row to standard INSERT generation. The picker pre-selects the currently assigned template on re-render. Deleted-from-disk template names are preserved in the dropdown to prevent silent auto-clears. The top-of-page multiselect remains for fast bulk-adds. `🔄 Reload SQL from library` updated to use `sql_template_name` for matching. See [§6.3](#63-recurring-sql-template-library) and [§6.6](#66-editing-campaign-rows).
- **Rich Push Image checkbox** — New per-row `st.checkbox("Rich Push Image")` rendered between Required Fields and Optional Fields. When checked and `media_url` is blank, an inline warning is shown inside Optional Fields. Stored as `rich_push_image: bool` in row JSON. Exported to CSV as `Y`/`N`; parsed back on import. See [§6.6](#66-editing-campaign-rows) and [§6.9](#69-exporting-the-grid-to-csv).
- **Inline field guards in Optional Fields** — `pushsection` warns when blank and Offer Type is `PUSHSECTION`; `media_url` warns when blank and Rich Push Image is checked. See [§6.6](#66-editing-campaign-rows).

**v3.29 (Jun 3, 2026):**
- **Title/message swap detection** — New advisory pre-QC check flags rows where `title` and `message` may have been accidentally swapped. `_compute_historical_char_stats()` reads campaign data from the last 7 days to derive dynamic averages (~26 chars for title, ~95 for message; cached 5 min, falls back to hardcoded baselines). `_check_title_message_swap()` warns when: title is longer than message (strong signal), or title exceeds 1.5× its average while message is below 0.6× its average (weaker signal). Warning shows exact char counts and computed averages. Appears in both User and Developer pre-QC scorecard under **"title/message character counts (possible swap detection)"**. See [§7.1](#71-pre-submit-validation) and [§8.3](#83-pre-export-validation).

**v3.35 (Aug 5, 2026):**
- **Day-of-week table suffixes** — `load_tables()` in `app/ui.py` now accepts a `send_day` parameter. When the campaign's Send Date is set, a 3-letter uppercase day abbreviation (`_MON`–`_SUN`) is appended to `push_allocation`, `push_allocation_final`, `push_priority`, and `push_priority_full` at export time. The suffix flows automatically through all Jinja2 templates — preamble, INSERT blocks, finalization, and the static tail. `PUSH_Allocation_Final_archive` is not suffixed.
- **SQL templates converted to Jinja2** — The sample recurring template uses configured table placeholders, so the output table and day suffix are supplied at render time.
- **Static tail converted to Jinja2** — `extras/finalization_static_tail.sql` was previously appended verbatim. It is now rendered through the permissive Jinja2 environment in `build_sql()`, resolving `{{ tables.push_allocation_final }}`, `{{ tables.push_priority }}`, `{{ tables.offer_catalog }}`, `{{ tables.coupon_store_validity }}`, `{{ tables.offer_allocation_history }}`, and `{{ tables.consolidated_offer_bank }}` from `tables.yaml`.

**v3.28 (May 6, 2026):**
- **Analytics metric overhaul** — All Build Time Analytics charts now use **Active Editing Time** (`handling_min`) as the primary metric instead of wall-clock elapsed time. KPI labels updated to "Avg/Median Active Edit Time". Charts renamed: "Weekly Active Edit Time Trend", "Active Edit Time by Day of Week". Wall-clock elapsed time (`elapsed_to_submit_min`) retained in the Build Detail table as "Wall-Clock (min)" for reference only. All charts migrated from `st.bar_chart` to Altair for explicit axis sort control.
- **Campaign Day Timeline chart** — New bar chart in the Analytics view showing active edit time per individual campaign day, labeled `Wk{NN} {Day} MM/DD` (e.g. `Wk18 Thu 05/07`). Filters to only days with recorded active editing time. Tooltips show full label and minutes. Has its own independent week filter.

**v3.27 (May 4, 2026):**
- **Build Time Analytics view** *(Developer only)* — New `📊 Build Analytics` view accessible from the sidebar. Tracks campaign build velocity, effort, and throughput across all saved campaign days. Includes: KPI summary (Campaign Days, Avg/Median Build Time, Total Campaigns Built, Total Active Edit Time), weekly build time trend, build time by day of week (Mon–Sun in day order), adhoc vs recurring campaign split, active edit time breakdown, full sortable campaign day detail table with CSV export, and a Business Case Snapshot with full glossary and metric computation reference. See [Section 9](#9-build-time-analytics).
- **Per-chart week filters** — Each analytics chart section has its own independent Include/Exclude week multiselect. Testing weeks can be excluded from individual charts without affecting others.
- **Analytics terminology standardised** — Campaign Day = a send day (Mon–Sun container); Campaign = each individual row/audience segment; throughput metric counts total campaigns (rows) per week, not campaign days.
- **Adhoc vs Recurring Rows chart** — Replaced the noisy "Rows vs Build Time" chart with a stacked bar chart showing adhoc (form-built) vs recurring (SQL template) campaigns per week — directly useful for business case justification.
- **Business Case Snapshot glossary** — Terminology table and metric computation table added inside the Business Case Snapshot so stakeholders who do not use the app can understand every number.

**v3.26 (May 4, 2026):**
- **Banner multiselect dropdown** — The `Banners` field in flat targeting (§6.7) and OR groups (§6.10) is now a clickable multiselect dropdown populated from `reference_data/banners.txt`. Users pick banners from the list instead of typing. Falls back to text input if `banners.txt` is missing. Stored format and SQL output are unchanged.
- **Numbered offer ID Jinja2 variables** — `_expand_offer_ids()` in `compose.py` auto-expands comma-separated `offer_id` into `offer_id_1`, `offer_id_2`, …, `offer_id_N` and `offer_id_list` (`'id1','id2',...` format) at Jinja2 render time for SQL template rows. Available in both the export path and Developer SQL Preview. Caption warning shown in UI when a template references `{{ offer_id_N }}` but fewer than N IDs are provided. See §6.3 and §6.8 for usage.
- **Recurring offer template updated** — The example template supports numbered offer-ID variables and SQL-ready ID lists for reusable offer logic.

**v3.25 (Apr 23, 2026):**
- **Portfolio identity** — The fictional Orchard & Tide demo is presented as **P·A·C·E — Precision Audience Campaign Engine**.

**v3.24 (Apr 23, 2026):**
- **Local setup** — The portfolio README provides standard Python virtual-environment setup and the command to launch the demo locally.

**v3.23 (Apr 22, 2026):**
- **Theme mismatch check extended to SQL template rows** — `_check_theme_mismatch()` in `app/ui.py` previously skipped SQL template rows. Removed the skip so both week-token and day-token checks run on every row. Catches themes like `..._wk15_2026_Thu` in a Week 16 campaign.
- **Dev pre-export validation — targeted row-type checks** — Duplicate priority and duplicate theme checks in the Developer pre-export loop now apply to all rows (form and SQL template). Required-field and offer-type warnings still correctly skip SQL rows. Prevents mismatched priorities/themes from being silently ignored when SQL template rows are present.

**v3.22 (Apr 22, 2026):**
- **Feature guide** — New `Features/` folder and `Features/campaign-builder-features.md` created. 27-section end-user reference covering every feature with examples, field tables, and SQL output samples. Suitable for any user level.
- **Offer type top-strip alignment fix** — Added `vertical_alignment="bottom"` to the 4-column header row (`tc1–tc4`) in `_render_row_form()` (`app/ui.py`). Fixes misalignment between the `st.selectbox` (Offer Type) and the adjacent `st.number_input`/`st.text_input` widgets in each row expander.

**v3.21 (Apr 16, 2026):**
- **PST clock in sidebar** — All roles now see a live Pacific Time clock (🕐 HH:MM AM/PM · Mon DD, YYYY) in the sidebar above the breadcrumb, rendered on every page interaction.
- **Status selectbox non-typeable** — CSS disables the type-to-search input inside all status selectboxes (`pointer-events:none`, `caret-color:transparent`). Status is now strictly a dropdown pick.
- **"Campaign Launched" status** — New 7th status (dark green `#037f4c`). Auto-assigned on the dashboard whenever the send date has passed **8:00 AM PST/PDT**. Excluded from manual User selection. `storage.py` `STATUSES` list updated; CSS color rule added.
- **Auto-transition uses PST timezone** — `datetime.now(ZoneInfo("America/Los_Angeles"))` used for the send-date comparison. `from zoneinfo import ZoneInfo as _ZoneInfo` added to `ui.py` imports.
- **Exported status revert fix** — `user_statuses` excluded "Exported", causing the dashboard selectbox to fall back to index 0 ("Draft") and silently overwrite the JSON on every render for Users. Fixed by always appending the campaign's current status to the available options list when it is not already present.
- **Detail view session rehydration** — Added guard at top of `render_detail()`: if `campaign_status` is absent from session state (full page refresh while on detail view), the campaign is re-loaded from disk via `_load_into_session()` before any widgets render or auto-save fires.

**v3.17 (Apr 16, 2026):**
- **Dashboard alignment overhaul (revised)** — Dashboard rows now use `st.columns(vertical_alignment="center")` for all header and data rows. Manual `padding-top:8px` hacks removed. CSS collapses hidden marker element containers (`.status-color`, `.btn-red`) to `height:0` so they don't inflate row height; zeros the vertical gap between stacked column children; removes extra margins from selectboxes and buttons inside columns. Status selectbox nudged up via `margin-top:-1rem` to align with action buttons.

**v3.16 (Apr 16, 2026):**
- **Active session counter** — Developer sidebar now shows `🟢 N active session(s)` below the breadcrumb. Uses Streamlit's internal runtime API (`_get_active_session_count()` in `ui.py`); fails silently if the API is unavailable.

**v3.13–v3.15 (Apr 2026):**
- Offer template cache invalidation — auto-clears generated SQL when `macros/offer_types/` files change
- Double header fix in SQL overrides (`build_sql()` no longer wraps verbatim overrides)
- Row expander label uses only `campaign_name`; empty falls back to `Row N`
- Apostrophe auto-escape for SQL template rows (`_escape_sql_strings()` in `compose.py`)

**v3.10–v3.12 (Apr 2026):** editable priority field, stable `_row_id` UUIDs, `message`/`title` as `st.text_area`, trailing-whitespace detection, banner spelling check, unified `exports/` folder, dedicated `sql_exports/` folder.

**v3.6–v3.9 (Mar 2026):** per-row expandable forms, INCLUDE/EXCLUDE mode labels, content warnings (apostrophes, `[Banner]`), theme mismatch advisory, OR group parenthesis fix.

**v3.0–v3.5 (Mar 2026):** Jinja2 placeholder substitution for SQL template rows, editable SQL Preview, compact audit log, Activity Log, Developer passphrase gate, custom JOINs per row, Division+Banner/Store OR groups.

**v2.x (Feb–Mar 2026):** Dashboard + persistence, status pipeline, role-based access, CSV import/export, column pinning.

**v1.x (Feb 2026):** Initial release — targeting, offer types, SQL template library, recurring SQL templates, data editor.
