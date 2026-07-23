# ADR-006: Hosting & HIPAA BAA strategy for the VSO market

- **Status:** Proposed
- **Date:** 2026-07-23
- **Deciders:** Zach Beaudoin
- **Related:** `docs/GOV_CONTRACT_REMEDIATION_PLAN.md` (Phase 4, HIPAA baseline), ADR-005
  (data posture)

> **Note:** BAA scope, covered-service lists, and pricing below were researched on
> 2026-07-23 from vendor and third-party sources and **must be confirmed in writing with
> each vendor before relying on them.** This is an engineering decision record, not legal
> advice.

## Context

Benefits Navigator handles veteran medical/disability PHI (Django + Celery + PostgreSQL +
Redis + object storage). The target market is **VSOs / DAV / county (CVSO) / state
veterans departments / accredited non-profits — not the federal VA directly.** That market
does **not** trigger FedRAMP (FedRAMP is triggered by a *federal agency* consuming a cloud
service), so the compliance anchor is a **HIPAA BAA + SOC 2**, not a federal ATO. See the
remediation plan, Phase 4.

To make the honest claim of handling PHI under the HIPAA Security Rule, every entity that
processes PHI needs a signed BAA — including the **hosting provider** and the **AI
provider**. The app currently runs on **DigitalOcean App Platform + Managed PostgreSQL +
Managed Valkey**, which forced the question this ADR answers: *where should the PHI backend
live?*

## Options considered

### DigitalOcean (current host)
- DO signs a HIPAA BAA (since July 2024) — **but its "Covered Products" list excludes App
  Platform, Managed PostgreSQL, and Managed Valkey**, which is the app's entire current
  stack. DO's guidance prohibits placing ePHI on non-covered products. Hosting HIPAA
  workloads also requires a paid Standard/Premium support plan.
- To be BAA-covered on DO, the app would have to **re-architect onto Droplets/Kubernetes**
  with **self-managed** Postgres and Redis, plus Spaces for uploads — losing the managed-DB
  convenience and adding ops burden.

### AWS (commercial — no GovCloud)
- AWS signs a HIPAA BAA **free and self-service** (accepted in AWS Artifact) covering
  **160+ HIPAA-eligible services**, including **RDS PostgreSQL, ElastiCache (Redis), and
  S3** — i.e. managed Postgres and Redis stay managed *and* covered.
- No FedRAMP / GovCloud needed for the VSO market, so this is ordinary commercial AWS
  pricing (see cost note below), not the six-figure federal path.

### Cloudflare
- Cloudflare signs a BAA **Enterprise-plan only** (no self-serve; not on the $5 Workers
  plan) — custom-quoted, not budget-friendly.
- **No managed PostgreSQL or Redis.** Its data services are D1 (SQLite), KV, R2, Queues,
  Durable Objects, and Hyperdrive (a pooler to an *external* Postgres) — so PHI datastores
  would live off-Cloudflare under a *separate* BAA, fragmenting the compliance boundary.
- Compute: Workers can't run Django/Celery/Tesseract (V8/Pyodide, no native packages).
  Cloudflare **Containers** (GA April 2026) can run the container but is request-driven /
  scale-to-zero with HTTP-only ingress — awkward for a long-running Celery worker — and its
  **HIPAA/BAA eligibility is unconfirmed** in official docs.
- Verdict: **not a viable primary host** here; its natural role is the **edge/CDN/WAF/DDoS/
  TLS layer in front of** a backend hosted elsewhere.

### AI provider (independent of host)
- Anthropic signs a BAA for the **Claude API**, available to standard commercial API
  customers (Primary Owner signs, Sales enables "HIPAA readiness"). Covered models require
  30-day retention, so the BAA and zero-data-retention are mutually exclusive for API use.
  Confirm `claude-sonnet-5` is on the covered-models list. This is solvable on any host.

## Decision

1. **Target market: VSO / non-profit — no FedRAMP.** Compliance anchor = HIPAA BAA + SOC 2.
2. **Host the PHI backend on commercial AWS** (RDS PostgreSQL + ElastiCache Redis + S3 for
   uploads), under AWS's free BAA. This keeps managed databases *and* gets them covered.
3. **Put Cloudflare in front** as the edge/WAF/CDN/DDoS/TLS layer (consistent with how other
   BAS apps already use Cloudflare) — not as the app host.
4. **Sign Anthropic's BAA** for the Claude API (host-independent; do this first — it's free
   and unblocks the honest PHI claim on the AI path).
5. **DigitalOcean is not a fit as-is.** Staying on DO would require re-architecting off App
   Platform + managed DBs onto Droplets with self-hosted Postgres/Redis; AWS gives the same
   managed-DB convenience with a lower-friction BAA, so AWS is preferred.

## Consequences

- **Positive:** free hosting BAA, managed Postgres/Redis stay managed, Cloudflare edge
  security retained, no six-figure FedRAMP path, cost stays in the low tens-to-hundreds/mo
  (see below). Compliance boundary is coherent (one host BAA + one AI BAA).
- **Negative / cost:** a migration off DigitalOcean is real work (infra-as-code, DB
  migration, cutover). Until it happens the app is *not* on BAA-covered infrastructure, so
  **do not onboard a paying VSO with live PHI before the host migration + BAAs are done.**
- **Follow-ups:** (a) confirm DO's current Covered Products list and Anthropic's covered
  models with the vendors; (b) scope the AWS footprint (App Runner/ECS/EC2 + RDS +
  ElastiCache + S3) as IaC; (c) sign AWS + Anthropic BAAs; (d) the Redis TLS verification
  work (this branch) applies on either host.

## Rough cost (commercial AWS, no FedRAMP)

Small footprint, single environment, Cloudflare in front (so no separate ALB needed):

| Component | Rough monthly |
|---|---|
| Compute (small ECS/Fargate or t-class EC2 for web + worker) | ~$20–40 |
| RDS PostgreSQL (db.t4g.micro, single-AZ; ~2× for Multi-AZ) | ~$15–30 |
| ElastiCache Redis (cache.t4g.micro) | ~$12–15 |
| S3 (uploads) + CloudWatch + data transfer | ~$5–15 |
| **Total (single-AZ)** | **~$50–100/mo** |
| Production-grade (Multi-AZ RDS, more headroom) | ~$120–250/mo |

BAA is $0. No GovCloud premium, no ATO. The real recurring compliance spend is **SOC 2**
(~$15–50k/yr) and cyber-liability insurance — tracked in the remediation plan, not here.
