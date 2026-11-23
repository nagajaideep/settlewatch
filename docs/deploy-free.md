# Deploying for free, no credit card: Render + Neon

| Piece | Where | Free plan |
|---|---|---|
| Spring Boot app + ops console | [Render](https://render.com) web service | 512 MB RAM, no card, sleeps after 15 min idle |
| PostgreSQL | [Neon](https://neon.com) | 1 GB storage per project, no card, no expiry |
| Images | GitHub Container Registry (already built by CI) | free for public images |

Render also offers free Postgres, but it is deleted after 30 days. Neon's free database doesn't expire,
which is why it's used here.

**Trade-off:** free hosting runs the core app (APIs, settlement engine, UI, `/actuator/prometheus`), but
not Prometheus, Grafana or the SRE bot, which need a long-running server. Demo those locally with
`docker compose up`, or use the screenshots in the README. Say exactly that in interviews: "the app is live
on Render; the observability stack runs in Docker Compose".

---

## 1. Database: Neon (5 minutes)

1. Sign up at <https://neon.com> with your GitHub account.
2. Create a project: name `settlewatch`, Postgres 16, region close to Render's (e.g. *AWS US East (Ohio)*
   if you'll pick Render Ohio, or *AWS Europe (Frankfurt)* for Render Frankfurt).
3. On the dashboard click **Connect**, and **turn OFF "Connection pooling"**. Flyway's migration lock
   needs a direct connection. You'll see a URL like:

   ```
   postgresql://neondb_owner:AbC123xyz@ep-cool-name-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

   Split it into the three values Render needs:

   | Variable | Value from the example |
   |---|---|
   | `DB_URL` | `jdbc:postgresql://ep-cool-name-123456.us-east-2.aws.neon.tech/neondb?sslmode=require` |
   | `DB_USER` | `neondb_owner` |
   | `DB_PASSWORD` | `AbC123xyz` |

   (`DB_URL` is the part after `@`, prefixed with `jdbc:postgresql://`.)

## 2. Make the image public

GitHub → your profile → **Packages** → `settlewatch` → *Package settings* → *Change visibility* → **Public**.

## 3. App: Render (5 minutes)

1. Sign up at <https://render.com> with GitHub. No card is needed for the free instance type.
2. **New → Web Service → Existing Image**, image URL: `ghcr.io/nagajaideep/settlewatch:latest`
3. Name `settlewatch`, pick a region, Instance type **Free**.
4. **Environment variables:**

   | Key | Value |
   |---|---|
   | `DB_URL` | from step 1 |
   | `DB_USER` | from step 1 |
   | `DB_PASSWORD` | from step 1 |
   | `DB_POOL_SIZE` | `5` |
   | `JAVA_OPTS` | `-Xmx256m -XX:MaxMetaspaceSize=128m -Xss512k -XX:+UseSerialGC -XX:TieredStopAtLevel=1` |

   The `JAVA_OPTS` keep the JVM inside 512 MB. They were tested under a 512 MB / 0.1 CPU limit:
   ~230 MB used.
5. **Advanced → Health Check Path:** `/actuator/health`
6. Create. The first start takes **about 2 minutes** (Render's free CPU is small) while Flyway creates the
   schema. Your URL is `https://settlewatch-xxxx.onrender.com`.

## 4. Load demo data

Repo → **Settings → Secrets and variables → Actions → New repository secret**:
`SEED_DATABASE_URL` = the full Neon URL from step 1 (the `postgresql://...` one).

Then **Actions → Seed database → Run workflow** (default 500,000 trades, about 200 MB, comfortably inside
Neon's 1 GB). No local tools are needed.

## 5. Auto-deploy on every push (optional, but it's real CD)

Render → your service → **Settings → Deploy Hook** → copy the URL. Add it as the repository secret
`RENDER_DEPLOY_HOOK_URL`. From then on, every push to `main` runs tests, builds the image, pushes it to
GHCR and tells Render to redeploy.

## Things to know

- **Sleeps when idle.** After 15 minutes without traffic the service sleeps. The next visit wakes it in
  about 1–2 minutes. Open the link yourself a few minutes before an interview.
- **Chaos endpoints are public** on the demo. That's fine for a portfolio, but production would put
  `/api/admin/**` behind authentication.
- Render free gives 750 instance-hours per month, enough for one service running all month.
- Students: **Azure for Students** gives $100 credit with no card (verify with your college email). A small
  Ubuntu VM there can run the *full* stack with Grafana and the SRE bot, using `docs/deploy-oracle.md`
  from step 3 onwards and the **Deploy to server** workflow.
