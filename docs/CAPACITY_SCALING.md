# Capacity & Scaling Guide

When to scale, what to watch, and how to do it on DigitalOcean App Platform.

---

## Current Configuration (2026-03-26)

| Component | Instance | Count | Key Constraint |
|---|---|---|---|
| Web (Django) | basic-xxs (1 vCPU, 512MB RAM) | 1 | Memory: Django + gunicorn workers |
| Celery Worker | basic-xxs (1 vCPU, 512MB RAM) | 1 | Memory: OCR + OpenAI calls |
| PostgreSQL | Managed DO (smallest) | 1 | Connection pool |
| Redis | Managed DO (smallest) | 1 | Queue depth |

Celery worker concurrency: **2** (two tasks may run simultaneously)

---

## When to Scale

### Celery Worker → Scale UP when:

| Signal | Threshold | Action |
|---|---|---|
| Queue backlog | ≥50 tasks sustained >5 min | Increase concurrency or add instance |
| Task age (p95) | >5 min | Increase concurrency |
| Processing success rate | <90% with OOM in logs | Upgrade to basic-xs |
| OOM kills in DO logs | Any | Upgrade to basic-xs immediately |
| Failure rate | >10/hr sustained | Investigate + scale if bottleneck |

**Fastest fix:** Upgrade instance size before adding instances.

```
basic-xxs (512MB) → basic-xs (1GB) → basic-s (2GB)
```

### Web (Django) → Scale UP when:

| Signal | Threshold | Action |
|---|---|---|
| P95 response time | >2s | Add instance or upgrade |
| Error rate (5xx) | >1% | Investigate then scale |
| Memory usage | >80% | Upgrade instance |

Web is stateless — horizontal scaling (add instances) is safe.

### Database → Scale UP when:

| Signal | Threshold | Action |
|---|---|---|
| Connection pool exhaustion | `FATAL: remaining connection slots reserved` in logs | Increase pool size or upgrade DB |
| Query p95 latency | >100ms on simple queries | Add indexes or upgrade |

---

## How to Scale on DigitalOcean

### Upgrade worker instance size

Edit `app-spec.yaml.template` — change the worker `instance_size_slug`:

```yaml
workers:
  - name: worker
    instance_size_slug: basic-xs  # was: basic-xxs
    instance_count: 1
```

Then deploy:
```bash
doctl apps update <app-id> --spec app-spec.yaml
```

### Add a second worker instance

```yaml
workers:
  - name: worker
    instance_size_slug: basic-xs
    instance_count: 2  # was: 1
```

> With `concurrency=2` and 2 instances, you get 4 concurrent tasks. Watch for
> OpenAI rate limits before scaling past 4 concurrent AI calls.

### Increase Celery concurrency (without instance change)

In the worker run command (DO App Platform env var or spec):
```
celery -A benefits_navigator worker -l info --concurrency=4
```

> Only safe on basic-xs or larger. On basic-xxs, concurrency >2 risks OOM on
> overlapping OCR+LLM calls.

---

## Memory Sizing Rationale

A single document processing task uses roughly:

| Stage | Peak Memory |
|---|---|
| Django worker base | ~80MB |
| PDF file load | 5–20MB (per document) |
| Tesseract OCR | 50–150MB |
| OpenAI request (httpx) | ~20MB |
| **Total peak (one task)** | ~200–270MB |

On basic-xxs (512MB) with `concurrency=2`, two overlapping tasks peak at ~450MB —
leaving very little headroom. A single large document (multi-page scanned PDF) can
exceed 512MB and trigger an OOM kill.

**Recommended minimum for production:** `basic-xs` (1GB RAM) with `concurrency=2`.

---

## OpenAI Rate Limit Considerations

When scaling workers, the bottleneck shifts to OpenAI API rate limits.

Current model: `gpt-3.5-turbo` — default tier limits:
- **TPM (tokens/min):** 90,000 (Tier 1)
- **RPM (requests/min):** 3,500

A single document analysis uses ~2,000–4,000 tokens. At `concurrency=4` across
2 workers (8 concurrent calls), sustained processing could approach rate limits during
peak usage.

**Watch for:** `RateLimitError` spikes in `ProcessingFailure` records after scaling.

---

## Scaling Checklist

Before scaling in production:

- [ ] Check current failure rate: `ProcessingFailure.get_stats()`
- [ ] Check queue depth: `/health/?full=1` → `celery.queue_length`
- [ ] Check DO App Platform logs for OOM kills
- [ ] Review OpenAI usage dashboard for RPM/TPM headroom
- [ ] Update `app-spec.yaml.template` to reflect new config
- [ ] Test in staging first if upgrading to a new instance tier

---

## Related Docs

- `docs/INCIDENT_RESPONSE.md` — Celery worker runbooks
- `docs/FAILURE_TRACKING.md` — failure triage during scaling events
- `.do/app-spec.yaml.template` — full DO App Platform spec
