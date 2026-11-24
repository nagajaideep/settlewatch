# Deploying to AWS (free plan credits)

New AWS accounts get **$100 in credits at sign-up, plus up to $100 more** for completing onboarding tasks
(e.g. launching an EC2 instance). On the **Free plan** you are **never charged**: when the credits run out
or 6 months pass, the account pauses instead of billing your card. One small EC2 VM runs the *whole*
stack (app, Postgres, Prometheus, Alertmanager, Grafana, SRE bot) for well under that budget.

## 0. Sign up (India)

1. Go to <https://aws.amazon.com> → *Create an AWS account*.
2. Choose the **Free plan** (not Paid). This is what guarantees no charges.
3. Indian addresses are served by **AWS India (AISPL)**, which bills in INR and accepts **RuPay, Visa,
   Mastercard and Amex** credit/debit cards. Verification is a refundable **₹2** charge with a redirect to
   your bank's OTP page. A RuPay card such as super.money works because this is a domestic
   transaction.
4. If the account still says "Complete your registration" after verification, wait a few hours. If it
   persists, open an AWS Support case (free).

## 1. Budget alarm (2 minutes, do this first)

Billing → **Budgets → Create budget → Zero spend budget** (or a $5 monthly budget) with your email.
You'll get an email if anything ever starts costing real money.

## 2. Launch the VM

EC2 → region **Asia Pacific (Mumbai) ap-south-1** → **Launch instance**:

| Setting | Value |
|---|---|
| Name | `settlewatch` |
| AMI | Ubuntu Server 24.04 LTS (x86_64) |
| Instance type | **`t3.small`** (2 vCPU, 2 GB). Pick one marked *Free tier eligible*; `t3.small` fits the stack |
| Key pair | Create new → RSA → `.pem` → **download it** |
| Network | Allow SSH from **My IP**; add rules for TCP **8080** and **3000** from `0.0.0.0/0` |
| Storage | 20 GB gp3 |

Approximate cost in Mumbai: `t3.small` about $16/month, plus public IPv4 about $3.6/month and 20 GB gp3
about $2/month, so **~$22/month** from credits. $100 covers about 4.5 months running 24/7, and the full $200
covers the 6-month plan. **Stop the instance when you're not demoing** to make credits last much longer.
You pay only for storage while it's stopped. Note that the public IP changes on stop/start unless you
attach an Elastic IP.

## 3. Install Docker on the VM

```bash
chmod 400 ~/Downloads/settlewatch.pem
ssh -i ~/Downloads/settlewatch.pem ubuntu@<PUBLIC_IP>

# on the VM:
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
# 2 GB swap: headroom for Java + Postgres + Grafana on a 2 GB machine
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
exit
```

(Unlike Oracle, the Ubuntu AMI has no extra OS firewall. The security group from step 2 is enough.)

## 4. Make the images public

GitHub → your profile → **Packages** → `settlewatch` and `settlewatch-sre-bot` → *Package settings* →
*Change visibility* → **Public**.

## 5. Repository secrets and environment

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Value |
|---|---|
| `DEPLOY_HOST` | the instance's public IPv4 |
| `DEPLOY_USER` | `ubuntu` |
| `DEPLOY_SSH_KEY` | full contents of the `.pem` file, including the BEGIN/END lines |

Optional, for real Jira tickets: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`.

Then **Settings → Environments → New environment → `production`**. Adding yourself as a required
reviewer gives you an ITIL-style change-approval gate before every deploy.

## 6. Deploy

Repo → **Actions → Deploy to server → Run workflow** (tag `latest`, or a commit SHA to roll back).
It copies the Compose files, pulls the images, starts everything and waits for `/actuator/health`.

Seed demo data once (500k rows suits a 2 GB machine):

```bash
ssh -i ~/Downloads/settlewatch.pem ubuntu@<PUBLIC_IP> 'cd settlewatch && SEED_ROWS=500000 \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile seed run --rm seed'
```

Optional, to keep the dashboards moving: add `--profile load up -d loadgen` the same way.

## 7. Your links

- App and ops console: `http://<PUBLIC_IP>:8080`
- Grafana: `http://<PUBLIC_IP>:3000` (anonymous read-only; admin password from `GRAFANA_ADMIN_PASSWORD`
  in `~/settlewatch/.env`, default `change-me`)
- Run a drill live in an interview: `curl -XPOST 'http://<PUBLIC_IP>:8080/api/admin/chaos/failure-rate?rate=0.5'`,
  then watch the Grafana panels turn red and the SRE bot open a ticket a few minutes later.

## Notes

- The chaos endpoints are public on a demo box. Production would put `/api/admin/**` behind auth.
- Check **Billing → Free Tier / Credits** occasionally to see remaining credit and days left.
