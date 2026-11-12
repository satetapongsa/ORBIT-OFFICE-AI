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
   backend port. Behind another load balancer configure `set_real_ip_from`.
