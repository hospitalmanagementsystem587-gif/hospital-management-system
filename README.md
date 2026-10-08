# Hospital Management System

A hospital operations system for a single hospital, covering OPD, IPD,
pharmacy, and billing workflows. The application uses Django templates and the
Django ORM backed by PostgreSQL.

## Implemented modules

| Module | Description |
| :--- | :--- |
| **Patients (OPD)** | Multi-step registration, auto-generated MRN, document vault uploads |
| **Appointments** | Slot scheduling, doctor queues, no-show tracking |
| **Consultations** | Clinical notes, vitals, diagnosis, follow-up dates |
| **Prescriptions** | Digital prescriptions linked to pharmacy inventory |
| **Pharmacy** | Batch inventory, dispensing from prescription, OTC sales, stock receipts |
| **Billing** | Itemised invoices, multiple payment methods, receipts, voids, adjustments |
| **Inpatient (IPD)** | Ward and bed management, admission dossiers, MLC flag, advance deposit ledger, discharge summaries |
| **Patient Documents** | Scanned upload (prescription, lab report, insurance, photo ID) per patient |

## Production deployment

| Component | Details |
| :--- | :--- |
| **Edge / CDN** | Cloudflare Pages proxy (`vedant-hospital-app.pages.dev`) |
| **Web origin** | Render web service, Python 3.12, Gunicorn + WhiteNoise |
| **Database** | Supabase PostgreSQL (connection-pooler port 6543, `aws-0-ap-south-1`). `DATABASE_URL` is set in Render environment variables; it is not committed. All 12 core migrations are applied. |
| **Error monitoring** | Sentry (`SENTRY_DSN` set in Render env) |
| **Product analytics** | PostHog EU (`POSTHOG_KEY` set in Render env) |
| **Traffic analytics** | Cloudflare Web Analytics beacon |

> **Never commit `DATABASE_URL`, `DJANGO_SECRET_KEY`, or any other secret.**
> Never share production credentials in reports, issues, or documentation.

## Development setup

Requirements: Python 3.12 or newer and pip. PostgreSQL is the target environment
for staging and production. For local development convenience, SQLite is used by
default if `DATABASE_URL` is omitted. To run against PostgreSQL locally or in CI,
set `DATABASE_URL` in `.env`.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

If `.env` already exists, do not overwrite it; merge the required settings from
`.env.example` into it. Open http://127.0.0.1:8000/ for the home page and
http://127.0.0.1:8000/health/ for the health check.

## Configuration

Settings are read from environment variables, with `.env` loaded for local
development. `.env.example` contains only local placeholders. Set
`DJANGO_SECRET_KEY` to a unique secret and set `DJANGO_DEBUG=false` outside local
development. Set `DJANGO_ALLOWED_HOSTS` to a comma-separated host list when
deploying.

`CSRF_TRUSTED_ORIGINS` should include every origin that proxies requests to the
Django origin (e.g. Cloudflare Pages). Set via `DJANGO_CSRF_TRUSTED_ORIGINS`.

### Public SEO and HTTPS

Set `PUBLIC_SITE_URL` to the canonical public origin (for example,
`https://www.example.com`). Canonical, sitemap, structured-data, and social
preview URLs use this configured value and never trust the inbound Host header.
The public sitemap is available at `/sitemap.xml`; `/robots.txt` references it
and excludes private application routes. Set `GOOGLE_SITE_VERIFICATION` only to
the token issued for the production property by Google Search Console.

After HTTPS is working end-to-end through the trusted proxy, enable
`DJANGO_SECURE_SSL_REDIRECT`. Introduce HSTS gradually with
`DJANGO_SECURE_HSTS_SECONDS`; enable subdomains/preload only after confirming
that every subdomain supports HTTPS. `SECURE_PROXY_SSL_HEADER` expects the
trusted proxy to replace, rather than append to, `X-Forwarded-Proto`.

Search Console operations remain deployment tasks: verify the production URL,
submit `<PUBLIC_SITE_URL>/sitemap.xml`, inspect the homepage, and monitor Page
Indexing, Core Web Vitals, impressions, clicks, CTR, and query position. Code
readiness does not guarantee indexing or ranking.

For PostgreSQL, use a URL such as:

```dotenv
DATABASE_URL=postgresql://hospital:change-me@localhost:5432/hospital
```

Never commit `.env`, production credentials, uploaded files, local databases, or
patient data.

## Development commands

```sh
python manage.py check
python manage.py test
ruff check .
ruff format --check .
```

Runtime and development dependencies are pinned in `requirements.txt` and
`requirements-dev.txt`; update pins intentionally and verify them with CI.

## Staff accounts

Create the first administrator interactively; the application has no default
credentials or public staff-registration page:

```sh
python manage.py migrate
python manage.py bootstrap_hospital
python manage.py createsuperuser
```

Sign in at `/accounts/login/` and use Django Admin at `/admin/` to create
individual staff accounts and profiles. Assign role groups only through the
server-side admin; deactivate accounts with Django's `is_active` field rather
than deleting them. Local password-reset emails use the console backend. With
`DJANGO_DEBUG=false`, SMTP is configured for Resend using `RESEND_KEY` and
`RESEND_FROM_EMAIL`; set the latter to a verified sender before staging use. No
email is sent by the test suite.

The application has server-side login throttling (5 failures per IP/username
locks the pair for 10 minutes). Configure and verify edge-level rate limiting
under KAN-16 before real patient data is handled.
See [docs/security.md](docs/security.md).

The admin, staff, store, patient, and agent host boundaries are documented in
[docs/portal-architecture.md](docs/portal-architecture.md). They all use this
same Django backend, database, and authorization system; `/api/v1/` remains the
host-neutral Android API.

After creating the initial administrator, run `python manage.py bootstrap_hospital`
to create the singleton hospital settings placeholder, four curated role groups,
and document-number sequences. Replace the placeholder hospital name and review
the managed permissions before staff onboarding. Rerunning the command safely
reapplies code-defined role permissions; change `core/roles.py` rather than
editing those permissions manually. It does not create users. Configure
departments, visit types, services, payment methods, suppliers, and medicines in
Django Admin. See [docs/roles-and-permissions.md](docs/roles-and-permissions.md).
Tax, discount, refund, and pharmacy pricing policies remain subject to the open
decisions in `docs/decisions.md`.

## Known gaps before production use with real patient data

- KAN-16: Edge-level rate limiting and security hardening not verified
- KAN-18: Backup, restore, and operational runbook not completed
- KAN-22: Operational dashboards and management reports not built
- KAN-24: Infrastructure observability (alerts, uptime checks) not configured
