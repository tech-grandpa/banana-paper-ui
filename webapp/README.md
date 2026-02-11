# PaperBanana Web UI

A web interface for the PaperBanana text-to-diagram generator.

## Features

- **Intuitive UI**: Clean, retro-futuristic design with dark mode
- **Real-time Progress**: Live updates showing which agent is running and current iteration
- **Result Gallery**: View all iterations side-by-side with the final output highlighted
- **Easy Download**: One-click download of the final diagram

## Setup

### 1. Install Dependencies

First, create and activate a virtual environment:

```bash
cd /Users/tg/repos/banana-paper-ui
python3 -m venv venv
source venv/bin/activate
```

Then install the package and web dependencies:

```bash
pip install -e ".[google]"
pip install fastapi uvicorn python-multipart
```

### 2. Configure Environment

Make sure you have a `.env` file in the repo root with your Google API key:

```env
GOOGLE_API_KEY=your_api_key_here
```

You can copy `.env.example` as a starting point.

## Running the Server

Start the web server:

```bash
# From the repo root
cd /Users/tg/repos/banana-paper-ui

# Activate venv if not already active
source venv/bin/activate

# Run the server
python -m webapp.main
```

Or use uvicorn directly:

```bash
uvicorn webapp.main:app --host 0.0.0.0 --port 8000 --reload
```

The server will be available at:
- **Local**: http://localhost:8000
- **Network**: http://0.0.0.0:8000

## Usage

1. **Paste your text**: Add your methodology description or paper text in the large text area
2. **Add a caption**: Describe what the diagram should communicate
3. **Select iterations**: Choose 1-5 refinement iterations (default: 3)
4. **Generate**: Click "Generate Diagram" and watch the progress
5. **Download**: Once complete, download your final diagram

## API Endpoints

### `POST /api/generate`

Start a new diagram generation job.

**Request Body:**
```json
{
  "text": "Source context / methodology description",
  "caption": "Communicative intent / caption",
  "iterations": 3
}
```

**Response:**
```json
{
  "job_id": "uuid",
  "status": "queued"
}
```

### `GET /api/status/{job_id}`

Get the current status of a generation job.

**Response:**
```json
{
  "job_id": "uuid",
  "status": "running",
  "phase": "refinement",
  "agent": "visualizer",
  "iteration": 2,
  "total_iterations": 3,
  "progress": "Generating image (iteration 2/3)...",
  "error": null
}
```

### `GET /api/result/{job_id}`

Get the results of a completed job.

**Response:**
```json
{
  "job_id": "uuid",
  "status": "completed",
  "final_image": "/api/result/{job_id}/image/final.png",
  "iteration_images": [
    "/api/result/{job_id}/image/iteration_1.png",
    "/api/result/{job_id}/image/iteration_2.png",
    "/api/result/{job_id}/image/iteration_3.png"
  ],
  "error": null
}
```

### `GET /api/result/{job_id}/image/{filename}`

Download an individual image file.

## Architecture

- **Backend**: FastAPI with async/await support
- **Frontend**: Single-page HTML with vanilla JavaScript
- **Storage**: In-memory job storage (resets on server restart)
- **Progress Tracking**: Polls `/api/status` every 2 seconds during generation

## Design

The UI uses a retro-futuristic aesthetic:
- **Colors**: Electric orange (#ff6b35), deep purple (#1a1a2e), cream text (#f4f1de)
- **Fonts**: Outfit (body), Syne (headings)
- **Style**: Dark mode, glowing effects, smooth animations

## Notes

- Jobs are stored in memory and will be lost on server restart
- The pipeline runs asynchronously in the background
- Multiple generations can run concurrently
- Each job gets a unique UUID and its own output directory
- The server loads `.env` from the repo root automatically
