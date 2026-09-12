// ============================================================
//  Safari POS Pro - Splash Screen Poller
//  Polls the backend /health endpoint, redirects when ready
// ============================================================

const PORT = 8001;
const HEALTH_URL = `http://localhost:${PORT}/health`;
const APP_URL = `http://localhost:${PORT}/`;
const MAX_TRIES = 60;
const INTERVAL_MS = 500;

const statusText = document.getElementById("statusText");
const subStatus = document.getElementById("subStatus");
const progressFill = document.getElementById("progressFill");
const errorBox = document.getElementById("errorBox");
const errorMsg = document.getElementById("errorMsg");

let tries = 0;
const startTime = Date.now();

function setProgress(pct) {
    progressFill.style.width = Math.min(pct, 100) + "%";
}

function setStatus(msg, sub) {
    statusText.textContent = msg;
    if (sub !== undefined) subStatus.textContent = sub;
}

function showError(msg) {
    document.querySelector(".loader").style.display = "none";
    document.querySelector(".progress-bar").style.display = "none";
    statusText.style.display = "none";
    subStatus.style.display = "none";
    errorMsg.textContent = msg;
    errorBox.style.display = "block";
}

async function checkHealth() {
    tries++;

    // Progress bar grows slowly while waiting
    setProgress((tries / MAX_TRIES) * 100);

    // Update status text at certain thresholds
    const elapsed = Date.now() - startTime;
    if (elapsed < 2000) {
        setStatus("Starting server...", "Warming up FastAPI, please wait");
    } else if (elapsed < 5000) {
        setStatus("Loading database...", "Initializing SQLAlchemy");
    } else if (elapsed < 10000) {
        setStatus("Almost ready...", "Hang tight, this is normal on first launch");
    } else {
        setStatus("Still starting...", "Slower than usual — check antivirus if this persists");
    }

    // Enforce minimum splash time (feels less jarring)
    const minSplashTime = 1500;
    if (elapsed < minSplashTime) {
        setTimeout(checkHealth, INTERVAL_MS);
        return;
    }

    try {
        const res = await fetch(HEALTH_URL, {
            method: "GET",
            cache: "no-store",
            signal: AbortSignal.timeout(2000),
        });

        if (res.ok) {
            const data = await res.json();
            if (data.status === "healthy") {
                setStatus("Ready!", "Redirecting to Safari POS Pro...");
                setProgress(100);
                setTimeout(() => {
                    window.location.replace(APP_URL);
                }, 300);
                return;
            }
        }
    } catch (e) {
        // Server not ready yet — keep polling
    }

    if (tries >= MAX_TRIES) {
        showError("The server did not start within 30 seconds. This can happen if antivirus blocked Python or if port " + PORT + " is in use by another program.");
        return;
    }

    setTimeout(checkHealth, INTERVAL_MS);
}

// Start polling as soon as page loads
window.addEventListener("load", () => {
    setTimeout(checkHealth, 300);
});
