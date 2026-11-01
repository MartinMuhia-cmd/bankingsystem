# Harborline Demo Banking

A fictional, local-only online banking simulator with a consistent burgundy/red/white theme, login, account overview, simulated deposits, simulated withdrawals, and transaction history. It uses **raw SQLite SQL**, not an ORM.

## Important safety notes

- This is a demo, not a bank, and is not affiliated with Wells Fargo or any financial institution.
- All balances and money movements are simulated. No real payment, deposit, withdrawal, or bank connection exists.
- Run locally only. The Flask development server is bound to `127.0.0.1`; do not expose it to the public internet.
- Use a unique demo password that is not used on any real service. Do not use real banking credentials.
- Before any production use, obtain a professional security review and replace the demo transaction flow with authorized provider integrations, robust ledger/reconciliation controls, production session management, monitoring, and compliance procedures.

## Requirements

- Python 3.10+
- `python3-venv` package on Debian/Ubuntu

## Quick start (Linux)

```bash
cd burgundy-banking-demo
chmod +x run.sh
./run.sh
```

On first run, the script creates a virtual environment, installs Flask, and copies `.env.example` to `.env`. Edit `.env` and set:

- `FLASK_SECRET_KEY` to a long random secret
- `DEMO_USERNAME` to your local demo username
- `DEMO_PASSWORD` to a strong, unique demo password
- `DEMO_DISPLAY_NAME` to the name shown in the UI

Then run `./run.sh` again and open `http://127.0.0.1:5000`.

The database and first demo user are initialized on the first start. The demo password is stored as a password hash. If you change `DEMO_USERNAME` or `DEMO_PASSWORD` after the database user has already been created, those changes do not automatically reset the existing user. For a fresh reset, stop the app and remove `banking_demo.sqlite3`, then start it again. This resets all demo data.

## Manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env before starting
python app.py
```

## Included features

- Responsive sign-in page and customer dashboard
- Fictional checking and savings accounts with seeded demo balances
- Deposit form with server-side validation
- Withdrawal form with ownership checks and insufficient-funds protection
- SQLite transactions (`BEGIN IMMEDIATE`) to serialize balance-changing operations
- Unique transaction references and searchable recent activity
- CSRF token validation on POST forms
- Password hashing, HTTP-only session cookies, and same-site cookie policy
- Consistent design tokens in `static/styles.css`

## Current demo limitations

This intentionally does not implement real transfers, payment rails, bank APIs, SMS/email verification, account recovery, multi-factor authentication, full double-entry general ledger, external payment webhooks, or a production admin panel. The balance table is a simplified demo ledger. Do not use it to hold or move real funds.
