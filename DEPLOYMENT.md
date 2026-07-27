# Benefits Navigator - Deployment & Operations Guide

## Environments

### Local Development
- **URL:** http://localhost:8000
- **Database:** PostgreSQL via Docker (port 5432)
- **Redis:** Docker (port 6379)
- **Flower (Celery monitor):** http://localhost:5555

### Staging (DigitalOcean App Platform)
- **URL:** https://benefits-navigator-staging-3o4rq.ondigitalocean.app
- **App ID:** `2119eba2-07b6-405f-a962-d40dd6956137`
- **Region:** NYC

---

## Local Development

### Start all services
```bash
docker compose up -d
```

### View logs
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f celery
docker compose logs -f web
```

### Rebuild after code changes
```bash
docker compose build celery && docker compose up -d celery
docker compose build web && docker compose up -d web
```

### Access local database
```bash
docker exec -it benefits_nav_db psql -U benefits_user -d benefits_navigator
```

### Reset usage limits (for testing)
```bash
docker exec benefits_nav_db psql -U benefits_user -d benefits_navigator -c "UPDATE accounts_usagetracking SET documents_uploaded_this_month = 0;"
```

### Environment variables
- File: `.env` (used by docker-compose)
- Key variables:
  - `OPENAI_API_KEY` - Required for AI analysis
  - `FEATURE_ORGANIZATIONS=true` - Enable Path B (VSO Platform)

---

## Staging (DigitalOcean)

### Prerequisites
Install doctl CLI:
```bash
brew install doctl
doctl auth init  # Enter your DO API token
```

### Check deployment status
```bash
doctl apps list-deployments 2119eba2-07b6-405f-a962-d40dd6956137 --output json | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data:
    print(f\"Phase: {data[0].get('phase')}\")"
```

### View logs
```bash
# Web service
doctl apps logs 2119eba2-07b6-405f-a962-d40dd6956137 web

# Worker (Celery — executes tasks)
doctl apps logs 2119eba2-07b6-405f-a962-d40dd6956137 worker

# Beat (Celery — schedules them)
doctl apps logs 2119eba2-07b6-405f-a962-d40dd6956137 beat

# Follow logs
doctl apps logs 2119eba2-07b6-405f-a962-d40dd6956137 worker --follow
```

## Celery Beat — required component

Beat is what runs everything in `CELERY_BEAT_SCHEDULE`: account purges, pilot
data retention, reminder emails, health metrics. **The worker does not start
it.** The deployment ran without a Beat component for months, during which
every scheduled task was silently inert — including the purge that makes the
30-day account-deletion promise true.

`app-spec.yaml.template` now defines a `beat` component. That template is not
the live spec: the authoritative one lives in the DigitalOcean console
(`.do/app.yaml` is gitignored), so **merging the repo change does not by itself
start Beat.** Apply it:

```bash
doctl apps spec get 2119eba2-07b6-405f-a962-d40dd6956137 > /tmp/live-spec.yaml
# add the `beat` worker block from app-spec.yaml.template, keeping the live
# env values, then:
doctl apps update 2119eba2-07b6-405f-a962-d40dd6956137 --spec /tmp/live-spec.yaml
```

Verify it took, in this order:

```bash
doctl apps logs 2119eba2-07b6-405f-a962-d40dd6956137 beat --follow   # expect "beat: Starting..."
curl -H "X-Health-Token: $HEALTH_CHECK_TOKEN" \
  https://<app-host>/health/?full=1 | jq .checks.scheduler
```

`checks.scheduler` reports `unhealthy` until Beat has dispatched something, and
`healthy` with an `age_minutes` under 30 once it is running.

> ⚠️ **First run purges a backlog.** `process_scheduled_account_deletions` runs
> daily at 04:00 UTC and permanently deletes every account whose 30-day grace
> period has elapsed. Because it has never run, that includes *every* deletion
> requested more than 30 days ago. This is the promised behaviour and it is
> irreversible. Before enabling Beat, check the size of the backlog:
>
> ```bash
> python manage.py shell -c "
> from django.contrib.auth import get_user_model; from django.utils import timezone
> from datetime import timedelta
> U = get_user_model()
> print(U.objects.filter(deletion_requested_at__isnull=False,
>     deletion_requested_at__lte=timezone.now()-timedelta(days=U.DELETION_GRACE_DAYS)).count())
> "
> ```
>
> Take a database backup first.

### Force redeploy
```bash
doctl apps create-deployment 2119eba2-07b6-405f-a962-d40dd6956137 --force-rebuild
```

## Gated deploys

Production used to deploy straight from `main`: every component carried
`deploy_on_push: true` and nothing consulted CI. Commit `a6d8f98` shipped with
`Tests: failure`. Nobody bypassed a gate — there wasn't one.

Deploys now go through `.github/workflows/deploy.yml`, which waits for every
check on the merge commit and refuses unless all of them passed. It checks the
*merge commit* rather than trusting branch protection: protection verifies the
PR branch, but squash-merge makes a new commit nothing has run.

### Rollout — four steps, in this order

The order matters in both directions: the workflow must be on `main` before it
can be run by hand, and turning off `deploy_on_push` before the CI path works
would freeze deploys entirely.

**1. Merge the repo change first.** GitHub only offers `workflow_dispatch` for
workflows on the **default branch**, so the Deploy workflow cannot be tested
from a PR branch. Merging is safe: the live spec still has
`deploy_on_push: true`, and the workflow stops short of deploying while
`DEPLOY_VIA_CI` is unset. Every push logs a warning that the gate is not armed.

**2. Add the credentials.** Settings → Secrets and variables → Actions:

| Kind | Name | Value |
|---|---|---|
| Secret | `DIGITALOCEAN_ACCESS_TOKEN` | a DO API token with read + write on Apps |
| Variable | `DO_APP_ID` | `2119eba2-07b6-405f-a962-d40dd6956137` |
| Variable | `DEPLOY_VIA_CI` | `true` — set this **last** |

Or from the CLI (the first prompts, so the token stays out of your shell
history):

```bash
gh secret set DIGITALOCEAN_ACCESS_TOKEN
gh variable set DO_APP_ID --body 2119eba2-07b6-405f-a962-d40dd6956137
gh variable set DEPLOY_VIA_CI --body true
```

Only the token is secret. The app ID is not — it appears in plain text
throughout this file — and calling it a secret would just make it harder to see
in logs when a deploy misbehaves.

**3. Prove the CI path works.** Actions → Deploy → Run workflow. Confirm it
reaches DigitalOcean and the app redeploys. Both paths are briefly live: DO
deploys on push *and* CI deploys after checks. Two deploys is noisy but safe;
a window with neither is not.

**4. Turn off auto-deploy in DigitalOcean.** Only after step 3 works:

```bash
doctl apps spec get 2119eba2-07b6-405f-a962-d40dd6956137 > /tmp/live-spec.yaml
# set deploy_on_push: false on every component, then:
doctl apps update 2119eba2-07b6-405f-a962-d40dd6956137 --spec /tmp/live-spec.yaml
```

After this, the Deploy workflow is the only route to production.

### Verifying the gate

The wait-and-refuse logic was dry-run against two real commits before shipping:

| Commit | Checks | Gate |
|---|---|---|
| current `main` | all green | **deploy** |
| `a6d8f98` | `Run Tests: failure` | **refuse** |

`a6d8f98` is the commit that actually reached production broken.

### If you need to deploy urgently

Run the Deploy workflow by hand — it still enforces the checks. If checks are
genuinely broken and you must ship anyway, deploy from the DigitalOcean console
directly and say so in the incident log. Do not re-enable `deploy_on_push`:
that removes the gate for every future commit, not just the urgent one.

### Connect to staging database
```bash
# Get password from DO Console or use:
# doctl databases get benefits-nav-db --output json
PGPASSWORD=<DB_PASSWORD> psql \
  -h benefits-nav-db-do-user-29214045-0.j.db.ondigitalocean.com \
  -p 25060 \
  -U doadmin \
  -d benefits_navigator
```

### Check/update app spec
```bash
# Get current spec
doctl apps get 2119eba2-07b6-405f-a962-d40dd6956137 --output json

# Update spec (see .do/app.yaml for template)
doctl apps update 2119eba2-07b6-405f-a962-d40dd6956137 --spec .do/app.yaml
```

---

## Managed Services

### Database (PostgreSQL)
- **Host:** benefits-nav-db-do-user-29214045-0.j.db.ondigitalocean.com
- **Port:** 25060
- **User:** doadmin
- **Database:** benefits_navigator
- **SSL:** Required

### Valkey (Redis-compatible)
- **Host:** db-valkey-nyc3-98037-do-user-29214045-0.k.db.ondigitalocean.com
- **Port:** 25061
- **Protocol:** rediss:// (SSL required)

Get connection URL:
```bash
doctl databases connection d13ae1d1-e114-4174-999c-be584026ec14 --output json
```

---

## Environment Variables (Staging)

### App-level (inherited by all components)
| Variable | Type | Description |
|----------|------|-------------|
| DJANGO_SETTINGS_MODULE | Plain | `benefits_navigator.settings` |
| DEBUG | Plain | `False` |
| STAGING | Plain | `True` |
| ALLOWED_HOSTS | Plain | Hardcoded in app.yaml (never use `*`) |
| SECRET_KEY | Secret | Django secret key |
| FIELD_ENCRYPTION_KEY | Secret | PII encryption key (separate from SECRET_KEY) |
| DATABASE_URL | Secret | PostgreSQL connection string |
| REDIS_URL | Secret | Valkey connection string |
| CELERY_BROKER_URL | Secret | Valkey connection string |
| OPENAI_API_KEY | Secret | OpenAI API key |
| SENTRY_DSN | Secret | Sentry error tracking |

> **Security Note:** `ALLOWED_HOSTS` is hardcoded in `.do/app.yaml` to prevent misconfiguration. `FIELD_ENCRYPTION_KEY` must be a dedicated key separate from `SECRET_KEY` for defense in depth.

### Path B Feature Flags
| Variable | Value | Description |
|----------|-------|-------------|
| FEATURE_ORGANIZATIONS | True | Enable organizations |
| FEATURE_ORG_ROLES | True | Role-based permissions |
| FEATURE_ORG_INVITATIONS | True | Team invitations |
| FEATURE_CASEWORKER_ASSIGNMENT | True | Case assignment |
| FEATURE_ORG_ADMIN | True | Admin dashboard |

### Worker-specific (must be set explicitly)
DO App Platform does NOT inherit app-level secrets to workers. These must be set at worker level:
- REDIS_URL
- CELERY_BROKER_URL
- OPENAI_API_KEY

---

## Document & Media Storage

### Storage Locations

| Environment | Storage | Path |
|-------------|---------|------|
| Local | Filesystem | `./media/documents/user_{id}/{uuid}.{ext}` |
| Staging (testing) | Filesystem (ephemeral) | `/app/media/documents/user_{id}/{uuid}.{ext}` |
| Staging/Production (users) | S3 (**required**) | `s3://{bucket}/media/documents/user_{id}/{uuid}.{ext}` |

### Current Configuration

Staging uses local filesystem storage (`USE_S3=False`). Files are stored on the app container's ephemeral filesystem.

> **⚠️ CRITICAL: Ephemeral Storage Limitations**
>
> Files on DO App Platform are **deleted on every deployment**. This means:
> - All uploaded documents are lost when you push new code
> - Users will see "file not found" errors for previously uploaded documents
> - This is acceptable for testing only
>
> **Before any user-facing rollout (including beta/pilot), you MUST:**
> 1. Enable S3 storage (`USE_S3=True`)
> 2. Configure AWS credentials
> 3. Migrate any existing files to S3
>
> See "Enable S3 Storage" section below.

### File Restrictions

| Setting | Value |
|---------|-------|
| Max file size | 50 MB |
| Max pages | 100 |
| Allowed types | PDF, JPEG, PNG, TIFF |

### Enable S3 Storage (Production)

1. Create S3 bucket with private ACL
2. Set environment variables:
```bash
USE_S3=True
AWS_ACCESS_KEY_ID=<key>
AWS_SECRET_ACCESS_KEY=<secret>
AWS_STORAGE_BUCKET_NAME=<bucket-name>
AWS_S3_REGION_NAME=us-east-1
```

### Protected Media Access

Documents are **not** served directly via URL. All access goes through Django views that verify:
- User is authenticated
- User owns the document (or has org access)

Download endpoint: `/claims/document/<pk>/download/`

---

## Health Check Details

### Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `/health/` | Liveness check (load balancer) | `{"status": "ok"}` |
| `/health/?full=1` | Full system health (staff or token) | Detailed JSON, or `403` |

### Reading the full health check

It requires either a staff session or the `HEALTH_CHECK_TOKEN` shared secret, passed in
the `X-Health-Token` header — a header rather than a query parameter so the token stays
out of access logs, proxy logs and browser history. Set `HEALTH_CHECK_TOKEN` in the DO
console for unattended monitoring; leave it unset and only staff can read it.

```bash
curl -H "X-Health-Token: $HEALTH_CHECK_TOKEN" https://your-app.ondigitalocean.app/health/?full=1
```

Unlike the plain liveness check, this request goes through normal host validation, so
call it on a hostname in `ALLOWED_HOSTS` rather than an internal IP.

### Full Health Check Components

The `/health/?full=1` endpoint checks:

| Component | What it checks |
|-----------|----------------|
| Database | PostgreSQL connection (SELECT 1) |
| Redis | Cache read/write test |
| Celery | Worker count, active tasks, queue length |
| Document Processing | Success rate over last 24 hours |
| Failures | Recent processing failure count |

### Response Format
```json
{
  "status": "healthy|degraded|unhealthy",
  "timestamp": "2024-01-15T12:00:00Z",
  "checks": {
    "database": {"status": "healthy", "message": "..."},
    "redis": {"status": "healthy", "message": "..."},
    "celery": {"status": "healthy", "workers": 1, "queue_length": 0},
    "document_processing": {"status": "healthy", "success_rate": 98.5},
    "failures": {"status": "healthy", "total": 0}
  }
}
```

### DO App Platform Health Check Config

```yaml
health_check:
  http_path: /health/
  initial_delay_seconds: 30
  period_seconds: 10
```

The simple `/health/` endpoint is used (not `?full=1`) to avoid heavy checks on every probe.

---

## Scaling

### Current Instance Sizes

| Component | Size | vCPU | RAM | Monthly Cost |
|-----------|------|------|-----|--------------|
| Web | basic-xxs | 0.5 | 512MB | ~$5 |
| Worker | basic-xxs | 0.5 | 512MB | ~$5 |
| Migrate Job | basic-xxs | 0.5 | 512MB | Per-run |

### Celery Concurrency

Current: `--concurrency=2` (2 concurrent tasks per worker)

### Scale Horizontally (More Instances)

Update `.do/app.yaml`:
```yaml
services:
  - name: web
    instance_count: 2  # Increase from 1

workers:
  - name: worker
    instance_count: 2  # Increase from 1
```

Apply:
```bash
doctl apps update 2119eba2-07b6-405f-a962-d40dd6956137 --spec .do/app.yaml
```

### Scale Vertically (Larger Instances)

Available sizes (DO App Platform):
| Slug | vCPU | RAM | Monthly |
|------|------|-----|---------|
| basic-xxs | 0.5 | 512MB | ~$5 |
| basic-xs | 1 | 1GB | ~$10 |
| basic-s | 1 | 2GB | ~$20 |
| basic-m | 2 | 4GB | ~$40 |
| professional-xs | 1 | 1GB | ~$12 |
| professional-s | 1 | 2GB | ~$25 |

Update in `.do/app.yaml`:
```yaml
services:
  - name: web
    instance_size_slug: basic-xs  # Upgrade from basic-xxs
```

### Increase Celery Concurrency

For CPU-bound tasks, increase concurrency:
```yaml
workers:
  - name: worker
    run_command: celery -A benefits_navigator worker -l info --concurrency=4
```

---

## Running Migrations Manually

### Automatic Migrations

Migrations run automatically via the `migrate` PRE_DEPLOY job on every deployment.

### If Migrate Job Fails

1. Check job logs:
```bash
doctl apps logs 2119eba2-07b6-405f-a962-d40dd6956137 migrate
```

2. Run migrations manually via console:
```bash
doctl apps console 2119eba2-07b6-405f-a962-d40dd6956137 web
# Then in the console:
python manage.py migrate --noinput
```

3. Or connect directly to database and run SQL:
```bash
# Generate migration SQL locally
python manage.py sqlmigrate <app_name> <migration_name>

# Then run SQL in staging database
PGPASSWORD=<DB_PASSWORD> psql \
  -h benefits-nav-db-do-user-29214045-0.j.db.ondigitalocean.com \
  -p 25060 -U doadmin -d benefits_navigator \
  -c "<SQL from above>"
```

### Check Migration Status

```bash
doctl apps console 2119eba2-07b6-405f-a962-d40dd6956137 web
# Then:
python manage.py showmigrations
```

---

## Remote Shell Access

### Django Shell (Staging)

```bash
# Open console to web service
doctl apps console 2119eba2-07b6-405f-a962-d40dd6956137 web

# Then run Django shell
python manage.py shell
```

### Run One-Off Commands

```bash
doctl apps console 2119eba2-07b6-405f-a962-d40dd6956137 web

# Examples:
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py check --deploy
```

### Worker Shell

```bash
doctl apps console 2119eba2-07b6-405f-a962-d40dd6956137 worker
```

### Execute Single Command

For quick commands without interactive console:
```bash
# This feature requires DO App Platform CLI support
# Alternative: Use the web console in DO Dashboard
```

### Local Development Shell

```bash
# Django shell
docker compose exec web python manage.py shell

# Database shell
docker exec -it benefits_nav_db psql -U benefits_user -d benefits_navigator

# Celery shell (inspect tasks)
docker compose exec celery celery -A benefits_navigator inspect active
```

---

## Common Issues & Fixes

### AI analysis not saving
**Symptom:** Document shows "completed" but ai_summary is NULL

**Fix:** Ensure `claims/tasks.py` has explicit save before `mark_completed()`:
```python
document.ai_summary = ai_result['analysis']
document.ai_model_used = ai_result['model']
document.ai_tokens_used = ai_result['tokens_used']
document.save(update_fields=['ai_summary', 'ai_model_used', 'ai_tokens_used'])  # This line!
document.mark_completed(duration=duration)
```

### Worker not receiving tasks
**Symptom:** Tasks queued but worker logs show no activity

**Causes:**
1. Worker missing CELERY_BROKER_URL (check worker-level envs)
2. Web service missing CELERY_BROKER_URL (tasks can't be queued)

**Fix:** Ensure both app-level AND worker-level have REDIS_URL and CELERY_BROKER_URL set.

### Invalid OpenAI API key
**Symptom:** 401 error in Celery logs

**Fix:**
- Local: Update `.env` file, then `docker compose down celery && docker compose up -d celery`
- Staging: Update via doctl spec or DO Console

### Celery SSL connection error
**Symptom:** `ValueError('A rediss:// URL must have parameter ssl_cert_reqs...')`

**Fix:** Ensure `settings.py` has SSL config for Celery (already implemented):
```python
if CELERY_BROKER_URL.startswith('rediss://'):
    CELERY_BROKER_USE_SSL = {'ssl_cert_reqs': ssl.CERT_REQUIRED}
```

---

## Rollback Procedures

### Staging (DigitalOcean App Platform)

#### List recent deployments
```bash
doctl apps list-deployments 2119eba2-07b6-405f-a962-d40dd6956137 --format ID,Phase,CreatedAt,UpdatedAt
```

#### Rollback to a previous deployment
```bash
# Get deployment ID from list above, then:
doctl apps create-deployment 2119eba2-07b6-405f-a962-d40dd6956137 --wait
```

> **Note:** DO App Platform doesn't have native rollback. To revert:
> 1. Identify the last working commit in GitHub
> 2. Revert or reset to that commit
> 3. Push to trigger new deployment

#### Quick revert via Git
```bash
# Find the last working commit
git log --oneline -10

# Revert the bad commit (creates new commit)
git revert <bad-commit-hash>
git push origin main

# OR reset to previous state (rewrites history - use with caution)
git reset --hard <good-commit-hash>
git push origin main --force
```

#### Rollback database migrations
If a deployment included a bad migration:
```bash
# Connect to staging database
PGPASSWORD=<DB_PASSWORD> psql \
  -h benefits-nav-db-do-user-29214045-0.j.db.ondigitalocean.com \
  -p 25060 -U doadmin -d benefits_navigator

# Check migration history
SELECT * FROM django_migrations ORDER BY applied DESC LIMIT 10;
```

Then locally:
```bash
# Identify the migration to rollback to
python manage.py showmigrations

# Generate reverse migration SQL (review before running!)
python manage.py sqlmigrate <app_name> <migration_name> --backwards
```

> **Warning:** Always backup the database before rolling back migrations. Some migrations are not reversible.

### Local Development

```bash
# Reset to previous state
git checkout <commit-hash>
docker compose down
docker compose build
docker compose up -d
```

---

## Database Backup & Restore

### Staging (DigitalOcean Managed Database)

#### Automatic Backups
DigitalOcean Managed Databases include automatic daily backups with 7-day retention.

**View backups in DO Console:**
https://cloud.digitalocean.com/databases/benefits-nav-db/backups

#### Manual Backup (pg_dump)
```bash
# Full database backup
PGPASSWORD=<DB_PASSWORD> pg_dump \
  -h benefits-nav-db-do-user-29214045-0.j.db.ondigitalocean.com \
  -p 25060 -U doadmin -d benefits_navigator \
  --format=custom --no-owner \
  -f benefits_navigator_$(date +%Y%m%d_%H%M%S).dump

# Data-only backup (no schema)
PGPASSWORD=<DB_PASSWORD> pg_dump \
  -h benefits-nav-db-do-user-29214045-0.j.db.ondigitalocean.com \
  -p 25060 -U doadmin -d benefits_navigator \
  --format=custom --no-owner --data-only \
  -f benefits_navigator_data_$(date +%Y%m%d_%H%M%S).dump
```

#### Restore from Backup

**Restore to staging (destructive):**
```bash
# WARNING: This will overwrite existing data
PGPASSWORD=<DB_PASSWORD> pg_restore \
  -h benefits-nav-db-do-user-29214045-0.j.db.ondigitalocean.com \
  -p 25060 -U doadmin -d benefits_navigator \
  --clean --no-owner \
  benefits_navigator_20240115_120000.dump
```

**Restore to a fresh database:**
```bash
# Create new database first via DO Console, then:
PGPASSWORD=<DB_PASSWORD> pg_restore \
  -h benefits-nav-db-do-user-29214045-0.j.db.ondigitalocean.com \
  -p 25060 -U doadmin -d benefits_navigator_restore \
  --no-owner \
  benefits_navigator_20240115_120000.dump
```

#### Point-in-Time Recovery
For critical data loss within the last 7 days, contact DigitalOcean support or use the Console to restore from a specific backup point.

### Local Development

#### Backup local database
```bash
docker exec benefits_nav_db pg_dump \
  -U benefits_user -d benefits_navigator \
  --format=custom \
  -f /tmp/local_backup.dump

# Copy from container
docker cp benefits_nav_db:/tmp/local_backup.dump ./local_backup.dump
```

#### Restore to local database
```bash
# Copy backup into container
docker cp ./local_backup.dump benefits_nav_db:/tmp/local_backup.dump

# Restore (destructive)
docker exec benefits_nav_db pg_restore \
  -U benefits_user -d benefits_navigator \
  --clean --no-owner \
  /tmp/local_backup.dump
```

#### Clone staging data to local
```bash
# Dump staging
PGPASSWORD=<DB_PASSWORD> pg_dump \
  -h benefits-nav-db-do-user-29214045-0.j.db.ondigitalocean.com \
  -p 25060 -U doadmin -d benefits_navigator \
  --format=custom --no-owner \
  -f staging_clone.dump

# Restore to local
docker cp staging_clone.dump benefits_nav_db:/tmp/staging_clone.dump
docker exec benefits_nav_db pg_restore \
  -U benefits_user -d benefits_navigator \
  --clean --no-owner \
  /tmp/staging_clone.dump
```

> **Note:** Scrub sensitive data after cloning staging to local if needed.

---

## CI/CD Pipeline

### Current Setup

Deployments are handled automatically by DigitalOcean App Platform:

| Trigger | Action |
|---------|--------|
| Push to `main` | Auto-deploy to staging |
| Pull request | No automated checks (recommended to add) |

Configuration: `.do/app.yaml` with `deploy_on_push: true`

### Deployment Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Push to     │────▶│  DO App      │────▶│  Build &     │
│  main branch │     │  Platform    │     │  Deploy      │
└──────────────┘     └──────────────┘     └──────────────┘
                                                 │
                     ┌───────────────────────────┼───────────────────────────┐
                     ▼                           ▼                           ▼
              ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
              │   Migrate   │            │    Web      │            │   Worker    │
              │   (Job)     │            │  (Django)   │            │  (Celery)   │
              └─────────────┘            └─────────────┘            └─────────────┘
                     │
                     ▼
              PRE_DEPLOY
              (runs first)
```

### Recommended: GitHub Actions Workflow

Create `.github/workflows/ci.yml` to run tests before merging:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  PYTHON_VERSION: "3.11"

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Install dependencies
        run: |
          pip install ruff
      - name: Run linter
        run: ruff check .

  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest-django pytest-cov
      - name: Run tests
        env:
          DATABASE_URL: postgres://test_user:test_pass@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379/0
          CELERY_BROKER_URL: redis://localhost:6379/0
          SECRET_KEY: test-secret-key-not-for-production
          DEBUG: "True"
        run: |
          pytest --cov=. --cov-report=xml -m "not e2e and not slow"
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
          fail_ci_if_error: false

  e2e:
    runs-on: ubuntu-latest
    needs: test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
      redis:
        image: redis:7
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest-playwright
          playwright install chromium --with-deps
      - name: Run E2E tests
        env:
          DATABASE_URL: postgres://test_user:test_pass@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379/0
          SECRET_KEY: test-secret-key-not-for-production
        run: |
          pytest -m e2e --headed=false
```

### Running Tests Locally

```bash
# Unit tests only
docker compose exec web pytest -m "not e2e and not slow"

# All tests including slow
docker compose exec web pytest -m "not e2e"

# E2E tests (requires Playwright)
docker compose exec web pytest -m e2e

# With coverage
docker compose exec web pytest --cov=. --cov-report=html
```

### Branch Protection (Recommended)

Configure in GitHub repo settings (`Settings > Branches > Add rule`):

| Setting | Value |
|---------|-------|
| Branch name pattern | `main` |
| Require pull request | ✓ |
| Require status checks | ✓ (select `lint` and `test` jobs) |
| Require branches up to date | ✓ |
| Include administrators | Optional |

### Manual Deployment

If auto-deploy is disabled or you need to trigger manually:

```bash
# Via doctl
doctl apps create-deployment 2119eba2-07b6-405f-a962-d40dd6956137

# Force rebuild (clears build cache)
doctl apps create-deployment 2119eba2-07b6-405f-a962-d40dd6956137 --force-rebuild
```

### Disable Auto-Deploy

To require manual deployments, update `.do/app.yaml`:

```yaml
services:
  - name: web
    github:
      deploy_on_push: false  # Changed from true
```

Then apply:
```bash
doctl apps update 2119eba2-07b6-405f-a962-d40dd6956137 --spec .do/app.yaml
```

### Monitoring Deployments

```bash
# Watch deployment progress
doctl apps list-deployments 2119eba2-07b6-405f-a962-d40dd6956137 --format ID,Phase,Progress,CreatedAt

# Get deployment details
doctl apps get-deployment 2119eba2-07b6-405f-a962-d40dd6956137 <deployment-id>

# View build logs
doctl apps logs 2119eba2-07b6-405f-a962-d40dd6956137 --type build
```

---

## Key URLs

### Staging
- Home: https://benefits-navigator-staging-3o4rq.ondigitalocean.app
- Health check: https://benefits-navigator-staging-3o4rq.ondigitalocean.app/health/
- Document upload: https://benefits-navigator-staging-3o4rq.ondigitalocean.app/claims/upload/
- Organizations: https://benefits-navigator-staging-3o4rq.ondigitalocean.app/accounts/organizations/

### Local
- Home: http://localhost:8000
- Document upload: http://localhost:8000/claims/upload/
- Organizations: http://localhost:8000/accounts/organizations/
- Flower (Celery): http://localhost:5555
- Django Admin: http://localhost:8000/admin/

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    DO App Platform                       │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   Web       │  │   Worker    │  │   Migrate   │     │
│  │  (Django)   │  │  (Celery)   │  │   (Job)     │     │
│  └──────┬──────┘  └──────┬──────┘  └─────────────┘     │
│         │                │                              │
│         ▼                ▼                              │
│  ┌─────────────────────────────────────────────┐       │
│  │              Valkey (Redis)                  │       │
│  │         (Task Queue & Results)               │       │
│  └─────────────────────────────────────────────┘       │
│         │                                               │
│         ▼                                               │
│  ┌─────────────────────────────────────────────┐       │
│  │           PostgreSQL Database                │       │
│  └─────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

---

## Dual-Path Development

### Path A - Direct-to-Veteran (B2C)
- Freemium model with usage limits
- Individual Stripe billing
- Usage tracking

### Path B - VSO Platform (B2B)
- Organization management
- Role-based access (Admin, Caseworker, Viewer)
- Team invitations
- Case assignment
- Organization billing (future)

Feature flags in `benefits_navigator/settings.py` control which path is active.

---

## Monitoring & Alerting

### Sentry (Error Tracking)

Sentry captures unhandled exceptions and errors in both Django and Celery.

**Configuration:**
- DSN set via `SENTRY_DSN` environment variable
- Only active when `DEBUG=False`
- Integrations: Django, Celery
- PII disabled (`send_default_pii=False`)
- Sample rate: 10% of transactions traced

**Setup Sentry:**
1. Create project at https://sentry.io
2. Get DSN from project settings
3. Set in DO Console: `SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx`

**Alert Configuration (in Sentry Dashboard):**
- Go to Alerts → Create Alert Rule
- Recommended alerts:
  - Error frequency > 10/hour
  - New issue in production
  - Celery task failures

### DigitalOcean Monitoring

DO App Platform provides built-in metrics:

**View in Console:**
https://cloud.digitalocean.com/apps/2119eba2-07b6-405f-a962-d40dd6956137/insights

**Available Metrics:**
- CPU usage per component
- Memory usage per component
- Request latency (p50, p95, p99)
- Request count
- Restart count

**Set Up Alerts:**
1. Go to Settings → Alerts in DO Console
2. Configure thresholds for:
   - CPU > 80%
   - Memory > 80%
   - Restart count > 3

### Health Check Monitoring

For external uptime monitoring, use the health endpoint:

```
URL: https://benefits-navigator-staging-3o4rq.ondigitalocean.app/health/
Expected: {"status": "ok"}
Frequency: Every 1-5 minutes
```

Services: UptimeRobot (free), Pingdom, Better Uptime

---

## Secret Rotation

### When to Rotate

- Immediately if compromised
- After team member departure
- Periodically (recommended: every 90 days for production)

### SECRET_KEY Rotation

1. Generate new key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

2. Update in DO Console (Settings → App-Level Environment Variables)

3. Redeploy to apply:
```bash
doctl apps create-deployment 2119eba2-07b6-405f-a962-d40dd6956137
```

> **Note:** Rotating SECRET_KEY invalidates all existing sessions. Users will need to log in again.

### FIELD_ENCRYPTION_KEY Rotation

Used for encrypting PII (VA file numbers, DOB, etc.). Separate from SECRET_KEY for defense in depth.

1. Generate new key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

2. Update in DO Console (Settings → App-Level Environment Variables)

3. Redeploy to apply:
```bash
doctl apps create-deployment 2119eba2-07b6-405f-a962-d40dd6956137
```

> **Warning:** Rotating FIELD_ENCRYPTION_KEY will make existing encrypted data unreadable. You must either:
> - Re-encrypt all PII data with the new key (requires migration script), or
> - Keep the old key available for decryption during a transition period
>
> For most cases, avoid rotating this key unless it's compromised.

### DATABASE_URL Rotation

1. Reset password in DO Database Console
2. Update `DATABASE_URL` in DO App Console
3. Redeploy

### OPENAI_API_KEY Rotation

1. Generate new key at https://platform.openai.com/api-keys
2. Update in DO Console (both app-level AND worker-level)
3. Revoke old key in OpenAI dashboard
4. Redeploy

### REDIS_URL / CELERY_BROKER_URL Rotation

1. Reset password in DO Database Console (Valkey)
2. Update both `REDIS_URL` and `CELERY_BROKER_URL` at:
   - App-level environment variables
   - Worker-level environment variables
3. Redeploy

### Local Development

Update `.env` file and restart containers:
```bash
docker compose down
docker compose up -d
```

---

## Cost Overview

### Current Staging Costs (Estimated)

| Resource | Type | Monthly Cost |
|----------|------|--------------|
| Web Service | basic-xxs (0.5 vCPU, 512MB) | ~$5 |
| Worker | basic-xxs (0.5 vCPU, 512MB) | ~$5 |
| PostgreSQL | db-s-1vcpu-1gb | ~$15 |
| Valkey (Redis) | db-s-1vcpu-1gb | ~$15 |
| **Total** | | **~$40/month** |

### Production Estimates

| Scenario | Web | Worker | DB | Redis | Total |
|----------|-----|--------|-----|-------|-------|
| Low traffic | basic-xs ×1 | basic-xs ×1 | 1vCPU/1GB | 1vCPU/1GB | ~$50/mo |
| Medium traffic | basic-s ×2 | basic-s ×2 | 2vCPU/4GB | 2vCPU/4GB | ~$150/mo |
| High traffic | professional-s ×4 | professional-s ×4 | 4vCPU/8GB | 4vCPU/8GB | ~$400/mo |

### Additional Costs

| Service | Cost |
|---------|------|
| OpenAI API | ~$0.002/1K tokens (GPT-3.5-turbo) |
| S3 Storage | ~$0.023/GB/month |
| Sentry | Free tier: 5K errors/month |
| Domain | ~$12/year |

### Cost Optimization Tips

1. **Use basic-xxs for staging** - Sufficient for testing
2. **Scale workers based on queue** - Don't over-provision
3. **Monitor OpenAI usage** - Set billing limits in OpenAI dashboard
4. **Use S3 lifecycle policies** - Archive/delete old documents
5. **Review DO bandwidth** - First 1TB outbound free, then $0.01/GB
