# ORBIT OFFICE AI — Production deployment

A single Linux host with Docker runs the whole system: Nginx (HTTPS) in front of the Next.js
frontend and the FastAPI backend, a Celery worker and scheduler, PostgreSQL 17 + pgvector,
Redis and MinIO object storage. Only Nginx publishes ports. Everything below is done on the
server unless stated otherwise.

> Read §8 "Known risks" before going live.

## 1. Requirements

| Item | Minimum |
| --- | --- |
| Host | Linux x86-64, 2 vCPU, 4 GB RAM (8 GB with a local AI model elsewhere), 40 GB SSD + room for documents and backups |
| Software | Docker Engine 27+ with the Compose plugin v2.30+, `git`, `openssl` |
| Network | A DNS name (e.g. `office.example.com`) pointing at the host; ports 80 and 443 open; outbound SMTP to your mail provider |
| Certificates | A TLS certificate for that name (Let's Encrypt or your organisation's CA) |

## 2. Configuration (`.env.production`)

```bash
git clone https://github.com/satetapongsa/ORBIT-OFFICE-AI.git /opt/orbit-office
cd /opt/orbit-office
cp .env.production.example .env.production
chmod 600 .env.production
```

Replace every `CHANGE_ME` (generate each secret separately with `openssl rand -hex 32`) and set
`ORBIT_DOMAIN`, `FRONTEND_BASE_URL` (`https://…`), `SMTP_*` and, if wanted, `AI_*`.

The backend **refuses to start** in production when:
- `JWT_SECRET_KEY` is shorter than 32 characters or the development value;
- any secret still contains `CHANGE_ME`, or the database/storage credentials are the
  development defaults;
- `COOKIE_SECURE=false`, `DEBUG=true`, `SEED_DEV_PASSWORD` is set, or `FRONTEND_BASE_URL` is not
  `https://`.

Production defaults that differ from development: API docs off, JSON logs, Secure cookies,
rate limiter **fails closed** (503 when Redis is down), readiness details hidden from the
public (§6).

## 3. TLS certificates

Nginx reads `fullchain.pem` and `privkey.pem` from `TLS_CERT_DIR` (default
`./infra/nginx/certs`, git-ignored).

**Let's Encrypt** (first issue, before Nginx is running):

```bash
sudo certbot certonly --standalone -d office.example.com
sudo mkdir -p infra/nginx/certs
sudo cp /etc/letsencrypt/live/office.example.com/{fullchain,privkey}.pem infra/nginx/certs/
```

Renewal (cron, e.g. weekly) with the webroot Nginx already serves on port 80:

```bash
sudo certbot renew --webroot -w /opt/orbit-office/infra/nginx/acme \
  --deploy-hook "cp /etc/letsencrypt/live/office.example.com/*.pem /opt/orbit-office/infra/nginx/certs/ && docker compose -f /opt/orbit-office/docker-compose.prod.yml --env-file /opt/orbit-office/.env.production exec nginx nginx -s reload"
```

TLS 1.2/1.3 only, HSTS (one year), HTTP redirects to HTTPS.

## 4. First start

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.production ps
```

The `migrate` service applies database migrations, synchronises permissions and system roles,
and creates the storage bucket; the backend starts after it succeeds. Then create the first
administrator (the password is asked twice and never shown or stored in shell history):

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production \
  exec backend python -m app.cli create-admin you@company.com ชื่อ นามสกุล
```

Sign in at `https://office.example.com`, then create departments and people in
"ศูนย์พนักงาน" and adjust roles on "ตั้งค่า". `seed-dev` is refused in production.

## 5. Updates

```bash
cd /opt/orbit-office
bash scripts/backup.sh --prod                 # always back up first
git pull
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

Migrations run automatically (`migrate`). Roll back by checking out the previous release and
restoring the backup taken before the update (migrations are forward-only in production).

## 6. Operations

| Task | Command / place |
| --- | --- |
| Status | `GET https://<domain>/api/v1/health` (overall status only); monitoring sends `X-Health-Token: $HEALTH_CHECK_TOKEN` for component details; administrators see details on "สถานะระบบ" |
| Logs | `docker compose -f docker-compose.prod.yml --env-file .env.production logs -f backend worker` (JSON, rotated 5 × 20 MB per service) |
| Retention clean-up | automatic daily at 03:15 Asia/Bangkok (`beat` service); by hand: `… exec backend python -m app.cli purge --dry-run` then without `--dry-run` |
| Search index | `… exec backend python -m app.cli reindex-documents [--all]` after enabling/changing embeddings |
| Restart one service | `… restart backend` (the worker needs a restart after configuration changes) |

Retention defaults: soft-deleted documents and their files after 30 days, unreferenced stored
files after 24 hours, deleted or idle (180 days) chats, expired sign-in sessions and reset
tokens after 30 days, read notifications after 365 days. Audit logs are never purged.

## 7. Backup and recovery

```bash
bash scripts/backup.sh --prod    # backups/<UTC stamp>/database.dump, files.tar, SHA256SUMS
```

- Schedule it daily (cron, e.g. 02:30) and **copy the folder off the server** (another host or
  object storage); local copies are kept `BACKUP_KEEP_DAYS` (14) days. The files contain
  personal data: store them encrypted with restricted access.
- **Verify** regularly without touching live data (restores into a separate database and
  bucket, then compare or inspect; drop them afterwards):

  ```bash
  bash scripts/restore.sh backups/<stamp> --prod --database orbit_restore_check --bucket orbit-restore-check
  ```

- **Disaster recovery** (replaces all live data; stops the app during the restore):

  ```bash
  bash scripts/restore.sh backups/<stamp> --prod --yes
  ```

  On a new host: install, write a new `.env.production` (new secrets are fine; everyone
  simply signs in again), start the stack, then run the full restore.

Recovery point = the last backup; recovery time ≈ minutes per GB of files.

## 8. Known risks and limitations (production)

1. Single host: no high availability; a host failure means restoring from backup.
2. MinIO uses a community build (`pgsty/minio`, pinned by digest, ADR-013). For long-term
   production prefer managed S3-compatible storage (set `STORAGE_ENDPOINT_URL`, remove the
   `minio` service).
3. The page Content-Security-Policy allows inline scripts (`'unsafe-inline'`), required by
   Next.js without nonces (ADR-050); XSS protection relies on React escaping and on never
   rendering raw HTML.
4. Uploaded files are type-checked and size-limited but not virus-scanned.
5. Scanned (image-only) PDFs are not OCR'd and are not searchable.
6. AI providers receive the prompts and the permitted document passages; use a local provider
   (e.g. Ollama) if data must not leave your servers. The assistant has not been validated
   against every model; small local models may call tools poorly.
7. E-mail delivery depends on your SMTP provider; failed notification e-mails are marked
   `FAILED` and not retried.
8. Backups are only as good as their off-site copy and the last restore test.
9. Rate limits and the readiness policy assume Nginx is the only way in; do not publish the
   backend port. Behind another load balancer configure `set_real_ip_from`. With the front end
   on Vercel (section 9) set `PROXY_SHARED_SECRET` instead.

## 9. Alternative: front end on Vercel, API on Railway (ADR-055)

The Next.js front end can run on Vercel while the API, worker, scheduler, database, Redis and
file storage run elsewhere. The steps below use [Railway](https://railway.com) for the API side
and Cloudflare R2 (or Railway Buckets) for files; any host that runs Docker images works the
same way. Vercel keeps proxying `/api/*` to the API, so the browser still talks to one origin
and the session cookies keep working unchanged.

### 9.1 Railway project

Create one project with these services:

| Service | Source | Settings |
| --- | --- | --- |
| `Postgres` | Railway **pgvector** template (PostgreSQL with the `vector` extension) | — |
| `Redis` | Railway Redis | — |
| `backend` | this GitHub repo | Dockerfile path `infra/docker/backend.Dockerfile` · pre-deploy command `sh -c "alembic upgrade head && python -m app.cli sync-rbac && python -m app.cli ensure-bucket"` · healthcheck path `/api/v1/health/live` · public domain on port `8000` |
| `worker` | same repo, same Dockerfile | start command `celery -A app.workers.celery_app worker --loglevel=INFO -Q default,documents --concurrency=2` · no public domain |
| `beat` | same repo, same Dockerfile | start command `celery -A app.workers.celery_app beat --loglevel=INFO` · no public domain · one replica only |

Shared variables (Project → Variables, referenced by `backend`, `worker` and `beat`):

```
ENVIRONMENT=production
DATABASE_URL=${{Postgres.DATABASE_URL}}      # postgres:// is switched to psycopg automatically
REDIS_URL=${{Redis.REDIS_URL}}
JWT_SECRET_KEY=<openssl rand -hex 32>
PROXY_SHARED_SECRET=<openssl rand -hex 32>   # the same value goes to Vercel
FRONTEND_BASE_URL=https://<your-project>.vercel.app
STORAGE_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
STORAGE_REGION=auto
STORAGE_ACCESS_KEY=<R2 access key id>
STORAGE_SECRET_KEY=<R2 secret access key>
STORAGE_BUCKET=orbit-documents
STORAGE_AUTO_CREATE_BUCKET=false
HEALTH_CHECK_TOKEN=<openssl rand -hex 32>
APP_TIMEZONE=Asia/Bangkok
```

Add SMTP and AI variables from `.env.production.example` when needed. Create the R2 bucket
first and give the access key read/write on that bucket only.

### 9.2 Vercel project

Root directory `frontend`, framework preset Next.js. Environment variables (Production):

```
BACKEND_INTERNAL_URL=https://<backend>.up.railway.app
PROXY_SHARED_SECRET=<the same value as on Railway>
```

Redeploy after changing them: the `/api` rewrite target is fixed at build time.
`frontend/vercel.json` adds the secret to every proxied `/api` request; with
`PROXY_SHARED_SECRET` set, the API refuses requests without it (`403 proxy_required`), so it
cannot be called around Vercel, and the visitor IP for login rate limits and the audit log
comes from Vercel's `X-Vercel-Forwarded-For`.

### 9.3 First administrator and checks

Open a shell in the `backend` service (`railway ssh` or the dashboard) and run:

```
python -m app.cli create-admin admin@company.com Firstname Lastname
```

Then check, in this order: `https://<backend>.up.railway.app/api/v1/health/live` returns
`ok`; `/api/v1/health` called directly returns `403 proxy_required` (the API is closed to
direct calls); the Vercel site shows the sign-in page, you can sign in, upload a document
and see it become searchable (worker), and download it.

### 9.4 Limits of this layout

1. Uploads and the assistant's streamed answers pass through Vercel's proxy; check a 25 MB
   upload and a long answer after the first deploy.
2. Backups: `scripts/backup.sh` targets the Compose stack. Use Railway's Postgres backups
   and R2's bucket tools (or `python -m app.cli storage-export` from the backend shell).
3. Vercel's Hobby plan is for non-commercial use; company use needs Pro.
4. Two providers to watch: Vercel for pages, Railway for everything else.

## 10. Free hosting: Oracle Cloud Always Free + Vercel

The API side runs as the single-host stack (sections 1-7) on an Oracle Cloud "Always Free"
virtual machine; the front end stays on Vercel (section 9.2). A free DuckDNS name and a
Let's Encrypt certificate give the API an HTTPS address. Everything here is free of charge.

### 10.1 Machine

1. Sign up at cloud.oracle.com (a card is asked for identity checks; Always Free resources
   are not billed). Upgrading the account to *Pay As You Go* keeps Always Free resources free
   and stops Oracle reclaiming instances that look idle for 7 days.
2. Compute → Instances → Create: image **Ubuntu 24.04**, shape **VM.Standard.A1.Flex**
   (Ampere, arm64) with 2-4 OCPU and 12-24 GB memory, boot volume 100 GB, upload your SSH
   public key. If the region reports "out of capacity", retry later or pick another
   availability domain. All images used by the stack are published for arm64.
3. Networking → the instance's subnet → Security List → add ingress rules for TCP **80** and
   **443** from `0.0.0.0/0`.
4. Note the instance's public IP.

### 10.2 Name and firewall

1. duckdns.org → sign in → add a subdomain (e.g. `orbit-office`) → set it to the public IP.
   The API address is then `orbit-office.duckdns.org`.
2. On the machine (`ssh ubuntu@<public-ip>`), Oracle's Ubuntu image blocks everything but
   SSH in iptables; open 80 and 443:

   ```bash
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```

### 10.3 Software, certificate, configuration

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && newgrp docker
sudo apt-get install -y certbot git
sudo git clone https://github.com/satetapongsa/ORBIT-OFFICE-AI.git /opt/orbit-office
sudo chown -R ubuntu:ubuntu /opt/orbit-office && cd /opt/orbit-office
sudo certbot certonly --standalone -d orbit-office.duckdns.org
mkdir -p infra/nginx/certs
sudo cp /etc/letsencrypt/live/orbit-office.duckdns.org/{fullchain,privkey}.pem infra/nginx/certs/
sudo chown ubuntu:ubuntu infra/nginx/certs/*.pem
cp .env.production.example .env.production && chmod 600 .env.production
```

In `.env.production` replace every `CHANGE_ME` (`openssl rand -hex 32` for each) and set:

```
ORBIT_DOMAIN=orbit-office.duckdns.org
FRONTEND_BASE_URL=https://<your-project>.vercel.app
PROXY_SHARED_SECRET=<openssl rand -hex 32, the same value goes to Vercel>
```

Start the stack, create the first administrator and set up certificate renewal exactly as in
sections 3 and 4 (`docker compose -f docker-compose.prod.yml --env-file .env.production up -d
--build`, then `create-admin`). The first build on the A1 machine takes several minutes.

### 10.4 Vercel

Project → Settings → Environment Variables (Production), then **Redeploy**:

```
BACKEND_INTERNAL_URL=https://orbit-office.duckdns.org
PROXY_SHARED_SECRET=<the same value as in .env.production>
```

Checks: `https://orbit-office.duckdns.org/api/v1/health/live` answers `ok`;
`https://orbit-office.duckdns.org/api/v1/health` answers `403 proxy_required`; the Vercel site
shows the sign-in page and the administrator can sign in, upload a document and download it.
The DuckDNS address itself is not a usable site (its pages call the API without the proxy
secret); people use the Vercel address.

### 10.5 Upkeep

- Backups: `bash scripts/backup.sh --prod` from a daily cron job; copy `backups/` off the
  machine (section 7). The free tier has no managed backups.
- Updates: section 5 (`git pull` + `up -d --build`), Vercel redeploys from GitHub on push.
- Security updates: `sudo apt-get update && sudo apt-get upgrade` monthly, or enable
  `unattended-upgrades`.
- Limits: one machine, no high availability (section 8); Vercel Hobby is for non-commercial
  use.
