# Tunnel Setup — Running the Backend via Cloudflare

This guide lets your Vercel-hosted frontend talk to the FastAPI backend
running on your Mac, through a public Cloudflare tunnel.

---

## Prerequisites (one-time)

### 1. Install cloudflared
```bash
brew install cloudflare/cloudflare/cloudflared
```

### 2. Install Python deps (if not done yet)
```bash
cd '/Users/samihan/Samihan/the AWSengers'
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 3. Install Ollama + pull the model (if not done yet)
```bash
brew install ollama
ollama pull llama3.1
```

> **Why llama3.1 and not llama3?** The original `llama3` does not support tool/function calling,
> which the Strands agent requires to invoke `check_guardrail` and `run_code`.
> `llama3.1` adds native tool calling. Alternatives if you prefer: `qwen2.5`, `qwen3`, `mistral`.

---

## Every time you want to run the agent

Open **three separate Terminal tabs**.

### Tab 1 — Ollama (local LLM)
```bash
ollama serve
```
Leave this running. It listens on `http://localhost:11434`.

### Tab 2 — FastAPI backend
```bash
cd '/Users/samihan/Samihan/the AWSengers'
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```
You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### Tab 3 — Cloudflare tunnel
```bash
cloudflared tunnel --url http://localhost:8000
```

After ~5 seconds you will see a line like:
```
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
|  https://olive-dragon-abc123.trycloudflare.com                                             |
+--------------------------------------------------------------------------------------------+
```

**Copy that URL** — you will need it for the next step.

> The URL changes every time you restart `cloudflared`.
> Re-paste it in Vercel whenever you restart your tunnel.

---

## Setting the Environment Variable in Vercel

### Option A — Vercel Dashboard (recommended for teammates)

1. Go to **https://vercel.com** and open your project.
2. Click **Settings** → **Environment Variables** in the left sidebar.
3. Click **Add New**.

| Field | Value |
|-------|-------|
| **Name** | `NEXT_PUBLIC_API_URL` |
| **Value** | `https://olive-dragon-abc123.trycloudflare.com` ← paste your URL here |
| **Environments** | ✅ Production  ✅ Preview  ✅ Development |

4. Click **Save**.
5. Go to **Deployments** → find your latest deployment → click the **⋯** menu → **Redeploy**.
   - This is required because `NEXT_PUBLIC_*` variables are baked in at build time.

### Option B — Vercel CLI (faster for solo use)
```bash
# Install CLI if you don't have it
npm install -g vercel

# Set the variable and trigger a redeploy in one shot
vercel env add NEXT_PUBLIC_API_URL production
# Paste your trycloudflare.com URL when prompted, then:
vercel --prod
```

---

## Verify it's working

After redeployment, open your Vercel app URL.  
The header should show **"Agent online"** with a green dot within a few seconds.

You can also test the tunnel directly from any browser or terminal:
```bash
curl https://olive-dragon-abc123.trycloudflare.com/health
# Expected: {"status":"ok"}
```

---

## What happens when your Mac sleeps

- The tunnel closes and teammates see the amber **"Backend unreachable"** banner.
- They can click the **Retry** button — if your Mac is back online and the tunnel
  is restarted it will reconnect immediately.
- The frontend pings `/health` every 30 seconds automatically, so the banner
  clears on its own once the tunnel comes back up.

---

## Quick reference

| Component | URL | Command |
|-----------|-----|---------|
| FastAPI | `http://localhost:8000` | `uvicorn backend.main:app --reload --port 8000` |
| Ollama | `http://localhost:11434` | `ollama serve` |
| Cloudflare tunnel | `https://<random>.trycloudflare.com` | `cloudflared tunnel --url http://localhost:8000` |
| Frontend (local) | `http://localhost:3000` | `pnpm dev` |
| Frontend (Vercel) | `https://your-app.vercel.app` | Deployed automatically on git push |

---

## Troubleshooting

**"The tunnel is active but the frontend still shows offline"**  
→ You probably forgot to redeploy after updating the env var.  
→ `NEXT_PUBLIC_*` vars are compiled into the JS bundle at build time — a redeploy is always required.

**"curl /health works but the browser gets a CORS error"**  
→ Check that `main.py` has `allow_origins=["*"]` and `allow_credentials=False`.  
→ These two must match — setting both to wildcard + credentials=True is rejected by browsers.

**"cloudflared: command not found"**  
→ Run `brew install cloudflare/cloudflare/cloudflared` and try again.

**"Port 8000 already in use"**  
```bash
lsof -ti:8000 | xargs kill -9
```
