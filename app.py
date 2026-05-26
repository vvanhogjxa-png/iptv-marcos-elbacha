import os, re, json, uuid, threading, csv, requests
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from flask import Flask, request, jsonify, send_file
from flask_socketio import SocketIO

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

jobs = {}
TIMEOUT = 20
MAX_WORKERS = 30
HEADERS = {"User-Agent": "VLC/3.0.14 LibVLC/3.0.14", "Accept": "*/*"}

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IPTV Checker</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Syne:wght@700;800&display=swap');
  :root {
    --bg:#0a0a0f; --surface:#111118; --border:#1e1e2e;
    --accent:#00ff88; --accent2:#ff3366; --accent3:#3366ff;
    --text:#e0e0f0; --muted:#555570;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font-family:'JetBrains Mono',monospace; min-height:100vh; padding:24px; }
  body::before { content:''; position:fixed; inset:0;
    background-image: linear-gradient(rgba(0,255,136,.03) 1px,transparent 1px), linear-gradient(90deg,rgba(0,255,136,.03) 1px,transparent 1px);
    background-size:40px 40px; pointer-events:none; z-index:0; }
  .wrap { max-width:1100px; margin:0 auto; position:relative; z-index:1; }
  header { display:flex; align-items:center; gap:16px; margin-bottom:32px; border-bottom:1px solid var(--border); padding-bottom:20px; }
  .logo { font-family:'Syne',sans-serif; font-size:26px; font-weight:800; color:var(--accent); letter-spacing:-1px; }
  .logo span { color:var(--text); }
  .badge { font-size:10px; font-weight:700; background:var(--accent); color:#000; padding:2px 8px; border-radius:4px; letter-spacing:2px; }
  .grid { display:grid; grid-template-columns:380px 1fr; gap:20px; }
  .card { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:20px; }
  .card-title { font-family:'Syne',sans-serif; font-size:13px; font-weight:700; color:var(--muted); letter-spacing:3px; text-transform:uppercase; margin-bottom:16px; }
  .drop-zone { border:2px dashed var(--border); border-radius:8px; padding:30px 20px; text-align:center; cursor:pointer; transition:all .2s; margin-bottom:16px; position:relative; }
  .drop-zone:hover,.drop-zone.drag { border-color:var(--accent); background:rgba(0,255,136,.04); }
  .drop-zone input { position:absolute; inset:0; opacity:0; cursor:pointer; }
  .drop-icon { font-size:32px; margin-bottom:8px; }
  .drop-label { font-size:12px; color:var(--muted); }
  .drop-label b { color:var(--accent); }
  #file-name { font-size:11px; color:var(--accent); margin-top:6px; min-height:16px; }
  textarea { width:100%; height:120px; background:#0d0d14; border:1px solid var(--border); border-radius:8px; color:var(--text); font-family:'JetBrains Mono',monospace; font-size:11px; padding:10px; resize:vertical; outline:none; transition:border .2s; }
  textarea:focus { border-color:var(--accent); }
  textarea::placeholder { color:var(--muted); }
  .sep { text-align:center; color:var(--muted); font-size:11px; margin:12px 0; }
  .btn { width:100%; padding:12px; border:none; border-radius:8px; font-family:'JetBrains Mono',monospace; font-size:13px; font-weight:700; cursor:pointer; transition:all .2s; letter-spacing:1px; }
  .btn-start { background:var(--accent); color:#000; margin-top:14px; }
  .btn-start:hover { filter:brightness(1.15); }
  .btn-start:disabled { opacity:.4; cursor:not-allowed; }
  .btn-stop { background:var(--accent2); color:#fff; margin-top:8px; display:none; }
  .stats { display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; margin-bottom:20px; }
  .stat { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:14px 10px; text-align:center; }
  .stat-val { font-family:'Syne',sans-serif; font-size:28px; font-weight:800; }
  .stat-lbl { font-size:10px; color:var(--muted); letter-spacing:2px; text-transform:uppercase; margin-top:2px; }
  .val-total { color:var(--accent3); } .val-valid { color:var(--accent); } .val-dead { color:var(--accent2); }
  .progress-wrap { margin-bottom:20px; }
  .progress-header { display:flex; justify-content:space-between; font-size:11px; color:var(--muted); margin-bottom:6px; }
  .progress-bar { height:6px; background:var(--border); border-radius:3px; overflow:hidden; }
  .progress-fill { height:100%; width:0%; background:linear-gradient(90deg,var(--accent),var(--accent3)); border-radius:3px; transition:width .3s; }
  .export-row { display:flex; gap:8px; margin-bottom:16px; }
  .btn-export { flex:1; padding:9px; background:transparent; border:1px solid var(--border); border-radius:6px; color:var(--text); font-family:'JetBrains Mono',monospace; font-size:11px; cursor:pointer; transition:all .2s; }
  .btn-export:hover { border-color:var(--accent); color:var(--accent); }
  .btn-export:disabled { opacity:.3; cursor:not-allowed; }
  .log { background:#080810; border:1px solid var(--border); border-radius:8px; height:420px; overflow-y:auto; padding:12px; font-size:11px; line-height:1.8; }
  .log::-webkit-scrollbar { width:4px; } .log::-webkit-scrollbar-thumb { background:var(--border); border-radius:2px; }
  .log-entry { display:flex; gap:10px; padding:3px 0; border-bottom:1px solid rgba(255,255,255,.03); }
  .log-num { color:var(--muted); min-width:32px; } .log-icon { min-width:18px; } .log-body { flex:1; }
  .log-user { color:var(--accent); font-weight:700; } .log-exp { color:var(--accent3); }
  .log-dead { color:var(--accent2); opacity:.7; }
  .empty-state { height:100%; display:flex; align-items:center; justify-content:center; color:var(--muted); font-size:12px; flex-direction:column; gap:8px; }
  .empty-icon { font-size:32px; opacity:.3; }
  @media (max-width:800px) { .grid { grid-template-columns:1fr; } .log { height:300px; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div><div class="logo">IPTV<span>Checker</span></div></div>
    <div class="badge">PRO</div>
  </header>
  <div class="grid">
    <div>
      <div class="card">
        <div class="card-title">Upload / Paste</div>
        <div class="drop-zone" id="drop-zone">
          <input type="file" id="file-input" accept=".txt,.m3u,.m3u8">
          <div class="drop-icon">📂</div>
          <div class="drop-label">Drop <b>.txt</b> file or click to browse</div>
          <div id="file-name"></div>
        </div>
        <div class="sep">— or paste URLs below —</div>
        <textarea id="url-input" placeholder="http://server.com:8080/get.php?username=xxx&password=yyy"></textarea>
        <button class="btn btn-start" id="btn-start" onclick="startCheck()">▶ START CHECK</button>
        <button class="btn btn-stop"  id="btn-stop"  onclick="stopCheck()">■ STOP</button>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:16px;">
      <div class="stats">
        <div class="stat"><div class="stat-val val-total" id="s-total">0</div><div class="stat-lbl">Total</div></div>
        <div class="stat"><div class="stat-val val-valid" id="s-valid">0</div><div class="stat-lbl">Active</div></div>
        <div class="stat"><div class="stat-val val-dead"  id="s-dead">0</div><div class="stat-lbl">Dead</div></div>
      </div>
      <div class="card progress-wrap">
        <div class="progress-header"><span id="prog-label">Ready</span><span id="prog-pct">0%</span></div>
        <div class="progress-bar"><div class="progress-fill" id="prog-fill"></div></div>
      </div>
      <div class="export-row">
        <button class="btn-export" id="btn-exp-all"    onclick="doExport(0)" disabled>⬇ Export All CSV</button>
        <button class="btn-export" id="btn-exp-active" onclick="doExport(1)" disabled>⬇ Active Only CSV</button>
      </div>
      <div class="card">
        <div class="card-title">Live Results</div>
        <div class="log" id="log">
          <div class="empty-state"><div class="empty-icon">📡</div><div>Waiting for URLs...</div></div>
        </div>
      </div>
    </div>
  </div>
</div>
<script>
const socket = io();
let currentJob = null, logCount = 0;
const dz = document.getElementById('drop-zone');
const fi = document.getElementById('file-input');
dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag'); });
dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
dz.addEventListener('drop', e => { e.preventDefault(); dz.classList.remove('drag'); if(e.dataTransfer.files[0]){fi.files=e.dataTransfer.files;document.getElementById('file-name').textContent=e.dataTransfer.files[0].name;} });
fi.addEventListener('change', () => { if(fi.files[0]) document.getElementById('file-name').textContent=fi.files[0].name; });
async function startCheck() {
  const fd = new FormData();
  const file = fi.files[0];
  const text = document.getElementById('url-input').value.trim();
  if (!file && !text) { alert('Upload a file or paste URLs first!'); return; }
  if (file) fd.append('file', file); else fd.append('urls', text);
  resetUI();
  document.getElementById('btn-start').disabled = true;
  document.getElementById('btn-stop').style.display = 'block';
  document.getElementById('log').innerHTML = '';
  logCount = 0;
  const res  = await fetch('/upload', { method:'POST', body:fd });
  const data = await res.json();
  if (data.error) { alert(data.error); resetBtn(); return; }
  currentJob = data.job_id;
  document.getElementById('s-total').textContent = data.total;
  document.getElementById('prog-label').textContent = `Checking ${data.total} URLs...`;
}
function stopCheck() { if(currentJob) fetch(`/stop/${currentJob}`,{method:'POST'}); }
function doExport(activeOnly) { if(currentJob) window.open(`/export/${currentJob}?active=${activeOnly}`,'_blank'); }
function resetUI() {
  ['s-total','s-valid','s-dead'].forEach(id => document.getElementById(id).textContent='0');
  document.getElementById('prog-fill').style.width='0%';
  document.getElementById('prog-pct').textContent='0%';
  document.getElementById('btn-exp-all').disabled=true;
  document.getElementById('btn-exp-active').disabled=true;
}
function resetBtn() {
  document.getElementById('btn-start').disabled=false;
  document.getElementById('btn-stop').style.display='none';
}
socket.on('progress', d => {
  if(d.job_id!==currentJob) return;
  document.getElementById('s-total').textContent=d.done;
  document.getElementById('s-valid').textContent=d.valid;
  document.getElementById('s-dead').textContent=d.dead;
  document.getElementById('prog-fill').style.width=d.pct+'%';
  document.getElementById('prog-pct').textContent=d.pct+'%';
  document.getElementById('prog-label').textContent=`${d.done} / ${d.total} checked`;
  appendLog(d.result, ++logCount);
});
socket.on('finished', d => {
  if(d.job_id!==currentJob) return;
  document.getElementById('prog-label').textContent=`✅ Done! ${d.valid} active / ${d.dead} dead`;
  document.getElementById('btn-exp-all').disabled=false;
  document.getElementById('btn-exp-active').disabled=false;
  resetBtn();
});
function appendLog(r, n) {
  const log = document.getElementById('log');
  const e = document.createElement('div');
  e.className = 'log-entry';
  if(r.ok) {
    e.innerHTML=`<span class="log-num">${n}</span><span class="log-icon">✅</span><span class="log-body"><span class="log-user">${r.username}</span> · <span class="log-exp">${r.expiry}</span> · ${r.conn} conns · <span style="color:var(--muted)">${r.server}</span></span>`;
  } else {
    e.innerHTML=`<span class="log-num">${n}</span><span class="log-icon">${r.status==='INVALID'?'🔴':'💀'}</span><span class="log-body log-dead">${r.username||r.url.substring(0,50)} · ${r.status}</span>`;
  }
  log.appendChild(e);
  log.scrollTop=log.scrollHeight;
}
</script>
</body>
</html>"""

def extract_urls(text):
    found = re.findall(r'https?://[^\s"\'<>\r\n]+', text)
    valid = [u for u in found if "username=" in u and "password=" in u]
    return list(dict.fromkeys(valid))

def parse_url(url):
    p = urlparse(url); qs = parse_qs(p.query)
    u = qs.get("username",[None])[0]; pw = qs.get("password",[None])[0]
    if not u or not pw: return None
    return f"{p.scheme}://{p.netloc}", u, pw

def check_one(url):
    parsed = parse_url(url)
    if not parsed:
        return {"url":url,"status":"INVALID","username":"","expiry":"","conn":"","server":"","ok":False}
    base, username, password = parsed
    try:
        r = requests.get(f"{base}/player_api.php", params={"username":username,"password":password},
                         headers=HEADERS, timeout=TIMEOUT, verify=False)
        if r.status_code == 200 and r.text.strip().startswith("{"):
            data = r.json(); user = data.get("user_info",{})
            if user.get("auth"):
                exp = user.get("exp_date","")
                try:
                    exp_str = datetime.fromtimestamp(int(exp)).strftime("%Y-%m-%d") if exp and str(exp).isdigit() else "Unlimited"
                    days = (datetime.fromtimestamp(int(exp))-datetime.now()).days if exp and str(exp).isdigit() else 9999
                    if days < 0: exp_str += " EXPIRED"
                    elif days == 0: exp_str += " TODAY"
                    else: exp_str += f" ({days}d)"
                except: exp_str = "Unlimited"
                status = user.get("status","Unknown")
                return {"url":url,"status":status,"username":username,"expiry":exp_str,
                        "conn":f"{user.get('active_cons','0')}/{user.get('max_connections','?')}",
                        "server":base,"ok":status=="Active"}
    except: pass
    return {"url":url,"status":"DEAD","username":username if parsed else "","expiry":"","conn":"","server":base if parsed else "","ok":False}

def run_job(job_id, urls):
    job = jobs[job_id]
    job.update({"status":"running","total":len(urls),"done":0,"valid":0,"dead":0,"results":[]})
    sem = threading.Semaphore(MAX_WORKERS)
    threads = []
    def worker(url):
        if job["stop_flag"]: sem.release(); return
        result = check_one(url)
        with threading.Lock():
            job["done"] += 1; job["results"].append(result)
            if result["ok"]: job["valid"] += 1
            else: job["dead"] += 1
            pct = round(job["done"]/job["total"]*100, 1)
            socketio.emit("progress",{"job_id":job_id,"done":job["done"],"total":job["total"],
                                      "pct":pct,"valid":job["valid"],"dead":job["dead"],"result":result})
        sem.release()
    for url in urls:
        if job["stop_flag"]: break
        sem.acquire(); t = threading.Thread(target=worker,args=(url,)); t.start(); threads.append(t)
    for t in threads: t.join()
    job["status"] = "done" if not job["stop_flag"] else "stopped"
    socketio.emit("finished",{"job_id":job_id,"valid":job["valid"],"dead":job["dead"],"total":job["done"]})

@app.route("/")
def index(): return HTML

@app.route("/upload", methods=["POST"])
def upload():
    text = ""
    if "file" in request.files and request.files["file"].filename:
        text = request.files["file"].read().decode("utf-8", errors="ignore")
    elif request.form.get("urls"):
        text = request.form.get("urls")
    urls = extract_urls(text)
    if not urls: return jsonify({"error":"No valid IPTV URLs found"}), 400
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status":"pending","results":[],"total":0,"done":0,"valid":0,"dead":0,"stop_flag":False}
    threading.Thread(target=run_job, args=(job_id,urls), daemon=True).start()
    return jsonify({"job_id":job_id,"total":len(urls)})

@app.route("/stop/<job_id>", methods=["POST"])
def stop(job_id):
    if job_id in jobs: jobs[job_id]["stop_flag"] = True
    return jsonify({"ok":True})

@app.route("/export/<job_id>")
def export(job_id):
    if job_id not in jobs: return "Not found", 404
    only_active = request.args.get("active") == "1"
    results = [r for r in jobs[job_id]["results"] if not only_active or r["ok"]]
    path = f"/tmp/export_{job_id}.csv"
    with open(path,"w",newline="",encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["Status","Username","Expiry","Connections","Server","URL"])
        for r in results: w.writerow([r["status"],r["username"],r["expiry"],r["conn"],r["server"],r["url"]])
    fname = f"active_{job_id}.csv" if only_active else f"all_{job_id}.csv"
    return send_file(path, as_attachment=True, download_name=fname)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
