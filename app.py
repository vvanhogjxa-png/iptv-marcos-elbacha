import os, re, json, uuid, threading, time, csv
import requests
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── job store ──────────────────────────────────────────────────────────────
jobs = {}   # job_id → { status, results, total, done, valid, dead, stop_flag }

TIMEOUT   = 20
MAX_WORKERS = 30
HEADERS   = {"User-Agent": "VLC/3.0.14 LibVLC/3.0.14", "Accept": "*/*"}

# ── helpers ────────────────────────────────────────────────────────────────

def extract_urls(text):
    found = re.findall(r'https?://[^\s"\'<>\r\n]+', text)
    valid = [u for u in found if "username=" in u and "password=" in u]
    return list(dict.fromkeys(valid))

def parse_url(url):
    p  = urlparse(url)
    qs = parse_qs(p.query)
    u  = qs.get("username", [None])[0]
    pw = qs.get("password",  [None])[0]
    if not u or not pw:
        return None
    return f"{p.scheme}://{p.netloc}", u, pw

def check_one(url):
    parsed = parse_url(url)
    if not parsed:
        return {"url": url, "status": "INVALID", "username": "", "expiry": "", "conn": "", "server": "", "ok": False}
    base, username, password = parsed
    try:
        r = requests.get(f"{base}/player_api.php",
                         params={"username": username, "password": password},
                         headers=HEADERS, timeout=TIMEOUT, verify=False)
        if r.status_code == 200 and r.text.strip().startswith("{"):
            data = r.json()
            user = data.get("user_info", {})
            if user.get("auth"):
                exp = user.get("exp_date", "")
                try:
                    exp_str = datetime.fromtimestamp(int(exp)).strftime("%Y-%m-%d") if exp and str(exp).isdigit() else "Unlimited"
                    days    = (datetime.fromtimestamp(int(exp)) - datetime.now()).days if exp and str(exp).isdigit() else 9999
                    if days < 0: exp_str += " ⚠ EXPIRED"
                    elif days == 0: exp_str += " ⚠ TODAY"
                    else: exp_str += f" ({days}d)"
                except: exp_str = "Unlimited"
                status = user.get("status", "Unknown")
                return {"url": url, "status": status, "username": username,
                        "expiry": exp_str,
                        "conn": f"{user.get('active_cons','0')}/{user.get('max_connections','?')}",
                        "server": base, "ok": status == "Active"}
    except: pass
    return {"url": url, "status": "DEAD", "username": username if parsed else "", "expiry": "", "conn": "", "server": base if parsed else "", "ok": False}

def run_job(job_id, urls):
    job = jobs[job_id]
    job["status"]  = "running"
    job["total"]   = len(urls)
    job["done"]    = 0
    job["valid"]   = 0
    job["dead"]    = 0
    job["results"] = []

    sem = threading.Semaphore(MAX_WORKERS)
    threads = []

    def worker(url):
        if job["stop_flag"]:
            sem.release()
            return
        result = check_one(url)
        with threading.Lock():
            job["done"]    += 1
            job["results"].append(result)
            if result["ok"]: job["valid"] += 1
            else:             job["dead"]  += 1
            pct = round(job["done"] / job["total"] * 100, 1)
            socketio.emit("progress", {
                "job_id":  job_id,
                "done":    job["done"],
                "total":   job["total"],
                "pct":     pct,
                "valid":   job["valid"],
                "dead":    job["dead"],
                "result":  result
            })
        sem.release()

    for url in urls:
        if job["stop_flag"]: break
        sem.acquire()
        t = threading.Thread(target=worker, args=(url,))
        t.start()
        threads.append(t)

    for t in threads: t.join()
    job["status"] = "done" if not job["stop_flag"] else "stopped"
    socketio.emit("finished", {"job_id": job_id, "valid": job["valid"], "dead": job["dead"], "total": job["done"]})

# ── routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    text = ""
    if "file" in request.files and request.files["file"].filename:
        text = request.files["file"].read().decode("utf-8", errors="ignore")
    elif request.form.get("urls"):
        text = request.form.get("urls")
    urls = extract_urls(text)
    if not urls:
        return jsonify({"error": "No valid IPTV URLs found"}), 400
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "pending", "results": [], "total": 0, "done": 0, "valid": 0, "dead": 0, "stop_flag": False}
    t = threading.Thread(target=run_job, args=(job_id, urls), daemon=True)
    t.start()
    return jsonify({"job_id": job_id, "total": len(urls)})

@app.route("/stop/<job_id>", methods=["POST"])
def stop(job_id):
    if job_id in jobs:
        jobs[job_id]["stop_flag"] = True
    return jsonify({"ok": True})

@app.route("/export/<job_id>")
def export(job_id):
    if job_id not in jobs:
        return "Not found", 404
    only_active = request.args.get("active") == "1"
    results = jobs[job_id]["results"]
    if only_active:
        results = [r for r in results if r["ok"]]
    path = f"/tmp/export_{job_id}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Status", "Username", "Expiry", "Connections", "Server", "URL"])
        for r in results:
            w.writerow([r["status"], r["username"], r["expiry"], r["conn"], r["server"], r["url"]])
    fname = f"active_lines_{job_id}.csv" if only_active else f"all_results_{job_id}.csv"
    return send_file(path, as_attachment=True, download_name=fname)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
