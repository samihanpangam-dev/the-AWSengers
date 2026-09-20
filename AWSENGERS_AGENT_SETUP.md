# AWSengers AI Agent integration

Infinity Tool Box now includes **AWSengers AI Agent** under **AI & Automation** at
`tools/awsengers-agent/index.html`. The page preserves the existing browser-first
tools and talks to the reference FastAPI contract:

- `GET /health`
- `POST /process` with `prompt` and zero or more `files`
- `GET /download/{request_id}/{filename}`
- `GET /subscription/status` and `POST /subscription/subscribe`
- `POST /subscription/checkout`
- `POST /subscription/webhook` for provider callbacks

## Run locally

1. Install Python 3.11+ and the backend dependencies:

   ```powershell
   py -m pip install -r backend\requirements.txt
   ```

2. Install and start Ollama, then pull the configured model (the default is
   `qwen2.5`):

   ```powershell
   ollama pull qwen2.5
   ```

3. Start the API from the project root:

   ```powershell
   py -m uvicorn backend.main:app --reload --port 8000
   ```

4. Open the static site through a local HTTP server (not `file://`) and set the
   agent page's API URL to `http://localhost:8000`.

The page stores only the API URL in browser local storage. It validates file
types, limits uploads to five files of 25 MB each, and displays clear offline
and API error states. The backend repeats those checks, strips path components
from filenames, confines generated downloads to per-request directories, and
removes temporary files after failed/text-only requests or after a generated
file is downloaded.

Set `MAX_UPLOAD_BYTES`, `MAX_UPLOAD_FILES`, `MAX_PROMPT_LENGTH`, and
`UPLOAD_TMP_DIR` to tune limits. For production, set `ENV=production` and use
the AWS/Bedrock settings documented in `backend\config.py`; provide credentials
through the runtime environment or IAM, never in this project.

The integrated agent intentionally exposes fixed PDF/media tools plus bounded
`inspect_file` and `edit_file` tools. File tools are confined to the request
workspace, reject binary/oversized content, and allow only common text
extensions. It does not execute arbitrary Python, shell commands, or scripts.

Agent actions require the configured user's 30-day trial or active subscription.
The development provider is in-memory and identifies users with `X-User-ID`
(default `dev-user`); production integrations can replace the provider and use
the webhook hook. The AI Agent plan is INR 99/month after the trial. Set
`SUBSCRIPTION_PROVIDER`, `AI_AGENT_TRIAL_DAYS`, and
`SUBSCRIPTION_WEBHOOK_SECRET` through the environment.
Set `BILLING_CHECKOUT_URL` to a provider-hosted checkout endpoint in production;
when it is unset, the development provider activates the in-memory plan
directly and other providers return a clear configuration error.

## Optional API authentication

The frontend preserves the existing `GET /health`, `POST /process`, and
`GET /download/{request_id}/{filename}` contract. For a protected deployment,
enter an auth header name and value on the agent page. The values are sent on
health and process requests and stored only in that browser. Common settings
are `Authorization` with `Bearer <token>` or a deployment-specific API-key
header. The download URL uses the browser navigation request, so deployments
that protect downloads must authenticate that route with a cookie or a signed
URL returned by the existing response contract.

For a static deployment, copy `tools/awsengers-agent/config.js` to your
deployment configuration and set:

```js
window.AWSENGERS_AGENT_CONFIG = {
    apiUrl: "https://api.example.com",
    authHeader: "Authorization",
    authToken: "replace-me"
};
```

Do not commit real tokens. The backend uses `AGENT_API_TOKEN`; when production
mode or that variable is configured, `POST /process` and `GET /download` require
`Authorization: Bearer <token>`, while `GET /health` remains public. For a
framework build, expose the same value as `NEXT_PUBLIC_AGENT_API_TOKEN` and
map it to `authToken` in the static config. The backend returns a short-lived
download URL token, so the existing response shape and download flow remain
compatible. Local development remains unauthenticated when the token is blank.
