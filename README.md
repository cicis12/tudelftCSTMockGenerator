# CST Studio

A responsive FastAPI + Tailwind CSS app for independent TU Delft Cognitive Skills Test practice. PostgreSQL stores questions, attempts, answers and generation jobs in the Docker deployment. No student signup is required.

## Start with one command

Install Docker Engine/Desktop with Compose v2 and OpenSSL, then run:

```sh
./deploy.sh
```

Open **http://localhost:8000**. The script builds the application, starts PostgreSQL, waits for health checks and seeds **90 original practice questions** (61 maths, 29 logic). It creates a private `.env` file with random credentials on first run and preserves existing credentials and database data on subsequent runs.

Open **http://localhost:8000/admin** and use `ADMIN_PASSWORD` from `.env`. Credentials are intentionally not printed into deployment logs. The default port can be changed with `APP_PORT` in `.env`.

For a public server with a domain pointing to it:

```sh
./deploy.sh --domain cst.example.com
```

This also starts Caddy for automatic HTTPS and secure cookies. DNS must point to the server and inbound TCP 80/443 must be reachable. Use the same command for subsequent updates. The direct application port is bound to localhost; PostgreSQL has no host port. Access the HTTPS URL for the domain deployment, since its secure cookies do not work over plain HTTP.

## What is included

- Maths, logic, or both; maths comes first when both are selected.
- Timed mock sections: 60 minutes maths and 45 minutes logic, with server-enforced deadlines. No pause or time reset on refresh. Expiry advances automatically, including after time offline.
- Configurable mock lengths: up to 24 maths and 20 logic questions by default. Questions are sampled across eligible topic groups and progress from easier to harder; recently correct questions rest for seven days.
- Infinite practice: immediate feedback after each submitted answer, no visible countdown, repeating timed blocks, and automatic section alternation when both are selected. Questions repeat only after the available section pool has been used. Finish anytime for a full review.
- Rules and an explicit readiness checkbox before starting.
- A sticky countdown for timed mocks, answer navigation, flags, automatic saving for timed answers, and an original-PDF link plus rendered formula sheet for maths. Mobile has a formula drawer.
- Complete reviews with all options, the learner’s answer, the correct answer and a worked explanation. Unanswered items are visible and count as zero in the mock score.
- Browser-specific resume and the last 20 completed sessions. Keep cookies to retain access; sessions are not synced across devices. New sessions replace this browser’s existing active session.
- Optional learner accounts sync question progress and cooldowns across devices. Guest practice works without an account; signing in merges guest progress into the account.
- Admin login, question filters, editing, publication/rejection and OpenAI generation with a review queue. Changes to a question do not rewrite existing attempts.
- Admin ZIP export/import for the entire question bank, preserving metadata and publication statuses and skipping duplicate prompts.
- Self-hosted, compiled Tailwind CSS and KaTeX, with no CDN requests at runtime.

## Remembered progress and optional accounts

Correctly answered questions are excluded from newly selected questions for **seven days**, in both modes. Incorrect answers remain eligible. Infinite practice records progress immediately after submission; timed mocks record only final answers after the entire mock ends, so progress cannot reveal answers during a test. Refreshing a page or reopening a result never counts an answer twice or extends its cooldown. Previously completed sessions are incorporated when their browser returns.

When fewer eligible questions remain, a timed mock is shorter. If none remain in a selected section, the setup displays when questions return. Infinite practice moves to the other selected section if it has eligible questions, or finishes with a full review. Correct questions are never recycled early just to fill a mock. Questions already loaded into an active test are not replaced when progress changes on another device.

The workspace shows checked answers, resting questions, section availability and the next review dates. Set `CORRECT_ANSWER_COOLDOWN_DAYS` in `.env` (1–365; default 7) and redeploy to change the interval. The interval is measured from the latest recorded correct answer. Changing the configuration recalculates existing cooldowns from those timestamps.

Use **Sign in → Create account** to register a username and password; no email or external identity service is required. Usernames are case-insensitive, 3–24 letters/numbers/underscores; passwords are 12–128 characters. Sign in on another device connected to the same deployment to retrieve the same question progress. Guest results merge into the account on registration/sign-in, without duplicate counting. Accounts are optional and grant no admin privileges.

Only question progress syncs. Active tests and review history remain browser-specific. Signing out creates a fresh guest workspace and prevents another person using that browser from inheriting the previous account’s history; account progress remains available after signing in again. Finish the current test before managing the account from the test screen. Learner sessions expire after 30 days; there is no email/password-recovery service in this version.

Passwords use salted scrypt (`N=2^15`, `r=8`, `p=3`), one of the [OWASP password-storage configurations](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). Login tokens are stored as hashes in the database and revoked on sign-out. Authentication is rate limited and uses the existing same-origin request protection. Account/progress data is excluded from question ZIP exports. This feature adds new database tables at startup without altering existing question or attempt tables.

## Question generation

In `/admin`, select a section, difficulty, count (1–100) and a model with Responses API structured-output support. Enter an OpenAI API key for that generation, or set `OPENAI_API_KEY` in `.env` and redeploy. `OPENAI_MODEL` sets the default model; the initial value is `gpt-4.1-mini`, and admins can change it per request according to account access.

The app uses the [OpenAI Responses structured output API](https://developers.openai.com/api/docs/guides/structured-outputs), validates each item, deduplicates identical normalized prompts, and saves the results as **drafts**. Requests are split into batches of at most 10 questions, with progress shown in the panel. The request schema enforces the selected section, exact syllabus topic labels and batch size. Invalid or truncated output is retried once per batch (which can incur another API charge); a token-limited retry uses a larger output budget. The panel reports validation fields, truncated output, refusals, authentication, quota and connection failures without exposing response contents or credentials. All batches must validate before any drafts are saved; larger requests can take several minutes and make multiple API calls. Review the mathematics and logic before approving. In the Drafts view, **Approve all** publishes every draft matching the section filter, including drafts beyond the visible list. Published and rejected questions are left unchanged. The full selection is validated before publishing; an invalid draft leaves the bank unchanged. Schema validation does not establish correctness or calibrated difficulty. One generation runs at a time; interrupted jobs are marked failed on server restart and can be retried. This application is designed for one app worker/replica.

API calls incur charges on the supplied key. Keys entered in the panel live only in the current request/background task, are never persisted in browser storage or the database, and are not returned in validation or provider-error messages. Requests use `store=False`. Server-configured keys remain in your `.env`. Generated text and options are escaped before rendering.

The model receives `context/generation-system.md` and the chosen `context/math.md` or `context/logic.md`. You can preview them in the admin panel. Full PDFs and student answers are not uploaded. See [source provenance and scope decisions](context/README.md).

## Export and import questions

In `/admin`, use **Export all questions (.zip)** to download the entire bank, including both sections and all published, draft and rejected questions. The current library filters do not limit the export.

Choose that ZIP under **Question archive**, then click **Import ZIP** to add its questions to another installation or restore missing questions. Imports preserve the options, correct answers, explanations, syllabus references, difficulty, origin, creation time and publication status. Matching normalized prompts are skipped, including duplicates within the archive. Existing questions and student attempts are not changed. The panel reports how many questions were imported or skipped.

Archives contain one UTF-8 `questions.json` file at the ZIP root. Its versioned envelope has `format: "cst-studio-questions"`, `version: 1`, a numeric Unix `exported_at`, and a `questions` array. Each entry contains the `QuestionInput` fields plus `status`, `origin` and numeric Unix `created_at`. Database IDs and fingerprints are not transferred. The ZIP contains no credentials or student data.

The limits are 10 MiB compressed and 50 MiB uncompressed. Archives are read in memory without extracting files to disk. The complete archive and every question are validated before any rows are added; an invalid file leaves the bank unchanged. Only administrators can export or import. Publication statuses are preserved, so importing a published question makes it immediately available to learners.

## Syllabus and mock assumptions

The supplied `/sources` files take precedence over outdated online descriptions:

- Maths: the seven topic groups in `syllabus.pdf`, exact values and no calculator.
- Logic: Chapter 2 of the supplied textbook excluding starred subsections. DNF §2.3.4 is included; starred gates, circuits and binary addition are excluded.
- Timings and permitted materials follow the supplied brochure; the maths formula panel uses `formulas.pdf`.
- Supplementary curriculum checks use [TU Delft’s calculus outline](https://ocw.tudelft.nl/courses/pre-university-calculus/) and the [DelftX course catalogue](https://www.edx.org/learn/calculus/delft-university-of-technology-pre-university-calculus).

The sources do not establish official question counts or an exclusively four-option format. The counts, multiple-choice format, topic sampling, no-negative-marking rule and infinite blocks are explicit mock-app choices. Scores are raw practice accuracy, not official normalized CST scores or admissions predictions. Starter material mixes conceptual questions with parameterized families and is not calibrated to official exam difficulty. This project is not affiliated with or endorsed by TU Delft. Supplied documents retain their existing attribution and licensing.

## Local development without Docker

Python 3.14 is used in the deployment. The local default database is SQLite for convenient development; PostgreSQL is the deployment database.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
cp .env.example .env
```

Edit `.env` to set a random `SECRET_KEY` of at least 32 characters and an `ADMIN_PASSWORD` of at least 12 characters. Do not keep placeholder values. Then:

```sh
uvicorn app.main:app --reload
```

Built CSS and KaTeX files are included, so Node is not needed to run locally. After changing the frontend, install Node and Yarn 1 and rebuild:

```sh
yarn install --frozen-lockfile
yarn build
```

Set `DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DB` to use your own PostgreSQL instance. Use URL-safe database passwords, or percent-encode them in a manually supplied URL. Docker generates a hexadecimal password automatically. `MATH_QUESTION_COUNT` and `LOGIC_QUESTION_COUNT` control mock sizes, capped by the eligible published pool. Restart/redeploy after configuration changes. `COOKIE_SECURE=true` requires HTTPS.

## Verification

```sh
pip install -r requirements-dev.txt
pytest -q
playwright install chromium
python scripts/browser_smoke.py
```

The API suite uses an isolated temporary database and covers grading, answer privacy, timing/expiry, sequential sections, infinite question recycling, browser ownership, CSRF, admin review, snapshot preservation, question archives, accounts, cross-device progress, cooldown expiry and mocked generation. The browser script starts and stops an isolated server, tests desktop and mobile learner flows plus admin editing/publication, and writes screenshots to ignored `artifacts/`. No test calls the paid OpenAI API.

## Operations

```sh
# Logs and status
docker compose logs --tail=100 app
docker compose ps

# Stop while preserving data
docker compose down

# Database backup
docker compose exec -T db pg_dump -U cst cst > cst-backup.sql

# Restore into a suitable empty database
docker compose exec -T db psql -U cst cst < cst-backup.sql
```

For the HTTPS deployment, add `-f compose.yml -f compose.https.yml` and set `CST_DOMAIN` to the hostname when managing its proxy. Keep `.env` and backups private. Removing the `postgres_data` volume deletes questions and attempts. Initial schema creation and idempotent seed loading run at startup; future schema changes need a database migration before deployment. The current release uses no external job queue, so server restarts interrupt in-flight generation without publishing partial output.

`GET /health` checks database connectivity. Student data is owned by a signed, HTTP-only, SameSite cookie. Admin authorization expires after eight hours, mutations require same-origin request protection, and login attempts are rate limited. No paid API credentials are needed for normal practice.

## Project layout

```text
app/                 FastAPI routes, database models, session engine, original seed bank
app/static/          Responsive UI, compiled Tailwind, self-hosted KaTeX
context/             Curated generation instructions and source provenance
sources/             User-supplied reference PDFs
scripts/             Asset build, source extraction and browser verification
tests/               API and generation regression tests
compose*.yml         PostgreSQL/app deployment and optional HTTPS proxy
deploy.sh            Single-command deployment
```
