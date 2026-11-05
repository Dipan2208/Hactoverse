# Hacktoverse

Hacktoverse is a hackathon and coding-event platform for students and organizers. Participants can discover competitions, solve coding challenges, see results, and update their profiles. Organizers can manage competitions, challenges, test cases, evaluations, and rankings.

## Features

- Participant registration, sign-in, profile, and progress pages
- Event discovery, coding challenges, automatic test-case grading, and leaderboards
- Organizer tools for creating events, challenges, and test cases
- In-browser code editor with Python 3, C, C++17, and Java
- Light/dark theme preference saved in the browser
- Responsive dashboard with an original CSS-animated robot illustration

### Code execution

Code questions use a Docker-isolated runner for custom runs and automatic test-case grading. Execution is disabled by default; the editor remains available and saves drafts in the browser. Do not enable execution unless Docker is running and the dedicated runner image is built. The runner has no network access, host mounts, Linux capabilities, or writable root filesystem, and is subject to container resource limits. Keep the runner image and Docker daemon patched; this local setup is not a substitute for a reviewed production sandbox.

### Hacktoverse Algorithm Sprint — Demo

The demo competition is **Hacktoverse Algorithm Sprint — Demo**, with two medium-level coding challenges:

1. **Shared Lab Rooms** — minimum interval partitioning / heap
2. **Longest Segment with Target Sum** — prefix sums / hash map

Participants solve both challenges directly in the browser editor; **no ZIP or file upload is required**. The organizer must start the competition before participants can join, and can end it at any time. Scheduled start/end dates and each participant's configured contest timer are enforced.

On a fresh database, sign in with the configured organizer account, create the event from **Organizer**, then add the two challenges and their test cases. The running local database is not included in this repository.

### Participate

1. Open the local site and create a participant account with your name, email, and password.
2. Sign in and open **Events**. Wait until the organizer starts **Hacktoverse Algorithm Sprint — Demo**.
3. Open the live event, write your solution in the editor, and use **Run Code** for custom input.
4. Choose **Submit** to run all configured test cases and receive a verdict and score before the organizer ends the event or your contest timer expires.

### Organize

Sign in using the configured organizer account, open **Organizer**, then choose **Settings** beside an event to edit its start/end dates and participant contest timer (1–1440 minutes; 45 minutes by default). Use **Start event** to let participants in on or after the scheduled start date, and **End event** to close an active competition immediately. Choose **Manage** to add or edit code questions and configure sample and hidden test cases. Automatic submissions and scores appear in **My progress / Evaluations**.

This is a local preview, not a public deployment. A dedicated Docker-isolated runner is required for code execution. Before public deployment, configure a production host and database, use protected secrets, and review the runner and deployment security.

## Run locally on Windows

Requirements: Python 3, MongoDB running locally or a MongoDB connection string. Docker Desktop is additionally required to run and grade participant code.

From PowerShell in the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set `SECRET_KEY`, `MONGO_URI`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD`. Use a unique secret key and an admin password of at least 12 characters. If PowerShell blocks activation, run this for the current terminal only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Start the app:

```powershell
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). To use local MongoDB, set `MONGO_URI=mongodb://localhost:27017/DevHost`. The app creates an organizer account from the `ADMIN_EMAIL` and `ADMIN_PASSWORD` values when that account does not already exist. If those values are absent, no default administrator is created. If your database predates this update, the old `admin` / default-password login is blocked; configure a new organizer account before deployment.

To enable code execution, start Docker Desktop and build the dedicated runner image from the project folder:

```powershell
docker build -f runner.Dockerfile -t hacktoverse-runner:local .
```

Set these values in `.env`, then restart the Flask app:

```text
CODE_EXECUTION_ENABLED=1
RUNNER_IMAGE=hacktoverse-runner:local
```

The app only enables **Run Code** and automatic grading when the setting is enabled and Docker can find the runner image. Build the runner image again after changing `runner_entry.py` or `runner.Dockerfile`. Do not expose this development server directly to the public internet.

## Deployment notes

Set `SECRET_KEY`, `MONGO_URI`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `CODE_EXECUTION_ENABLED`, and `RUNNER_IMAGE` in the hosting provider's environment settings. Never commit `.env` or credentials. Build and secure the isolated runner image on the host before enabling code execution; do not expose the Flask development server directly to the public internet.

Uploaded files are stored on the app's local filesystem by default. Choose persistent storage or an object-storage service before relying on uploaded submissions in a deployment where local files may be ephemeral.

## Stack

- Flask, Jinja templates, HTML, and CSS
- MongoDB via Flask-PyMongo
- CodeMirror editor
- Gunicorn for production serving
