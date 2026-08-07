"""
Netflix NFToken Web — Flask su Railway
Usa l'endpoint iOS API reale di Netflix, niente Playwright.
POST /api/generate  →  { "url": "https://netflix.com/?nftoken=..." }
"""

import os
import re
import json
import urllib.parse
import logging
import requests
from flask import Flask, request, jsonify, send_from_directory
from urllib3.exceptions import InsecureRequestWarning

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

app = Flask(__name__, static_folder="static")

_TOKEN_NAMES = {"NetflixId", "SecureNetflixId", "nfvdid", "OptanonConsent"}
_REQUIRED    = {"NetflixId"}
_HTTPONLY    = re.compile(r"^#HttpOnly_", re.IGNORECASE)
_COMMENT     = re.compile(r"^\s*#")

# ── iOS API endpoint (confirmed working) ──────────────────────────────────────
_API_URL = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"

_QUERY_PARAMS = {
    "appVersion": "15.48.1",
    "config": '{"gamesInTrailersEnabled":"false","cdsMyListSortEnabled":"true","kidsBillboardEnabled":"true","billboardEnabled":"true","useCDSGalleryEnabled":"true","sharksEnabled":"true"}',
    "device_type": "NFAPPL-02-",
    "esn": "NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "idiom": "phone",
    "iosVersion": "15.8.5",
    "isTablet": "false",
    "languages": "en-US",
    "locale": "en-US",
    "maxDeviceWidth": "375",
    "model": "saget",
    "modelType": "IPHONE8-1",
    "odpAware": "true",
    "path": '["account","token","default"]',
    "pathFormat": "graph",
    "pixelDensity": "2.0",
    "progressive": "false",
    "responseFormat": "json",
}

_HEADERS = {
    "User-Agent": "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
    "x-netflix.request.attempt": "1",
    "x-netflix.request.client.user.guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.context.profile-guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.request.routing": '{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',
    "x-netflix.context.app-version": "15.48.1",
    "x-netflix.argo.translated": "true",
    "x-netflix.context.form-factor": "phone",
    "x-netflix.context.sdk-version": "2012.4",
    "x-netflix.client.appversion": "15.48.1",
    "x-netflix.context.max-device-width": "375",
    "x-netflix.context.ab-tests": "",
    "x-netflix.tracing.cl.useractionid": "4DC655F2-9C3C-4343-8229-CA1B003C3053",
    "x-netflix.client.type": "argo",
    "x-netflix.client.ftl.esn": "NFAPPL-02-IPHONE8=1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "x-netflix.context.locales": "en-US",
    "x-netflix.context.top-level-uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
    "x-netflix.client.iosversion": "15.8.5",
    "accept-language": "en-US;q=1",
    "x-netflix.argo.abtests": "",
    "x-netflix.context.os-version": "15.8.5",
    "x-netflix.request.client.context": '{"appState":"foreground"}',
    "x-netflix.context.ui-flavor": "argo",
    "x-netflix.argo.nfnsm": "9",
    "x-netflix.context.pixel-density": "2.0",
    "x-netflix.request.toplevel.uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
    "x-netflix.request.client.timezoneid": "Asia/Dhaka",
}


# ── Cookie parsing ─────────────────────────────────────────────────────────────

def _decode(value):
    if isinstance(value, str) and "%" in value:
        try:
            return urllib.parse.unquote(value)
        except Exception:
            return value
    return value


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
            found[name] = _decode(value)
    return found


def parse_cookies(raw):
    lines = raw.strip().splitlines()

    # Try JSON format
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {k: _decode(v) for k, v in data.items() if k in _TOKEN_NAMES}
        if isinstance(data, list):
            return {c["name"]: _decode(c["value"]) for c in data
                    if c.get("name") in _TOKEN_NAMES}
    except Exception:
        pass

    # Netscape format
    if "\t" in raw or ".netflix.com" in raw:
        found = _parse_lines(lines)
        if found:
            return found

    # Raw browser string: "NetflixId=xxx; SecureNetflixId=xxx"
    found = {}
    for pair in raw.replace("\n", ";").split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        name = name.strip(); value = value.strip()
        if name in _TOKEN_NAMES and len(value) > 5:
            found[name] = _decode(value)
    return found


# ── Token generation ───────────────────────────────────────────────────────────

def generate_nftoken(cookies):
    netflix_id = cookies.get("NetflixId")
    if not netflix_id:
        raise RuntimeError("NetflixId non trovato nei cookie.")

    headers = dict(_HEADERS)
    headers["Cookie"] = f"NetflixId={netflix_id}"

    r = requests.get(
        _API_URL,
        params=_QUERY_PARAMS,
        headers=headers,
        timeout=30,
        verify=False,
    )
    r.raise_for_status()

    data = r.json()
    token_data = (
        (((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default")
        or {}
    )
    token = token_data.get("token")
    if not token:
        raise RuntimeError(f"Nessun token nella risposta: {json.dumps(data)[:300]}")

    return "https://netflix.com/?nftoken=" + token


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/generate", methods=["POST"])
def api_generate():
    raw = ""
    data = request.get_json(silent=True) or {}
    raw = data.get("cookie", "").strip()

    if not raw:
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
        token_part = url.split("?nftoken=")[1]
        mobile_url = "https://www.netflix.com/unsupported?nftoken=" + token_part
        return jsonify({"url": url, "mobile_url": mobile_url})
    except Exception as e:
        log.error("generate_nftoken error: %s", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


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
            // First: introspect to find valid TokenScope enum values
            const introspect = {
                query: `{ __type(name: "TokenScope") { enumValues { name } } }`
            };
            let scopeValues = [];
            try {
                const ri = await fetch("https://www.netflix.com/nq/website/memberapi/v1/graphql", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Accept": "application/json" },
                    body: JSON.stringify(introspect),
                    credentials: "include"
                });
                const di = await ri.json();
                const vals = di?.data?.__type?.enumValues;
                if (vals) scopeValues = vals.map(v => v.name);
            } catch(e) {}

            if (scopeValues.length === 0) {
                return { error: "Introspection fallita — impossibile trovare TokenScope values" };
            }

            // Try each scope value until one works
            for (const scope of scopeValues) {
                const body = {
                    operationName: "createAutoLoginToken",
                    variables: {},
                    query: `mutation createAutoLoginToken { createAutoLoginToken(scope: ${scope}) }`
                };
                try {
                    const r = await fetch("https://www.netflix.com/nq/website/memberapi/v1/graphql", {
                        method: "POST",
                        headers: { "Content-Type": "application/json", "Accept": "application/json" },
                        body: JSON.stringify(body),
                        credentials: "include"
                    });
                    const d = await r.json();
                    if (d?.data?.createAutoLoginToken) {
                        return { token: d.data.createAutoLoginToken, scope: scope };
                    }
                } catch(e) {}
            }

            return { error: "Nessun scope valido ha funzionato. Valori provati: " + scopeValues.join(", ") };
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
