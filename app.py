"""
Netflix NFToken Web — Flask + Playwright su Railway
POST /api/generate  →  { "url": "https://www.netflix.com/?nftoken=..." }
"""

import os
import re
import urllib.parse
import logging
from flask import Flask, request, jsonify, send_from_directory

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static")

_TOKEN_NAMES = {"NetflixId", "SecureNetflixId", "nfvdid"}
_REQUIRED    = {"NetflixId", "SecureNetflixId"}
_HTTPONLY    = re.compile(r"^#HttpOnly_", re.IGNORECASE)
_COMMENT     = re.compile(r"^\s*#")


# ── Cookie parsing ─────────────────────────────────────────────────────────────

def _parse_lines(lines):
    found = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if _HTTPONLY.match(line):
            line = _HTTPONLY.sub("", line)
        elif _COMMENT.match(line):
            continue
        parts = line.split("\t")
        if len(parts) != 7:
            parts = re.split(r"  +", line)
        if len(parts) != 7:
            continue
        _, _f, _p, _s, _e, name, value = parts
        name = name.strip(); value = value.strip()
        if name in _TOKEN_NAMES and len(value) > 5:
            found[name] = value
    return found


def parse_cookies(raw):
    lines = raw.strip().splitlines()
    if "\t" in raw or ".netflix.com" in raw:
        found = _parse_lines(lines)
        if found:
            return found
    found = {}
    for pair in raw.replace("\n", ";").split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        name = name.strip(); value = value.strip()
        if name in _TOKEN_NAMES and len(value) > 5:
            found[name] = value
    return found


# ── Token generation ───────────────────────────────────────────────────────────

def generate_nftoken(cookies):
    decoded = {k: urllib.parse.unquote(v) for k, v in cookies.items()}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        )

        pw_cookies = [
            {
                "name": name, "value": value,
                "domain": ".netflix.com", "path": "/",
                "httpOnly": name in {"NetflixId", "SecureNetflixId"},
                "secure": True, "sameSite": "Lax",
            }
            for name, value in decoded.items()
        ]
        ctx.add_cookies(pw_cookies)

        page = ctx.new_page()
        try:
            page.goto("https://www.netflix.com/browse", timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            browser.close()
            raise RuntimeError(f"Timeout Netflix: {e}")

        js = """
        async () => {
            const body = {
                operationName: "createAutoLoginToken",
                variables: {},
                query: "mutation createAutoLoginToken { createAutoLoginToken }"
            };
            try {
                const r = await fetch("https://www.netflix.com/nq/website/memberapi/v1/graphql", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Accept": "application/json" },
                    body: JSON.stringify(body),
                    credentials: "include"
                });
                const d = await r.json();
                if (d?.data?.createAutoLoginToken) return { token: d.data.createAutoLoginToken };
                if (d?.errors) return { error: JSON.stringify(d.errors) };
            } catch(e) {}
            try {
                const r2 = await fetch("https://web.prod.cloud.netflix.com/graphql", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "x-netflix.clienttype": "akira"
                    },
                    body: JSON.stringify(body),
                    credentials: "include"
                });
                const d2 = await r2.json();
                if (d2?.data?.createAutoLoginToken) return { token: d2.data.createAutoLoginToken };
                return { error: JSON.stringify(d2).substring(0, 300) };
            } catch(e2) {
                return { error: e2.toString() };
            }
        }
        """

        try:
            result = page.evaluate(js)
        except Exception as e:
            browser.close()
            raise RuntimeError(f"Errore JS: {e}")

        browser.close()

        if not result:
            raise RuntimeError("Nessuna risposta da Netflix.")
        if "error" in result:
            raise RuntimeError(result["error"])

        token = result.get("token")
        if not token:
            raise RuntimeError(f"Token assente: {result}")

        encoded = urllib.parse.quote(token, safe="")
        return f"https://www.netflix.com/?nftoken={encoded}"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json(silent=True) or {}
    raw  = data.get("cookie", "").strip()

    if not raw:
        # also accept file upload
        f = request.files.get("file")
        if f:
            raw = f.read().decode("utf-8", errors="replace")

    if not raw:
        return jsonify({"error": "Nessun cookie fornito."}), 400

    cookies = parse_cookies(raw)
    missing = _REQUIRED - cookies.keys()
    if missing:
        return jsonify({"error": f"Cookie mancanti: {', '.join(sorted(missing))}"}), 400

    try:
        url = generate_nftoken(cookies)
        return jsonify({"url": url})
    except RuntimeError as e:
        log.error("generate_nftoken error: %s", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
