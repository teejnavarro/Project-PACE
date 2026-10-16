# P·A·C·E — Precision Audience Campaign Engine

**A campaign request comes in. A reviewed, ready-to-run audience script comes out.**

At fictional grocery retailer **Orchard & Tide**, campaign teams often coordinate audience details, message copy, timing, and technical requirements across spreadsheets and handoffs. P·A·C·E brings that work into one place: people enter campaign details, check them before submission, and prepare consistent scripts for mobile **push notifications** and **RCS messages**.

This portfolio edition uses a fictional retailer, sample locations, and placeholder database tables. It demonstrates the product workflow; its sample SQL is not connected to a real company or production data.

## Why It Matters

- **Fewer handoff gaps:** campaign details, audience rules, and message content stay together instead of being scattered across files and conversations.
- **Issues caught earlier:** built-in checks flag missing information, inconsistent dates, suspicious targeting, and other common mistakes before a script is exported.
- **More repeatable work:** reusable templates and campaign-day tracking make recurring sends easier to prepare and review.
- **Clearer accountability:** status history, activity logs, and change summaries show what is ready and what still needs attention.
- **A safer review path:** users prepare and submit work; developer tools provide SQL preview, editing, and export controls.

## How It Works

1. Create a campaign day and set its planned send date.
2. Add one or more campaign messages, with audience selection and any optional content.
3. Review the built-in quality checks and resolve anything that needs attention.
4. Submit the campaign for review; an authorized developer can inspect and export the generated SQL.
5. Track progress from the dashboard and compare recurring campaigns with prior sends.

The same workflow supports different message shapes, including single-message campaigns and richer card-based RCS messages. Audience selection can combine location, store, and inclusion or exclusion rules.

## What the Project Demonstrates

- A complete workflow from planning through review and export.
- Form-based editing for campaigns with many fields and audience rules.
- Reusable SQL templates and configurable output columns.
- CSV import/export for spreadsheet-based collaboration.
- A request-spreadsheet converter, change history, and build analytics.
- Automated tests for SQL generation, data handling, and screen rendering.

## Try It Locally

This is a developer-run demo rather than a hosted service. To explore the interface, install Python 3.11 or later and run:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
streamlit run app/streamlit_app.py
```

The demo Developer passphrase is `demo`. Sample database settings are fictional, so generated SQL is for demonstration and review only.

## For Developers

The app is built with Python and Streamlit. SQL is composed from Jinja2 templates; campaign data is stored locally as JSON. The PUSH and RCS channels have separate configurations and templates, while sharing the dashboard, storage patterns, and quality-check workflow.

Run the test suite with:

```powershell
python -m pytest
```

Main folders: `app/` contains application code and screens; `push/` and `rcs/` contain channel-specific configuration and templates; `reference_data/` contains fictional sample lists; `tests/` contains automated checks.
