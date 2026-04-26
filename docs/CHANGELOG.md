# Changelog

## 2026-04-26 — Railway production deploy

- `c43b6f7` fix(worker): align beat schedule task names with `@shared_task name=` declarations
- `e5a882e` fix(worker): import task submodules so Celery autodiscover registers them
- `eabd2c2` fix(deploy): make nginx `API_HOST` configurable via envsubst
- Deployed all 5 services to Railway production (web, worker, frontend, Postgres, Redis)
- Frontend live: https://frontend-production-a3db.up.railway.app
- API live: https://web-production-15d76.up.railway.app

## 2026-04-25 — feature/payout-engine merged (87 tests passing)

- `b65677d` feat: merge feature/payout-engine — sub-5 through sub-7 complete
- `fef4271` docs(readme): quickstart, arch overview, deployed URL, reading order
- `2f83dda` docs(explainer): 9 sections referencing real code paths + EXPLAIN ANALYZE
- `6c94007` feat(deploy): Makefile
- `636e17f` feat(deploy): docker-compose with postgres + redis + web + worker + beat + frontend
- `694ec99` feat(deploy): frontend Dockerfile + nginx SPA + api proxy
- `d88b197` feat(deploy): backend Dockerfile
- `12c289d` chore(frontend): smoke verification + lint clean
- `7e467fb` feat(frontend): feature components + dashboard wiring
- `5aee23e` feat(frontend): presentational components — pure props/JSX, no I/O
- `63b6fc4` feat(frontend): hooks — polling, balance, payouts, transactions, create-payout, merchant
- `430e1d7` feat(frontend): utils — Indian INR formatting + timestamp + uuid
- `2722994` feat(frontend): api client + typed endpoints + idempotency-key injection
- `299157e` feat(frontend): vite + react + ts + tailwind scaffold
- `9f8ae22` feat(stress): concurrency harness for senior-signal demo
- Sub-1 through Sub-7 complete; 87 tests passing against real PostgreSQL

## 2026-04-25 — DocOps initialized

- saahilbasak DocOps initialized; docs/ graphify-out/ .claude/skills/ created
- git init + GitHub repo created
- graphify installed with Claude Code hooks
