# PaperBanana FastAPI Web UI

The TechGrandpa web interface for PaperBanana. It provides a paste-text-to-diagram workflow, live pipeline progress, an iteration gallery, and downloads.

Hosted instance: **https://fig.acgt.dev**

## Features

- Dark, responsive single-page interface
- Live progress from PaperBanana's structured progress callbacks
- One to five visualizer/critic refinement rounds
- Final image and iteration gallery
- OpenRouter and Google provider support through the standard PaperBanana settings

## Setup

```bash
git clone https://github.com/tech-grandpa/banana-paper-ui.git
cd banana-paper-ui
python3 -m venv venv
source venv/bin/activate
pip install -e '.[web]'
cp .env.example .env
```

Configure `.env`. The hosted deployment uses OpenRouter with Claude Opus 4.8 for planning and critique:

```env
OPENROUTER_API_KEY=your-key-here
VLM_PROVIDER=openrouter
VLM_MODEL=anthropic/claude-opus-4.8
IMAGE_PROVIDER=openrouter_imagen
IMAGE_MODEL=google/gemini-3-pro-image

# Public-endpoint safety limits
WEB_MAX_REQUEST_BYTES=262144
WEB_MAX_ACTIVE_JOBS=1
WEB_MAX_GLOBAL_REQUESTS_PER_HOUR=4
WEB_MAX_CLIENT_REQUESTS_PER_HOUR=2
WEB_JOB_BUDGET_USD=1.00
WEB_RUNS_DIR=outputs/web
WEB_RUN_TTL_SECONDS=86400
WEB_RUN_DISK_QUOTA_BYTES=1073741824
WEB_RUN_CLEANUP_INTERVAL_SECONDS=300
```

The web endpoint rejects oversized HTTP bodies before JSON parsing, forbids unknown request fields, bounds source and caption lengths, retains at most 100 jobs in memory, and only serves verified PNG/JPEG/WebP files explicitly recorded for a completed job with `nosniff` response protection. Public runs are isolated under `WEB_RUNS_DIR`. Cleanup runs at startup and every `WEB_RUN_CLEANUP_INTERVAL_SECONDS`: it removes directories older than `WEB_RUN_TTL_SECONDS`, then removes the oldest completed runs until total file usage is at or below `WEB_RUN_DISK_QUOTA_BYTES`. Active runs are protected. This retention deletes saved source input, prompts, intermediate images, and final images, so copy any result that must be kept before its TTL expires.

Keep Uvicorn at one worker because job and rate-limit state is process-local. When deployed behind a trusted reverse proxy, set `WEB_TRUST_PROXY_HEADERS=true` for per-client limits.

Do not commit `.env`.

## Run locally

```bash
source venv/bin/activate
python -m webapp.main
```

Or choose the bind address and port explicitly:

```bash
uvicorn webapp.main:app --host 0.0.0.0 --port 8765
```

## API

### `POST /api/generate`

```json
{
  "text": "Source context or methodology description",
  "caption": "What the diagram should communicate",
  "iterations": 3
}
```

Returns a queued job ID.

### `GET /api/status/{job_id}`

Returns the current status, pipeline phase, active agent, iteration, progress message, and any error.

### `GET /api/result/{job_id}`

Returns final and iteration image URLs after completion.

### `GET /api/result/{job_id}/image/{filename}`

Returns a generated image associated with the job.

## Production service

The hosted Ubuntu VM runs the app as `paperbanana.service` on port `8765`:

```ini
[Service]
User=ng
WorkingDirectory=/home/ng/banana-paper-ui
ExecStart=/home/ng/banana-paper-ui/venv/bin/python -m uvicorn webapp.main:app --host 0.0.0.0 --port 8765
Restart=on-failure
```

Useful commands:

```bash
sudo systemctl status paperbanana
sudo systemctl restart paperbanana
sudo journalctl -u paperbanana -n 100 --no-pager
```

## Notes

- Job state is kept in memory and resets when the service restarts.
- Generated web files are temporary and subject to the configured TTL and disk quota.
- The server loads `.env` from the repository root.
