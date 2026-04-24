Deployment Plan (Budget & Performance Options)
==============================================

Scope: DigitalOcean App Platform with Django, Celery, OCR, and OpenAI-backed tasks. Two profiles below: cost-optimized and performance-focused.

Shared defaults
---------------
- Secrets/env: `DJANGO_SETTINGS_MODULE`, `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_MAX_TOKENS`, `USE_X_SENDFILE=true` (when behind proxy), `MEDIA_URL`, `SPACES_BUCKET`, `SPACES_ENDPOINT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.
- Proc/commands:
  - Web: `gunicorn benefits_navigator.wsgi:application --workers 3 --threads 2 --timeout 60`.
  - Worker: `celery -A benefits_navigator worker -Q default,ai,notifications -c 2 -Ofair --max-tasks-per-child=100`.
  - Beat (optional separate component): `celery -A benefits_navigator beat`.
- Health: `/health/` (fast) and `/health/?full=1` (deeper). Add liveness checks for worker by touching Redis and simple task enqueue.
- Storage: Use DO Spaces for user uploads; serve via signed URLs/X-Accel. Keep staticfiles in built image or DO CDN.
- DB: Postgres (managed). Enable SSL, set connection limits, and add `CONN_MAX_AGE`/pgbouncer if needed.
- Broker: Redis (managed). Separate DB index for Celery; enable ACL/SSL.

Cost-optimized profile
----------------------
- Web: 1 x Basic droplet (1 vCPU, 1–2 GB) App Platform component.
- Worker: 1 x Basic droplet (1–2 vCPU). Concurrency 2; keep queues combined if low volume.
- Beat: Run on worker with `-B` (if reliability acceptable) or tiny separate worker.
- Postgres: Smallest managed (e.g., 1 vCPU/1GB). Use automatic backups.
- Redis: Smallest managed (512MB). Use for Celery + cache.
- Spaces: Standard storage; no CDN unless traffic requires.
- Knobs:
  - Increase HTMX polling intervals (5–10s) to reduce web load.
  - Cap OpenAI tokens and use `gpt-4o-mini`/`gpt-3.5` where acceptable.
  - Limit concurrent OCR/AI tasks (`-c 2`) to avoid CPU thrash.
  - Turn on rate limits for auth endpoints (already in accounts views).
- Observability: App Platform logs + basic metrics on queue depth and worker CPU/mem; alerts when task age > 2 minutes or Redis/DB errors spike.

Performance-focused profile
---------------------------
- Web: 2–3 x Professional droplets (2–4 vCPU) with autoscale enabled; keep sticky sessions off (stateless).
- Worker pools:
  - AI/OCR queue: 2 x 4 vCPU workers, `-Q ai -c 4–6`, higher memory for PyMuPDF/Tesseract.
  - Fast queue: 1–2 x 2 vCPU workers, `-Q default,notifications -c 4`, isolates email/notifications.
  - Beat: Dedicated tiny worker for stable schedules.
- Postgres: Managed 2–4 vCPU with pgbouncer; enable autoscaling storage; tune for ~200 connections.
- Redis: Managed 1–2GB with high-availability; separate logical DBs for cache vs. Celery if desired.
- Spaces: With CDN; serve media via signed URLs and X-Accel to offload web nodes.
- Knobs:
  - Enable Django caching for public/marketing pages and fragment caching for heavy templates.
  - Shorten status polling intervals but consider SSE/websockets for live updates.
  - Add request timeouts/backoff on OpenAI calls; set per-user/org rate limits and quotas.
  - Use `USE_X_SENDFILE` with Nginx/DO proxy for large downloads.
- Observability: Centralized logs + metrics (request latency, error rates, queue depth, OpenAI latency, OCR duration). SLOs: <300ms p95 for GET pages, <2m p95 for AI task completion.

Rollout checklist
-----------------
1) Migrate media to Spaces; set bucket policy and test signed URLs.
2) Move DB to managed Postgres; run migrations; set `CONN_MAX_AGE` and SSL.
3) Move broker to managed Redis; update Celery config; test enqueue/dequeue.
4) Split components: web, worker, (beat). Configure queues and concurrency per profile.
5) Add health checks and alerts (task age, queue depth, OpenAI error rate).
6) Verify rate limits and AI consent enforcement are enabled in settings/views.
7) Load test: parallel uploads + AI tasks to size worker pool; adjust concurrency.
8) Enable autoscale (performance profile) or set manual scale-up playbook (budget).
