# Deploying to AWS (free tier)

The stack runs on one EC2 instance with Docker Compose, using images that CI publishes to GHCR.

> The free-tier `t2.micro`/`t3.micro` has 1 GB of RAM, which is tight for Java, Postgres, Prometheus and
> Grafana together. Add a 2 GB swap file (below), or use a `t3.small` for a smoother demo.

## One-time setup

1. **Launch an instance**: Ubuntu 24.04, `t3.micro`, 20 GB gp3. Download the key pair (`.pem`).
2. **Security group**: allow inbound `22` from your IP, plus `8080` (app) and `3000` (Grafana) from wherever
   you want to demo. Leave Postgres, Prometheus and the bot private; the prod override does not publish them.
3. **Install Docker** (SSH in once):

   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker ubuntu && exit   # log in again for the group change
   sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```

4. **Make the GHCR packages pullable**: after CI first runs on `main`, open each package
   (GitHub → your profile → Packages → `settlewatch`, `settlewatch-sre-bot`) and set visibility to *Public*.
   Otherwise, run `docker login ghcr.io` on the instance with a read-only token.
5. **Repository secrets** (Settings → Secrets and variables → Actions):
   `EC2_HOST`, `EC2_USER` (`ubuntu`), `EC2_SSH_KEY` (contents of the `.pem`). Optional: `JIRA_BASE_URL`,
   `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`.
6. Create an Environment named `production` (Settings → Environments). You can add yourself as a required
   reviewer to get a change-approval gate before each deploy, which is the ITIL change-management step.

## Deploy

Actions → **Deploy to AWS EC2** → Run workflow → tag `latest` (or a commit SHA to roll back).

Seed demo data once:

```bash
ssh ubuntu@<host> 'cd settlewatch && docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile seed run --rm -e SEED_ROWS=200000 seed'
```

(200k rows keeps a micro instance responsive. The benchmarks in the README used 1M on 4 vCPUs.)

## Cost

A `t3.micro` with 20 GB EBS stays inside the 12-month free tier. Stop the instance when you're not
demoing it.
