# Deploying for free: Oracle Cloud Always Free

Oracle's *Always Free* tier includes an ARM (Ampere A1) VM with up to **4 CPUs and 24 GB RAM, free with no
time limit**. That runs the whole stack (app, Postgres, Prometheus, Alertmanager, Grafana and the SRE bot)
comfortably. CI publishes multi-arch images (amd64 + arm64), so the same images run here.

Total cost: **$0**. Oracle asks for a card at sign-up for identity checks, but Always Free resources are
not charged.

## 1. Create the VM (about 10 minutes, one time)

1. Sign up at <https://www.oracle.com/cloud/free/>. Pick a home region close to you; it can't be changed
   later, and A1 capacity varies by region.
2. Console → **Compute → Instances → Create instance**:
   - **Image:** Canonical Ubuntu 24.04
   - **Shape:** Change shape → Ampere → `VM.Standard.A1.Flex`, **2 OCPU / 12 GB** (any size up to 4/24 is free)
   - **Networking:** keep the default VCN, *Assign a public IPv4 address* = yes
   - **SSH keys:** *Generate a key pair for me* → **download the private key** (you'll need it twice)
   - Create. If you get "Out of capacity", try another availability domain or retry later. This is common
     with A1 instances.
3. Note the instance's **Public IP address**.

## 2. Open the ports

Oracle blocks traffic in two places, and both need opening.

**Cloud firewall:** Instance → Subnet → Default Security List → *Add Ingress Rules*:

| Source CIDR | Protocol | Destination port | For |
|---|---|---|---|
| `0.0.0.0/0` | TCP | `8080` | SettleWatch app + ops console |
| `0.0.0.0/0` | TCP | `3000` | Grafana |

(Port 22 for SSH is open by default.)

**VM firewall:** Oracle's Ubuntu image ships restrictive iptables rules. SSH in and run the setup below.

## 3. Install Docker on the VM

```bash
chmod 600 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@<PUBLIC_IP>

# on the VM:
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8080 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 3000 -j ACCEPT
sudo netfilter-persistent save
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit
```

## 4. Make the images public

GitHub → your profile → **Packages** → `settlewatch` → *Package settings* → *Change visibility* → **Public**.
Do the same for `settlewatch-sre-bot`. This lets the server pull without a login.

## 5. Add repository secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Value |
|---|---|
| `DEPLOY_HOST` | the VM's public IP |
| `DEPLOY_USER` | `ubuntu` |
| `DEPLOY_SSH_KEY` | full contents of the downloaded private key file, including the BEGIN/END lines |

Optional, for real Jira tickets: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`.

Then create an environment: **Settings → Environments → New environment → `production`**. Optionally add
yourself as a required reviewer, which gives you a change-approval gate before every deploy.

## 6. Deploy

Repo → **Actions → Deploy to server → Run workflow** (tag `latest`). The workflow copies the Compose files,
pulls the images, starts everything and waits for `/actuator/health` to report `UP`.

Load demo data once (1M rows is fine on 12 GB):

```bash
ssh -i <key> ubuntu@<PUBLIC_IP> 'cd settlewatch && docker compose -f docker-compose.yml \
  -f docker-compose.prod.yml --profile seed run --rm seed'
```

Optional, to keep the dashboards moving for anyone who visits:

```bash
ssh -i <key> ubuntu@<PUBLIC_IP> 'cd settlewatch && docker compose -f docker-compose.yml \
  -f docker-compose.prod.yml --profile load up -d loadgen'
```

## 7. Links for your CV and README

- App and ops console: `http://<PUBLIC_IP>:8080`
- Grafana dashboard: `http://<PUBLIC_IP>:3000` (anonymous read-only viewing is on)

## Notes

- **Chaos endpoints are public on a demo box.** Anyone can hit `/api/admin/chaos/*`. That's fine for a
  portfolio demo, but mention in interviews that production would put them behind auth or remove them.
- **Grafana admin password:** set a repository secret, or add `GRAFANA_ADMIN_PASSWORD=...` to
  `~/settlewatch/.env` on the server. It defaults to `change-me`.
- Oracle may reclaim Always Free instances that sit idle (very low CPU) for 7 days. Running the
  load generator avoids that.
