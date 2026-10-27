# CineSubz metadata scraper — beginner deployment

This project collects catalogue metadata and the URLs that a movie page publicly labels as download/watch/server links. It **does not download media files**, click countdown buttons, follow redirects, or visit external download destinations.

## Important first step

Before scraping, review CineSubz's terms and `https://cinesubz.net/robots.txt`, and obtain permission if required. The scraper fails closed when robots.txt cannot be read or disallows the requested page. It uses a delay (minimum 2 seconds) between requests. It does not bypass CAPTCHAs, login walls, anti-bot controls, or redirect/countdown systems.

The site's HTML can change. Selectors are intentionally broad; check the first test results before increasing limits.

## What's included

- Flask dashboard protected by `DASHBOARD_PASSWORD`
- PostgreSQL persistence; unique movie URLs and unique movie/link pairs
- Separate Render background worker, so jobs continue after you close the dashboard
- Test mode (up to 3 catalogue pages and 10 new movie details)
- Bounded larger batches, configurable through environment variables
- CSV/JSON movie export and CSV published-link export
- No link destination fetching; external URLs are stored as text only

## Deploy to Render

1. Create a GitHub repository and upload all files in this folder.
2. In Render, choose **New → Blueprint**, connect that repository, and deploy `render.yaml`.
3. Render will ask for `DASHBOARD_PASSWORD` because it is marked `sync: false`. Set a long, unique password. Also set `FLASK_SECRET_KEY` to a separate random secret in the web service's environment if desired.
4. Replace the `USER_AGENT` value with a descriptive name and a contact email you control in both services.
5. The Blueprint creates a web service, a background worker, and PostgreSQL. Render's current service setup is documented at https://render.com/docs/blueprint-spec and https://render.com/docs/web-services.
6. Open the dashboard's `onrender.com` URL and log in.
7. Start with **Test**. Wait for the worker to complete, refresh the dashboard, and review the job error and saved rows.
8. If the site disallows automated access, stop; do not try to bypass the restriction.

## Render cost note

The Blueprint uses starter web/worker services and a small managed database plan. Render pricing and free-tier rules can change; review current prices before deploying. You can instead run locally first.

## Local testing

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set a long `DASHBOARD_PASSWORD` in `.env`, and ensure the site permits your requests. Start two terminals:

```bash
python app.py
```

```bash
python worker.py
```

Open http://127.0.0.1:5000. For local development only, the database defaults to SQLite if `DATABASE_URL` is omitted.

## How to increase limits

For larger batches, change `MAX_PAGES_PER_JOB` and `MAX_DETAILS_PER_JOB` in Render's environment settings. Each job remains bounded; repeat jobs to continue. Use conservative limits and only after the small test works.

## Troubleshooting

- **Job fails immediately with `PermissionError`:** robots.txt disallows the page or could not be read. Stop and request permission; don't bypass.
- **No movie records:** the site may have changed its markup, the catalogue pagination might use a different control, or robots rules may block it. Inspect the HTML manually and adjust only for permitted public pages.
- **Database connection failure:** check Render's `DATABASE_URL` environment variable and that web/worker share the same database.
- **Dashboard login fails:** check `DASHBOARD_PASSWORD`; redeploy/restart after changing it.
- **No links saved:** link labels/context may not match the current site's published labels. Do not add redirect automation or click countdown links.
