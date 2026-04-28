# Projectin — Aggressive Dip Buying Agent

Autonomous trading agent for US equities. Scans 8 high-beta symbols daily at 15:45 ET, enters on red-day dips, exits via 2% stop / 10% take-profit.

**Backtest results (Sep–Dec 2025):** +6.58% avg monthly | +17.69% best month | −4.16% worst month

---

## Architecture

```
Oracle Cloud VPS (or Render)
  └── Python agent  ──writes──▶  Supabase (trades, symbols, heartbeat)
                                      ▲
                               GitHub Pages
                               (log viewer, auth via Supabase)
```

- **Agent**: runs as a systemd service, restarts automatically on crash
- **Supabase**: stores trades, active symbols, agent status — free tier (500 MB)
- **Frontend**: static GitHub Pages site — login required to view logs
- **Cron**: weekly log cleanup + Supabase keepalive

---

## Strategy parameters (do not change without backtesting)

| Parameter | Value | Notes |
|-----------|-------|-------|
| Symbols | SOXL, SMCI, MARA, COIN, MU, AMD, NVDA, TSLA | Loaded from Supabase `symbols` table |
| Entry time | 15:45 ET | Daily, market must be open |
| Stop loss | 2% | Below entry |
| Take profit | 10% | Above entry |
| Trailing stop | 2% | Activates after entry |
| Max positions | 2 | Concurrent |
| Position size | 50% equity | Per position |
| AI filter | Groq Llama 3.3 70B | Optional confirmation |

---

## Remote Deployment

### Hosting options (pick one)

| Option | Credit card? | Always-on? | Setup |
|--------|--------------|------------|-------|
| **Render Web Service + UptimeRobot** ★ | No | Yes (with HTTP ping) | Easiest |
| **GitHub Actions** | No (repo must be public) | Cron-based | Medium |
| **Oracle Cloud ARM VPS** | Yes (verification only) | Yes | Most powerful |
| **Fly.io / Google Cloud e2-micro** | Yes (verification only) | Yes | Medium |

★ Recommended if you don't have a credit card. Free, never sleeps, 5 minutes of setup.

### Step 1 — Create accounts (always required)

| Service | URL | Cost | Purpose |
|---------|-----|------|---------|
| Supabase | supabase.com | Free | Log storage + auth |
| GitHub Pages | github.com | Free | Log viewer frontend |
| UptimeRobot | uptimerobot.com | Free | Pings the agent every 5 min (Render option only) |

---

### Step 2 — Supabase setup

1. Create project at [supabase.com](https://supabase.com) → name it `projectin`
2. Go to **SQL Editor** and run:

```sql
-- Trades log
create table trades (
  id          bigserial primary key,
  ts          timestamptz default now(),
  symbol      text,
  action      text,
  entry_price numeric,
  stop_loss   numeric,
  take_profit numeric,
  exit_price  numeric,
  pnl_dollars numeric,
  pnl_percent numeric,
  exit_reason text,
  confidence  numeric,
  reasoning   text,
  executed    boolean default false,
  order_id    text
);

-- Active symbols (loaded by agent at startup)
create table symbols (
  id             bigserial primary key,
  symbol         text unique not null,
  is_active      boolean default true,
  added_by       text default 'manual',
  added_at       timestamptz default now(),
  notes          text,
  total_trades   int default 0,
  winning_trades int default 0,
  total_pnl      numeric default 0
);

-- Agent heartbeat (single row, id=1)
create table agent_status (
  id             int primary key default 1,
  last_heartbeat timestamptz,
  is_running     boolean,
  equity         numeric,
  open_positions jsonb
);
insert into agent_status values (1, now(), false, 0, '[]');

-- Row Level Security: authenticated users can read, agent writes via service_role key
alter table trades       enable row level security;
alter table symbols      enable row level security;
alter table agent_status enable row level security;

create policy "auth read trades"       on trades       for select using (auth.role() = 'authenticated');
create policy "auth read symbols"      on symbols      for select using (auth.role() = 'authenticated');
create policy "auth read agent_status" on agent_status for select using (auth.role() = 'authenticated');
```

3. Go to **Authentication → Users → Add user** — create your login (email + password)

4. Go to **Project Settings → API** and copy:
   - `Project URL` → `SUPABASE_URL`
   - `anon public` key → `SUPABASE_ANON_KEY`
   - `service_role` key → `SUPABASE_SERVICE_KEY` (keep private — server only)

---

### Step 3 — Environment variables

Copy `.env.example` to `.env` and fill in all values:

```bash
cp .env.example .env
```

Required variables:

```env
# Alpaca (paper trading) — https://app.alpaca.markets
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Groq (AI filter) — https://console.groq.com
GROQ_API_KEY=your_groq_key

# Supabase — https://supabase.com → Project Settings → API
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...   # service_role — server only, never in frontend
SUPABASE_ANON_KEY=eyJ...      # anon — safe for GitHub Pages frontend
```

---

### Step 4 — Seed Supabase with initial data

Run once after creating the tables (from your local machine or the server):

```bash
source .venv/bin/activate
python scripts/seed_db.py
```

This inserts the 8 core symbols with `is_active=true` and creates the `agent_status` row.

---

### Step 5A — Deploy to Render Web Service + UptimeRobot (recommended, no CC)

Render's free Web Service sleeps after 15 min without HTTP traffic. The agent already includes a tiny `/health` endpoint that activates when it detects a `PORT` env var. UptimeRobot pings it every 5 min — the service stays alive forever, free.

**1. Render setup:**

1. Go to [render.com](https://render.com) → sign up with GitHub
2. **New +** → **Web Service** (NOT Background Worker)
3. Connect repo `gudair/projectin`
4. Configure:
   - **Runtime**: Python 3
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `python -m cli.main --aggressive`
   - **Instance type**: **Free**
5. Under **Environment**, add every variable from `.env`:
   - `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL`
   - `GROQ_API_KEY`
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`
   - **Do NOT set `PORT`** — Render injects it automatically
6. Click **Create Web Service**. Wait for the first deploy (~3 min).
7. Copy the public URL Render assigns: `https://projectin-xxxx.onrender.com`

**2. Verify the health endpoint:**

```bash
curl https://projectin-xxxx.onrender.com/health
# {"status":"ok"}
```

**3. UptimeRobot setup (keeps the service awake):**

1. Sign up at [uptimerobot.com](https://uptimerobot.com) → free tier
2. **+ Add New Monitor**:
   - Monitor Type: **HTTP(s)**
   - Friendly Name: `projectin-agent`
   - URL: `https://projectin-xxxx.onrender.com/health`
   - Monitoring Interval: **5 minutes** (the free-tier minimum)
3. Save.

That's it. UptimeRobot now pings every 5 min → Render never spins it down.

**4. Seed the DB** (one-time, from your local machine):

```bash
source .venv/bin/activate
python scripts/seed_db.py
```

---

### Step 5B — Deploy to GitHub Actions (no CC, repo must be public)

Two scheduled workflows cover the full US market day. The agent is stateless (loads positions from Alpaca on startup), so the restart between jobs is safe.

**1. Make the repo public** (or accept ~$10/month in Actions minutes for private repos):
   - GitHub repo → Settings → General → scroll to **Danger Zone** → Change visibility

**2. Add secrets** at repo Settings → Secrets and variables → Actions → **New repository secret**.
   Add each variable from `.env` with the same name:
   - `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL`
   - `GROQ_API_KEY`
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`

**3. The workflow file is already at** `.github/workflows/trading-agent.yml`. Once secrets are set, the next push activates it. To test immediately: Actions tab → Trading Agent → **Run workflow**.

**4. Seed the DB** (one-time, from your local machine):

```bash
source .venv/bin/activate
python scripts/seed_db.py
```

---

### Step 5C — Deploy to Oracle Cloud (most powerful, requires CC)

**Provision the VM:**
1. Sign in at [cloud.oracle.com](https://cloud.oracle.com)
2. Create → Compute → Instance → **VM.Standard.A1.Flex** (ARM, Always Free)
   - Shape: 4 OCPUs, 24 GB RAM
   - OS: Ubuntu 22.04
   - Add your SSH public key

> If your Oracle Cloud account is rejected, try from a different network/device or use option 5A or 5B above.

**Deploy the agent:**

```bash
ssh ubuntu@YOUR_SERVER_IP

git clone https://github.com/gudair/projectin.git
cd projectin
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

nano .env   # paste your env vars
python scripts/seed_db.py

# systemd service (auto-restart on crash)
sudo cp deploy/projectin.service /etc/systemd/system/
sudo nano /etc/systemd/system/projectin.service   # adjust paths if needed

sudo systemctl daemon-reload
sudo systemctl enable projectin
sudo systemctl start projectin

sudo journalctl -u projectin -f   # tail logs

# Cron jobs (cleanup + Supabase keepalive)
crontab -e   # paste deploy/crontab.txt contents
```

---

### Step 6 — GitHub Pages frontend

1. Create a new repo: `projectin-logs-ui` (can be public)
2. Copy `frontend/index.html` to that repo's root
3. Edit the two constants at the top of the `<script>` block:

```js
const SUPABASE_URL  = 'https://YOUR_PROJECT_ID.supabase.co';
const SUPABASE_ANON = 'YOUR_ANON_KEY';
```

4. In repo Settings → Pages → Source: **Deploy from branch `main` / `/ (root)`**
5. Your viewer will be at `https://gudair.github.io/projectin-logs-ui/`

---

## Running locally (development)

```bash
source .venv/bin/activate
python -m cli.main --aggressive
```

Requires `.env` with all variables set. The agent logs trades to `logs/trades/` and mirrors them to Supabase if configured.

---

## Symbol management

Symbols are stored in the Supabase `symbols` table. The agent loads `is_active=true` rows at startup. If Supabase is unreachable, it falls back to the 8 hardcoded symbols.

**Add a symbol:**
```sql
-- In Supabase SQL Editor
insert into symbols (symbol, is_active, added_by, notes)
values ('PLTR', true, 'manual', 'Added after backtest confirmation');
```

**Remove a symbol** (non-destructive):
```sql
update symbols set is_active = false where symbol = 'SMCI';
```

**Discovery candidates**: the `discovery.py` module writes the top 10 daily movers to the `symbols` table as `is_active=false`. Review them in the Supabase Table Editor and set `is_active=true` to activate. The agent picks them up on next restart.

> Do not activate discovery candidates without backtesting first. The automated weekly scanner showed −0.29% avg vs +6.58% for the hardcoded set.

---

## Maintenance

### View live logs (server)
```bash
sudo journalctl -u projectin -f
```

### Restart agent
```bash
sudo systemctl restart projectin
```

### Stop agent
```bash
sudo systemctl stop projectin
```

### Manual log cleanup (runs automatically via cron on Sundays at 4 AM)
```bash
source .venv/bin/activate
python scripts/cleanup_logs.py
```

### Update code on server
```bash
git pull origin main
sudo systemctl restart projectin
```

### Validate stop/target logic (run before every deploy)
```bash
source .venv/bin/activate && python3 << 'EOF'
from agent.strategies.aggressive_dip import AggressiveDipStrategy, AggressiveDipConfig
config = AggressiveDipConfig()
strategy = AggressiveDipStrategy(config)
closes = [55,54,53,52.5,52,51.5,51,50.5,50,49.5,49,48.5,48,47.5,53.84]
highs = [c * 1.05 for c in closes]
lows  = [c * 0.95 for c in closes]
signal = strategy.generate_signal('TEST', closes, highs, lows, has_position=False)
stop_pct   = ((signal.stop_loss   - signal.entry_price) / signal.entry_price) * 100
target_pct = ((signal.take_profit - signal.entry_price) / signal.entry_price) * 100
assert signal.stop_loss   < signal.entry_price, "STOP ABOVE ENTRY"
assert signal.take_profit > signal.entry_price, "TARGET BELOW ENTRY"
assert abs(stop_pct   + 2.0) < 0.1, f"Stop pct wrong: {stop_pct}"
assert abs(target_pct - 10.0) < 0.1, f"Target pct wrong: {target_pct}"
print(f"Entry: ${signal.entry_price:.2f} | Stop: {stop_pct:+.1f}% | Target: {target_pct:+.1f}%")
print("ALL CHECKS PASSED")
EOF
```

---

## Cron schedule

| Schedule | Job | Command |
|----------|-----|---------|
| Sunday 4 AM | Delete logs > 30 days | `python scripts/cleanup_logs.py` |
| Mon + Fri 10 AM | Supabase keepalive ping | see `deploy/crontab.txt` |

See `deploy/crontab.txt` for the exact entries.

---

## Project structure

```
agent/
├── core/
│   ├── aggressive_agent.py   # Main agent — entry/exit/monitoring loops
│   ├── groq_client.py        # AI filter (Groq Llama 3.3 70B)
│   ├── trade_logger.py       # JSONL trade log + Supabase mirror
│   ├── supabase_logger.py    # Supabase writes (trades, symbols, heartbeat)
│   └── discovery.py          # Daily movers scanner → Supabase candidates
├── strategies/
│   └── aggressive_dip.py     # Signal generation (RSI, dip detection)
alpaca/
├── client.py                 # Alpaca REST API
└── executor.py               # Order execution + risk checks
backtest/
└── daily_data.py             # OHLCV loader (used by live agent)
cli/
└── main.py                   # Entry point: python -m cli.main --aggressive
config/
└── agent_config.py           # AggressiveAgentConfig (strategy params)
deploy/
├── projectin.service         # systemd service file (Oracle Cloud)
└── crontab.txt               # Cron entries (cleanup + keepalive)
frontend/
└── index.html                # GitHub Pages log viewer
scripts/
├── seed_db.py                # One-time Supabase seed (symbols + status)
└── cleanup_logs.py           # Weekly cleanup (JSONL + Supabase rows)
logs/
└── trades/                   # Local JSONL backup (trades_YYYY-MM-DD.jsonl)
```

---

## API keys reference

| Key | Where to get | Used by |
|-----|-------------|---------|
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | app.alpaca.markets → Paper Dashboard | Agent (trading) |
| `GROQ_API_KEY` | console.groq.com → API Keys | Agent (AI filter) |
| `SUPABASE_URL` | Supabase → Project Settings → API | Agent + Frontend |
| `SUPABASE_SERVICE_KEY` | Supabase → Project Settings → API | Agent only (server-side) |
| `SUPABASE_ANON_KEY` | Supabase → Project Settings → API | Frontend only (public) |
