# P·A·C·E — Orchard & Tide Campaign Studio Feature Guide

> **Who is this for?** Anyone using the tool, from first-time users to developers. No SQL knowledge required to read this guide.
>
> **Which channel?** This guide covers the **PUSH** channel (mobile app push notifications). The app also supports **RCS** rich messaging.

---

## 0. Channel Picker (before the Dashboard)

When you first open the app you see the **Channel landing page** — two large buttons:

| Button | Channel | When to use |
|---|---|---|
| **📱 PUSH** | Mobile app push notifications | This guide |
| **💬 RCS** | Rich messaging | For card-based and carousel messages |

Your selection is remembered for the browser session. To switch channels later:

- Use the **PUSH / RCS** toggle buttons in the sidebar, or
- Click **← Back to landing** in the sidebar to return to the picker.

A small **channel badge** (icon + label pill) appears next to the Dashboard header, next to the Analytics header, and inline in every sidebar breadcrumb so the active channel is always visible.

> **Starting the demo** — Follow the local setup steps in the project README. This portfolio copy stores any demo campaigns locally.

---

## Table of Contents

1. [Dashboard — Your Home Screen](#1-dashboard--your-home-screen)
2. [Campaign Day Lifecycle & Statuses](#2-campaign-day-lifecycle--statuses)
3. [Creating a Campaign Day](#3-creating-a-campaign-day)
4. [Opening & Editing a Campaign Day](#4-opening--editing-a-campaign-day)
5. [Cloning a Campaign Day](#5-cloning-a-campaign-day)
6. [Deleting a Campaign Day](#6-deleting-a-campaign-day)
7. [Campaign Rows — the Row Editor](#7-campaign-rows--the-row-editor)
8. [Required vs Optional Fields](#8-required-vs-optional-fields)
9. [Offer Types & JOIN Logic](#9-offer-types--join-logic)
10. [Targeting (Division / Banner / Store)](#10-targeting-division--banner--store)
11. [OR-Group Targeting](#11-or-group-targeting)
12. [Custom JOINs per Row](#12-custom-joins-per-row)
13. [Targeting Notes (per row)](#13-targeting-notes-per-row)
14. [SQL Template Library (Recurring Campaigns)](#14-sql-template-library-recurring-campaigns)
15. [Row Priority & Sorting](#15-row-priority--sorting)
16. [Removing a Row](#16-removing-a-row)
17. [Validation & Content Warnings](#17-validation--content-warnings)
18. [Saving & the Activity Log](#18-saving--the-activity-log)
19. [CSV Export & Import](#19-csv-export--import)
20. [SQL Export (Developer)](#20-sql-export-developer)
21. [SQL Preview per Row (Developer)](#21-sql-preview-per-row-developer)
22. [SQL Template Editor (Developer)](#22-sql-template-editor-developer)
23. [Input Summary (Developer)](#23-input-summary-developer)
24. [Pre-Export Warnings (Developer)](#24-pre-export-warnings-developer)
25. [Role-Based Access — User vs Developer](#25-role-based-access--user-vs-developer)
26. [Change History (Audit Log)](#26-change-history-audit-log)
27. [Sidebar Utilities](#27-sidebar-utilities)
28. [Script Editor (Developer)](#28-script-editor-developer)
29. [Multiple Themes (Sub-Rows)](#29-multiple-themes-sub-rows)
30. [Optional Column Schema Editor (Developer)](#30-optional-column-schema-editor-developer)

---

## 1. Dashboard — Your Home Screen

The Dashboard is the first screen you see. It lists every campaign day that has been created.

**What you see per campaign day:**

| Column | Description |
|---|---|
| **Week ID** | e.g. `Wk15` |
| **Send Date** | The date the push will be sent |
| **Send Day** | Auto-derived from Send Date (e.g. `Mon`, `Thu`) |
| **Rows** | Number of campaign rows in this day |
| **Last Modified** | Most recent save timestamp |
| **Status** | Current stage in the workflow (color-coded) |
| **Actions** | Open 📂, Clone 📋, Delete 🗑️ buttons |

**Status filter** — A multiselect at the top of the dashboard lets you filter by one or more statuses. A summary strip shows how many campaigns are at each stage.

**Duplicate prevention** — If you try to create a campaign day with the same Week ID + Send Date as an existing one, the tool blocks it and tells you which campaign already exists.

---

## 2. Campaign Day Lifecycle & Statuses

Every campaign day moves through a defined workflow. Statuses are color-coded to match Monday.com conventions.

| Status | Color | Meaning |
|---|---|---|
| **Draft** | Gray | Created but not ready for review |
| **Pending Assets** | Red | Saved with incomplete data; waiting on content |
| **In Progress** | Orange | Actively being built |
| **Ready** | Green | Complete and ready for review |
| **Submitted** | Blue | Submitted for SQL export by a User |
| **Exported** | Purple | SQL has been generated and downloaded by a Developer |
| **Campaign Launched** | Dark Green | Send date has passed 8:00 AM Pacific Time — auto-set |

> **Auto-transition:** The tool automatically changes the status to **Campaign Launched** once the send date has passed 8:00 AM Pacific Time. You don't need to do anything.

> **Pending Assets** is useful when you've started a campaign but are waiting on an image URL, message copy, or other content from another team. Click **"Save as Pending Assets"** to record this state without losing your progress.

---

## 3. Creating a Campaign Day

At the bottom of the Dashboard, fill in:

- **Week ID** — e.g. `Wk15` (required; must be unique with the Send Date)
- **Send Date** — Pick from the date picker
- **Send Day** — Auto-fills from Send Date (Mon, Tue, Wed, Thu, Fri, Sat, Sun)

Click **Create Campaign Day** (green button). The new day opens automatically in the editor.

**Example:**
- Week ID: `Wk16`
- Send Date: `2026-04-20`
- Send Day: `Mon` ← filled in for you automatically

---

## 4. Opening & Editing a Campaign Day

Click the **📂 Open** button next to any campaign day on the Dashboard to enter the detail editor.

At the top of the editor you'll see:
- **Week ID**, **Send Date**, **Send Day** — read-only header fields
- **💾 Last saved: HH:MM:SS AM/PM** — updates every time the campaign is auto-saved

All changes (status, rows, fields) are saved automatically as you work. There is no manual "save" button needed for normal editing.

---

## 5. Cloning a Campaign Day

Click the **📋 Clone** button on any dashboard row to create an identical copy.

What gets copied:
- All rows (form rows and SQL template rows)
- All field values, targeting, JOINs, and notes
- Week ID and Send Date (which you can then edit)

What is reset:
- Status → **Draft**
- Audit / change history → cleared
- Activity log → starts fresh with "Created (cloned)"

This is ideal for recurring campaigns where most rows stay the same week over week.

---

## 6. Deleting a Campaign Day

Click the **🗑️ Delete** button on the dashboard. A confirmation prompt appears — you must click **Yes, delete** to proceed. Clicking **Cancel** does nothing.

> Deletion is permanent. There is no undo.

---

## 7. Campaign Rows — the Row Editor

Each campaign day contains one or more **rows**. Each row becomes one SQL `INSERT` block in the exported file.

Rows are displayed as **expandable cards** (one per row). Click a row's header to expand or collapse it.

**Two types of rows:**

| Type | Label | How it's created |
|---|---|---|
| **Form row** | `form` | "Add blank row" button — you fill in all fields manually |
| **SQL template row** | `sql` | Selected from the Recurring SQL Template Library |

Inside each row expander you'll find:
- Required fields (always visible)
- Rich Push Image checkbox
- Optional fields (inside a sub-expander)
- Targeting section (Division, Banner, Store)
- Targeting notes
- Custom JOINs
- SQL template picker (`🗄️ SQL Template` selectbox)
- SQL source preview (SQL template rows only)

---

## 8. Required vs Optional Fields

### Required fields (must be filled before submitting)

| Field | Example value |
|---|---|
| **Campaign Name** | `Wk16_Mon_PD_CouponCenter` |
| **Title** | `Your Weekly Deals Are Here` |
| **Message** | `Save big this week on your favorites!` |

The **Campaign Name**, **Title**, and **Message** fields appear together in a 3-column row at the top of each row expander.

### 🎯 Theme Variants (required — shown in its own section)

The **Theme** field is displayed in its own dedicated **🎯 Theme Variants** section immediately below the Required Fields row. Theme is still required before submitting, but is kept visually separate because SQL template rows can also have `{{ theme_1 }}`, `{{ theme_2 }}`, etc. placeholders.

| Field | Example value |
|---|---|
| **theme \*** | `Wk16_Mon_PD` |
| **theme\_1 \*** *(SQL rows only, if template uses `{{ theme_1 }}`)* | `Wk16_Mon_PD_Div29` |
| **theme\_2 \*** *(SQL rows only, if template uses `{{ theme_2 }}`)* | `Wk16_Mon_PD_Div33` |

**Auto-detection for SQL template rows:** When a SQL template is assigned to a row, the app scans the template SQL for `{{ theme_1 }}`, `{{ theme_2 }}`, etc. and automatically displays the corresponding required input boxes **inline** (horizontal) next to the main `theme` field. The number of boxes adjusts to however many `theme_N` placeholders are in the template. All are required when present — a caption warning appears under any that are left blank.

### Optional fields (leave blank if not needed)

| Field | When to use |
|---|---|
| **Media URL** | URL to the push notification image |
| **Push Section** | Deep-link section name (e.g. `deals`) |
| **Param Q** | Deep-link query parameter value |
| **Screen Title** | Title shown after tapping the push |
| **Subtitle** | Secondary text for iOS banners |
| **Game ID, Product, Search Term, Store, Seller, Category, Program** | App deep-link parameters |
| **Partner ID** | Third-party partner identifier |
| **Auto Image** | Boolean: true/false/blank |
| **Model Config ID** | Personalization model config |

**Inline guards inside Optional Fields:**

| Field | Warning condition |
|---|---|
| **Media URL** | Shown when blank and the **Rich Push Image** checkbox is checked |
| **Push Section** | Shown when blank and Offer Type is `PUSHSECTION` |
| **Param Q** | Shown when the value contains an underscore (`_`) |
| **Screen Title** | Shown when the value contains a dash (`-`) |

**Rich Push Image checkbox** — A checkbox between Required Fields and Optional Fields. Check it when the push notification includes a hero image. When checked, an inline warning appears if `media_url` is left blank.

---

## 9. Offer Types & JOIN Logic

Each row has an **Offer Type** dropdown and an **Offer ID** field. These control which JOIN the SQL generates.

| Offer Type | What it does | Offer ID required? |
|---|---|---|
| **PERSONALIZED DEAL** | Joins to `OFFER_ALLOCATION_HISTORY` and `coupon_store_validity` | Yes |
| **STORE COUPON** | Joins to `coupon_store_validity` | Yes |
| **PUSHSECTION** | No JOIN; sets `pushofferid = NULL`, `pushoffertype = ''` | No |
| *(empty)* | Same as PUSHSECTION — no JOIN | No |

**Multiple offer IDs:** Enter comma-separated values to generate an `IN` clause.

**Numbered offer ID variables (SQL template rows):** When a SQL template row has multiple comma-separated offer IDs, these additional Jinja2 variables are automatically available:

| Variable | Description | Example (`offer_id = A,B,C,D`) |
|---|---|---|
| `{{ offer_id }}` | Raw comma-separated string | `A,B,C,D` |
| `{{ offer_id_1 }}` | First offer ID | `A` |
| `{{ offer_id_2 }}` | Second offer ID | `B` |
| `{{ offer_id_N }}` | Nth offer ID | `D` (for N=4) |
| `{{ offer_id_list }}` | SQL-ready quoted list for `IN` clauses | `'A','B','C','D'` |

Use `{{ offer_id_list }}` in `IN` clauses and `{{ offer_id_1 }}` / `{{ offer_id_2 }}` etc. for per-offer CASE logic. There is no fixed limit — you can have as many IDs as needed.

**Example:**
- Offer Type: `PERSONALIZED DEAL`
- Offer ID: `12345, 67890`

→ SQL output:
```sql
JOIN ... ON catalog_offer_id IN ('12345','67890')
```

---

## 10. Targeting (Division / Banner / Store)

Each row can be narrowed to a specific audience using three targeting dimensions. All are optional — leave blank to target all customers.

| Field | Example | Mode options |
|---|---|---|
| **Division IDs** | `29` or `5,17,29` | INCLUDE / EXCLUDE |
| **Banners** | **Multiselect dropdown** — pick from the list | INCLUDE / EXCLUDE |
| **Store IDs** | `1234` or `1234,5678` | INCLUDE / EXCLUDE |

**INCLUDE** → SQL generates `= value` or `IN (...)` clause  
**EXCLUDE** → SQL generates `!= value` or `NOT IN (...)` clause

Multiple targeting fields on the same row are combined with `AND`.

**Banners multiselect:** The Banners field is a clickable dropdown showing all banners from `reference_data/banners.txt`. Click to open the list and select one or more banners. Selected banners appear as chips you can remove. This eliminates typos and removes the need to remember exact banner spellings.

**Store list paste box:** Below the Store IDs field, expand **"📋 Paste a store list"** to import store numbers directly from an Excel column:
1. In Excel, select and copy the column of store numbers (header row included is fine)
2. Paste into the text area — one store per line
3. PACE shows a preview: `✅ N unique store ID(s) ready` with the first 10 listed
4. Non-numeric tokens (e.g. column headers, stray text) are flagged in a warning caption but do not block you
5. Click **Replace Store IDs** to overwrite the field, or **Append to Store IDs** to merge with any existing IDs (duplicates removed automatically)
6. A success message confirms the number of IDs injected

Store IDs can never accidentally merge — each cell value is parsed as an independent token validated against digits-only before being accepted.

**Example:**
- Division IDs: `29` (INCLUDE)
- Banners: select `cedar_market` and `blueharbor` from the dropdown

→ SQL output:
```sql
WHERE a.division_id = 29
  AND a.store_banner IN ('cedar_market','blueharbor')
```

> Banners are automatically lowercased in the SQL output.

> Banner spellings are validated against `reference_data/banners.txt`. A warning appears if an unrecognized banner is entered, but it doesn't block you.

---

## 11. OR-Group Targeting

For more complex audience logic, use **OR Groups** (inside the targeting expander per row, under "🔗 Division + Banner/Store OR groups").

OR groups let you combine multiple Division+Banner+Store combinations with OR logic.

**Example — target division 29 cedar_market/blueharbor OR division 33 redwood_fresh/meadowlane:**

Group 1:
- Division IDs: `29` (INCLUDE)
- Banners: `cedar_market, blueharbor` (INCLUDE)

Group 2:
- Division IDs: `33` (INCLUDE)
- Banners: `redwood_fresh, meadowlane` (INCLUDE)

→ SQL output:
```sql
WHERE ((a.division_id = 29 AND a.store_banner IN ('cedar_market','blueharbor'))
  OR (a.division_id = 33 AND a.store_banner IN ('redwood_fresh','meadowlane')))
```

Click **＋ Add OR group** to add more groups. Click **✕** to remove a group.

---

## 12. Custom JOINs per Row

Developers can add extra SQL JOINs per row (inside the "🔗 Custom JOINs" sub-expander).

**Two modes:**

**Structured JOIN** — Fill in fields:
- Join type: `INNER JOIN`, `LEFT JOIN`, etc.
- Table path: `project.dataset.table`
- Alias: `b`
- ON clause: `a.household_id = b.household_id`

→ SQL output:
```sql
INNER JOIN project.dataset.table b ON a.household_id = b.household_id
```

**Free-text JOIN** — Paste any raw SQL JOIN block directly.

---

## 13. Targeting Notes (per row)

Each row has a **"ADD custom targeting instructions"** sub-expander where you can write free-text notes for the SQL developer.

These notes are embedded in the exported SQL as a comment block, appearing directly below the `FROM` clause for that row. This applies to **both form rows and SQL template rows** — if a SQL template row has targeting notes, they appear immediately after the row's section header in the export.

**Example targeting note:**
```
Only include customers who opted into digital coupons in the last 30 days.
```

→ SQL output:
```sql
FROM project.dataset.eligible_push_audience a
/*
  Custom Targeting Instructions:
  Only include customers who opted into digital coupons in the last 30 days.
*/
```

Targeting notes are visible in the Developer's **Input Summary** section (collapsible panel listing all rows with notes).

---

## 14. SQL Template Library (Recurring Campaigns)

The **Recurring SQL Template Library** holds pre-built `.sql` files for campaigns that repeat week over week.

**How to use:**
1. In the detail view, find the "Add from SQL Template Library" multiselect
2. Select one or more templates from the dropdown
3. Click **Add Selected Templates** — they appear as `sql` type rows in the editor

**Placeholder substitution:** Template files can contain Jinja2 placeholders like `{{ theme }}`, `{{ message }}`, `{{ title }}`. When you fill in those fields on the row form, the values are injected into the SQL at export time.

**Available placeholders include:** `theme`, `message`, `title`, `campaign_name`, `offer_id`, `offer_id_1`, `offer_id_2`, `offer_id_list`, `wk_id`, `send_date`, plus all BigQuery table paths.

> `{{ offer_id_list }}` produces a SQL-ready quoted list (e.g. `'A','B','C'`) — use it in `IN` clauses. `{{ offer_id_1 }}`, `{{ offer_id_2 }}` etc. give you individual IDs for CASE statements.

**Example template snippet:**
```sql
-- Weekly Circular Ad
INSERT INTO {{ tables.push_allocation }}
SELECT ... WHERE theme = '{{ theme }}'
```

If `theme` is filled in as `Wk16_Mon_WeeklyAd` and the Send Date is a Monday, the export produces:
```sql
-- Weekly Circular Ad
INSERT INTO orchard-demo.messaging.push_allocation_MON
SELECT ... WHERE theme = 'Wk16_Mon_WeeklyAd'
```

> All `.sql` files in the template library use `{{ tables.push_allocation }}` — the day suffix (e.g. `_MON`, `_SAT`) is applied automatically based on the campaign's Send Date.

**Uploading new templates:** A file uploader in the template section lets you add new `.sql` files to the library without leaving the app.

**Reloading from disk:** The **"🔄 Reload SQL from library"** button re-reads template files from disk, picking up any edits made via the Template Editor.

**In-row template picker:** Every row expander contains a **"🗄️ SQL Template"** selectbox at the bottom of the form. This is the recommended way to assign a template after importing a metadata-filled CSV:
1. Import the CSV (with campaign_name, theme, message, title etc. filled in)
2. Open each row expander
3. Choose the appropriate template from the **"🗄️ SQL Template"** dropdown
4. Generate SQL — Jinja2 substitutes the row's field values into the template

Selecting **"— None —"** clears the template and reverts the row to standard form-row INSERT generation.

---

## 15. Row Priority & Sorting

Every row has a **Priority** number that controls its order in the exported SQL file. Lower number = higher priority = appears first.

**Editing priority:**
- The Priority field inside each row expander is editable
- Type a new number and click **"Sort by priority"** to reorder all rows

**Tiebreaker logic:** If two rows share the same priority after an edit, the row you just moved wins the tie.

---

## 16. Removing a Row

In the detail view, find the **"Remove a row"** section. Select the row from the dropdown (rows are labeled by their Campaign Name) and click **Remove Row**.

A confirmation prompt appears — click **Yes, remove** to confirm. Clicking **Cancel** does nothing.

After removal, remaining rows are automatically renumbered.

---

## 17. Validation & Content Warnings

The tool performs multiple checks before you submit or export. Most are **advisory** (warnings, not blockers) — they inform you without stopping the export.

### Submit Validation (User view — blocks submit if failing)
All form rows must have `campaign_name`, `theme`, `message`, and `title` filled in. Missing fields are listed in an expandable error panel.

### Advisory Warnings (shown in expanders — non-blocking)

| Warning | What triggers it | What to do |
|---|---|---|
| **Apostrophe detected** | `'`, `'`, `'` in title or message | Form rows: auto-escaped (no action needed). SQL template rows: verify manually. |
| **[Banner] placeholder** | The literal text `[Banner]` in title or message | Replace with `\|\| marketing_banner \|\|` |
| **Trailing/leading whitespace** | Extra spaces at start or end of title/message | Remove the spaces before submitting |
| **Banner spelling** | Banner name not found in `reference_data/banners.txt` | Check spelling; file may need updating |
| **Theme mismatch** | Theme is missing the `pn_wkNN_YYYY_Day` tracking token, or the token's week number / year / day doesn't match the campaign | Theme must contain a token like `pn_wk33_2026_Wed`; the check validates each component independently |
| **Unfilled placeholder** | `{{ var }}` token still in a SQL template row's field | Fill in the corresponding field (theme, message, etc.) |
| **Rich Push Image / media_url** | Rich Push Image is checked but `media_url` is blank | Fill in the media URL in Optional Fields |
| **PUSHSECTION / pushsection** | Offer Type is `PUSHSECTION` but `pushsection` is blank | Fill in the pushsection field in Optional Fields |

> **The Pre-QC scorecard shows only blockers and advisory warnings.** Checks that pass are not listed — only items requiring attention are displayed.

> **Auto-trim:** Leading and trailing spaces in `message`, `title`, `offer_id`, `theme`, and `banners` fields are trimmed automatically for all rows — including sub-rows inside multi-theme containers. An advisory notice is shown when trimming occurs.

---

## 18. Saving & the Activity Log

### Auto-save
The campaign is saved automatically whenever you:
- Change the status dropdown
- Add/remove a row
- Submit for export

### Last Saved indicator
A `💾 Last saved: HH:MM:SS AM/PM` caption appears below the header fields in the detail view, updating on every save.

### Activity Log
A collapsible **Activity Log** in the User view records lifecycle events with timestamps:

| Event | When it's recorded |
|---|---|
| Created | When the campaign day is first created |
| Opened | When the campaign is opened from the dashboard |
| Saved | On every save |
| Submitted for Export | When the User clicks "Submit for Export" |

---

## 19. CSV Export & Import

### Export grid to CSV
Click **"📥 Export Grid to CSV"** to download all rows as a spreadsheet.

- Saves to the `exports/` folder automatically
- Filename pattern: `PUSH_Wk{WW}_{Day}_grid.csv`  
  Example: `PUSH_Wk16_Mon_grid.csv`
- UTF-8 with BOM encoding (Excel-safe)
- Complex fields (OR groups, custom JOINs) are serialized as JSON strings in the CSV
- `rich_push_image` is exported as **Y** or **N**; on import `Y` restores the checked state

### Import CSV
A **"📤 Import CSV"** file uploader is always visible above the row list, even when there are no rows.

- Accepts UTF-8 or BOM-encoded CSVs
- On an empty campaign: replaces blank rows
- On a campaign with existing rows: appends the imported rows
- Re-importing the same file (same name + size) is detected and skipped to prevent duplicates

---

## 20. SQL Export (Developer)

Developers generate and download the final `.sql` file from the **"Review & Export"** section.

1. Click **"Generate SQL"** — renders all rows into a complete SQL script
2. Review the output in the text area
3. Click **"⬇️ Download .sql"** (orange button) to download

**Filename pattern:** `PUSH_Wk{WW}_{Day}.sql`  
Example: `PUSH_Wk16_Mon.sql`

The file is also automatically saved to the `sql_exports/` folder on disk.

### What the SQL file contains:
1. **Preamble** — Table variable declarations, TRUNCATE
2. **Campaign INSERTs** — One block per row, in priority order
3. **Priority block** — TRUNCATE + INSERT into `push_priority`
4. **Finalization** — DELETE duplicates, CREATE `PUSH_Allocation_Final`
5. **Counts / QC tail** — Count queries, Content QC, Archive INSERT

> **Day-specific tables:** All four key tables in the generated SQL automatically include the send-day abbreviation as a suffix. For a Saturday campaign the generated SQL targets `PUSH_Allocation_SAT`, `PUSH_Allocation_Final_SAT`, and `push_priority_SAT` everywhere — including the counts and QC queries at the end of the file.

### Offer type cache invalidation
If a Developer edits an offer type template in `macros/offer_types/`, the cached SQL is automatically cleared the next time **Generate SQL** is clicked, so the export always reflects the latest template.

---

## 21. SQL Preview per Row (Developer)

In the Developer view, a **"SQL Preview (per row)"** section shows the rendered INSERT SQL for each row in an editable text area.

- **Form rows:** Shows the rendered Jinja2 output
- **SQL template rows:** Shows the raw template SQL

**Editing the preview:**
- Changes are stored as **overrides** and used verbatim in the final export
- A **"Reset to generated"** button per row discards overrides and reverts to generated SQL

> Changes to form fields are reflected immediately in the preview on the next render.

---

## 22. SQL Template Editor (Developer)

Found under **"🔧 Edit SQL Template Library"** (Developer only).

This tool lets you convert hardcoded values in `.sql` template files into Jinja2 placeholders without opening a file editor.

**How to use:**
1. Select a template file from the dropdown
2. Select a placeholder token (e.g. `{{ theme }}`)
3. Paste the hardcoded value currently in the file (e.g. `Wk09_Mon_PD`)
4. Click **Apply** — the tool replaces that value with `{{ theme }}` in the file on disk

A read-only preview shows the current file content. **Save** / **Revert** buttons are available.

**Available placeholder tokens:** `theme`, `message`, `title`, `campaign_name`, `offer_id`, `offer_id_1`, `offer_id_2`, `offer_id_list`, `wk_id`, `send_date`

---

## 23. Input Summary (Developer)

The **"Input Summary"** section (Developer only) provides a quick overview of the campaign:

- Summary dataframe of all rows and their key field values
- Quick stats: total rows, form/SQL split, rows with targeting, rows with offer JOINs
- Collapsible targeting notes panel listing rows that have instructions

---

## 24. Pre-Export Warnings (Developer)

Before generating SQL, the Developer view shows advisory warnings:

| Warning | Example |
|---|---|
| Missing `campaign_name` or `theme` | Row 3 has no theme set |
| Duplicate priorities | Rows 2 and 4 both have priority 2 |
| Duplicate themes | Rows 1 and 5 share theme `Wk16_Mon_PD` |
| Unfilled `{{ }}` placeholders | SQL template row has `{{ offer_id }}` but offer_id is empty |
| Apostrophes / [Banner] / whitespace | Same as User view warnings |
| Banner spelling | Banner name not in reference list |
| Theme mismatch | Theme is missing the `pn_wkNN_YYYY_Day` token, or token components (week / year / day) don't match |

These are informational — they don't block SQL generation.

> **Passed checks are not shown.** Only warnings and blockers are displayed — there is no "✅ N check(s) passed" summary.

---

## 25. Role-Based Access — User vs Developer

Switch roles using the **👤 User** / **🔧 Developer** toggle buttons in the sidebar.

> Developer role is protected by a passphrase. You'll be prompted to enter it when switching to Developer. The default passphrase is set in `config/users.yaml`.

### What Users can do:
- Create, open, clone campaign days
- Add/edit/remove rows
- Fill in all form fields
- Set status (up to Submitted; cannot set Exported or Campaign Launched)
- Submit for Export (triggers a confirmation message and redirects to dashboard)
- Export the grid to CSV / import from CSV
- View the Activity Log

### What only Developers can do:
- Generate SQL
- Download the `.sql` file
- View SQL Preview per row (with editable overrides)
- View Input Summary
- View pre-export warnings
- Use the SQL Template Editor
- Use the **📝 Script Editor** (edit core SQL/Jinja2 template files in-app)
- Delete campaign days
- View the active session count in the sidebar
- Access Build Time Analytics
- Add new optional INSERT columns via the Optional Column Schema Editor

---

## 26. Change History (Audit Log)

The **Change History** section (in the detail view) records a reverse-chronological list of every meaningful edit.

Entries are compact and human-readable:

```
[Thu Apr 17 2026 10:23 AM] Row 1: theme → Wk16_Mon_PD_NewOffer
[Thu Apr 17 2026 10:21 AM] Row 2: message → Save big this week!
[Thu Apr 17 2026 10:18 AM] Status changed to: In Progress
```

> `custom_sql` and `row_type` fields are excluded from audit diffs to avoid noise.

---

## 27. Sidebar Utilities

| Element | Description |
|---|---|
| **🕐 PST Clock** | Live current time in Pacific Time — updates on every interaction |
| **Breadcrumb** | Shows current view: Dashboard, open campaign name, Build Analytics, or Script Editor |
| **👤 User / 🔧 Developer** | Role toggle buttons (Developer requires passphrase) |
| **🟢 N active session(s)** | Number of users currently connected (Developer only) |
| **📊 Build Analytics** | Opens the Build Time Analytics view (Developer only) |
| **📝 Script Editor** | Opens the Script Editor view (Developer only) |

---

## 28. Script Editor (Developer)

**Developer only.** Click **"📝 Script Editor"** in the sidebar to open the Script Editor view. This lets you read and edit the core SQL and Jinja2 template files that drive campaign generation — without leaving the browser or touching the file system directly.

### Files available to edit

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

### How to use

1. Click **"📝 Script Editor"** in the sidebar (Developer role required)
2. Select a file from the **"Select script to edit"** dropdown
3. The file's current content is loaded into a large text editor
4. Make your changes
5. Click **"💾 Save"** to write the changes to disk
6. Click **"↩️ Revert"** to discard unsaved edits and restore the on-disk version

### Diff preview

When unsaved changes are present, an expandable **"📄 Show diff"** panel displays a unified diff comparing the on-disk version against your edits — making it easy to spot what changed before saving.

### Editing `banners.txt`

The Store Banners file (`reference_data/banners.txt`) holds one banner name per line (all lowercase). Editing it via the Script Editor adds or removes banners from:
- The **Banners multiselect dropdown** in flat targeting and OR groups
- The **banner spelling check** advisory warnings

> **Cache note:** The banner list is cached for 5 minutes. After saving edits, the dropdown and spell-check will refresh automatically within 5 minutes — or immediately on a fresh page load.

### Important notes

- Changes to `.sql.j2` Jinja2 template files take effect immediately for new SQL generation. If you had already generated SQL before editing a template, click **"Generate SQL"** again to regenerate with the updated template.
- The Script Editor does **not** validate SQL syntax. Test your changes by generating SQL in a campaign detail view after saving.
- This view is separate from the **SQL Template Editor** (§22), which is for editing files in `sql_templates/` (the pre-built recurring campaign library) — not the core generation templates.

---

## 30. Optional Column Schema Editor (Developer)

**Developer only.** Inside any Campaign Detail view, expand **"⚙️ Optional Column Schema (Developer)"** in the Campaign Rows section (between the SQL Template Library and the SQL Template Editor).

This tool lets you add new optional INSERT columns to the campaign form — no code editing or app restart required.

### What it shows

A dataframe listing all loop-managed optional columns with their field name, UI label, SQL alias, type, and escape flag.

### Adding a new column

Fill in the **"Add new column"** form:

| Field | Description |
|---|---|
| **Field name** | Python identifier (e.g. `eventid`) |
| **UI label** | Label shown in Optional Fields (e.g. `Event ID`) |
| **SQL alias** | Column name in the INSERT SELECT list |
| **SQL type** | `text` (string) or `bool` (NULL/TRUE/FALSE) |
| **Apostrophe escape** | Whether to auto-escape `'` in the value |
| **Help tooltip** | Optional caption below the field |

Click **"Add column"** — the new field appears immediately in every row's **📎 Optional Fields** expander with no restart needed. It is also automatically injectable via the **Paste deep-link params** box and the CRF Push Section parser.

> To permanently remove or modify a column, edit `config/optional_columns.yaml` directly.

---

## 29. Multiple Themes (Sub-Rows)

The **Multiple Themes** feature lets you group several related campaign rows under a single priority — each sub-row generates its own INSERT block at the same priority number in the SQL export.

**When to use it:** When you have two or more audience segments (e.g. different banners, divisions, or offer IDs) that should all share the same send priority and are conceptually part of one campaign slot.

### Enabling Multiple Themes

1. Open any standard form row expander
2. Check the **"Multi Theme Campaign"** checkbox at the top
   - If the row already has data filled in, a confirmation dialog appears: **"Enabling Multi Theme Campaign will clear this row's form data and convert it to a container. Continue?"** — click **Yes, convert** or **Cancel**
3. The row converts to a **container**: only Priority and Campaign Name (group label) fields remain

> **Multi Theme Campaign is only available on standard form rows.** SQL template rows (`sql` type) do not have this option.

### Creating Sub-Rows

Inside the container:

1. Set the number of sub-rows using the **"Sub-rows to create"** number input (minimum 1, no maximum)
2. Click **＋ Create Sub-Rows** — the sub-rows appear as nested expanders

Each sub-row is labeled: **`Row {priority}.{n}: {campaign_name}`**  
Example: `Row 3.1: Summer Sale`, `Row 3.2: Summer Sale — Blueharbor Only`

### Editing Sub-Rows

Expand any sub-row to access a **full form** — identical layout to a standard form row:

| Section | Contents |
|---|---|
| **Top strip** | Row Type (read-only: `form`), Offer Type, Offer ID |
| **Required Fields** | `campaign_name *`, `title *`, `message *` (3-column row) |
| **🎯 Theme Variants** | `theme *` — separate section below Required Fields |
| **Rich Push Image** | Checkbox + inline `media_url` warning |
| **📎 Optional Fields** | All 17 optional columns with inline guards + **Paste deep-link params** parser |
| **🎯 Targeting** | Division IDs, Banners, Store IDs (INCLUDE/EXCLUDE) + OR Groups |
| **📝 Targeting Notes** | Free-text targeting instructions → emitted as SQL comment |
| **🔗 Custom JOINs** | Structured or free-text JOIN clauses per sub-row |

### Removing a Sub-Row

Inside the sub-row expander, click the red **✕ Remove Sub-Row N.n** button. A confirmation dialog appears — click **Yes, remove** to delete it, or **Cancel** to abort.

### Disabling Multiple Themes

To revert a container back to a normal row:

1. Uncheck the **"Multi Theme Campaign"** checkbox
2. A confirmation dialog shows: **"Disabling Multi Theme Campaign will delete N sub-row(s) and revert to a normal form row. Continue?"**
3. Click **Yes, revert** (red) to confirm, or **Cancel** to keep the container

> Sub-rows are permanently deleted when reverting. There is no undo.

### SQL Output

Each sub-row generates its **own INSERT block** in the exported `.sql` file. All sub-rows share the **parent container's priority** number.

**Example** — Container at priority 3 with 2 sub-rows:
```sql
--====================================================================
-- Summer Sale — Div 29 (form row)
--====================================================================
INSERT INTO push_allocation ...
WHERE a.division_id = 29 ...

--====================================================================
-- Summer Sale — Blueharbor Only (form row)
--====================================================================
INSERT INTO push_allocation ...
WHERE a.store_banner IN ('blueharbor') ...
```

Both blocks appear at **priority 3** in the push_priority table:
```sql
INSERT INTO push_priority (priority, theme) VALUES
(3, 'Wk16_Mon_Sale_Div29'),
(3, 'Wk16_Mon_Sale_Blueharbor');
```

### CSV Export Behavior

| Item | Behavior |
|---|---|
| **Container row** | **Not exported** — the container itself has no SQL/form data |
| **Sub-rows** | Exported as **flat rows**, each inheriting the parent's priority |
| **CSV import** | Sub-rows import as normal flat form rows (no container grouping preserved) |

### Validation & Warnings

All pre-QC checks run on sub-rows. Error messages use decimal labels matching the UI:

> ⚠️ **Row 3.1 (Summer Sale):** missing **theme, message**

| Behavior | Detail |
|---|---|
| **Duplicate priority** | Sub-rows sharing a priority (e.g. 3.1 and 3.2 both at priority 3) are **not flagged** — this is intentional |
| **All other checks** | Apply normally: required fields, theme mismatch, banner spelling, content warnings, offer type, etc. |

### SQL Preview (Developer)

In the Developer SQL Preview section, a multi-theme container appears as a single grouped expander showing each sub-row's rendered SQL in its own editable text area. Per-sub-row overrides work identically to regular rows — each has its own **Reset to generated** button.

---

## Quick Reference — Export Filename Patterns

| Export type | Filename example |
|---|---|
| SQL export | `PUSH_Wk16_Mon.sql` |
| CSV grid export | `PUSH_Wk16_Mon_grid.csv` |

---

## Quick Reference — Field Auto-Behaviors

| Field | Auto-behavior |
|---|---|
| **Send Day** | Auto-derived from Send Date — read-only |
| **BigQuery table names** | `_MON` through `_SUN` suffix appended to `PUSH_Allocation`, `PUSH_Allocation_Final`, and `push_priority` based on Send Date |
| **Banners** | Always lowercased in SQL output |
| **Apostrophes in title/message** | Auto-escaped to `\'` for form rows |
| **Whitespace in key fields** | Auto-trimmed (including sub-rows in multi-theme containers); advisory notice shown |
| **Status → Campaign Launched** | Auto-set after 8:00 AM PST on send date |
