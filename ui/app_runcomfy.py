#!/usr/bin/env python3
"""
Local web UI for the "One-click Pose Generator" workflow on RunComfy serverless.

Deployment f9c1e1f5-... takes ONE character image and auto-generates N pose variations
(an LLM writes the prompts). Overrides used:
    node 15 (LoadImage)  input "image"  <- your character image (data: base64 or URL)
    node 21 (CR Text)    input "text"   <- number of poses to generate
    node 8  (KSampler)   input "seed"   <- optional seed

Run:
    pip install flask requests
    export RUNCOMFY_TOKEN=your_api_token
    export RUNCOMFY_DEPLOYMENT_ID=f9c1e1f5-e4c6-4f4c-8a10-899b45d47aa4   # default
    python app_runcomfy.py            # -> http://localhost:5000
Your token stays server-side. Results come back as image URLs (valid 7 days).
"""
import os, base64, requests
from flask import Flask, request, jsonify, Response

TOKEN = os.environ.get("RUNCOMFY_TOKEN", "")
DEP   = os.environ.get("RUNCOMFY_DEPLOYMENT_ID", "f9c1e1f5-e4c6-4f4c-8a10-899b45d47aa4")
BASE  = f"https://api.runcomfy.net/prod/v2/deployments/{DEP}"
IMAGE_NODE = os.environ.get("IMAGE_NODE", "15")
COUNT_NODE = os.environ.get("COUNT_NODE", "21")
SEED_NODE  = os.environ.get("SEED_NODE",  "8")

app = Flask(__name__)
def hdr(): return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")


@app.post("/generate")
def generate():
    if not TOKEN:
        return jsonify(error="RUNCOMFY_TOKEN is not set on the server"), 400
    img = request.files.get("image")
    if not img:
        return jsonify(error="A character image is required"), 400
    count = (request.form.get("count") or "9").strip()
    seed  = (request.form.get("seed") or "").strip()

    mime = img.mimetype or "image/png"
    datauri = f"data:{mime};base64," + base64.b64encode(img.read()).decode()
    overrides = {
        IMAGE_NODE: {"inputs": {"image": datauri}},
        COUNT_NODE: {"inputs": {"text": str(count)}},
    }
    if seed:
        try: overrides[SEED_NODE] = {"inputs": {"seed": int(seed)}}
        except ValueError: pass

    r = requests.post(f"{BASE}/inference", headers=hdr(), json={"overrides": overrides}, timeout=120)
    if r.status_code not in (200, 201):
        return jsonify(error=f"RunComfy inference {r.status_code}: {r.text[:300]}"), 502
    return jsonify(request_id=r.json().get("request_id"))


@app.get("/status/<request_id>")
def status(request_id):
    s = requests.get(f"{BASE}/requests/{request_id}/status", headers=hdr(), timeout=60).json()
    st = s.get("status")
    if st in ("completed", "succeeded"):
        res = requests.get(f"{BASE}/requests/{request_id}/result", headers=hdr(), timeout=60).json()
        urls = [im["url"] for node in (res.get("outputs") or {}).values()
                for im in node.get("images", []) if im.get("url")]
        return jsonify(status="completed", images=urls)
    if st in ("failed", "error"):
        return jsonify(status="failed", error=str(s)[:400])
    return jsonify(status=st, queue_position=s.get("queue_position"))


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Pose Generator</title>
<style>
:root{color-scheme:light dark}*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:820px;margin:0 auto;padding:24px;background:#0f1115;color:#e7e9ee}
@media(prefers-color-scheme:light){body{background:#f6f7f9;color:#1a1d24}}
h1{font-size:20px;margin:0 0 4px}.sub{opacity:.6;font-size:13px;margin-bottom:20px}
.drop{border:2px dashed #3a4050;border-radius:12px;min-height:240px;display:flex;align-items:center;justify-content:center;text-align:center;cursor:pointer;overflow:hidden;position:relative;background:#171a21}
@media(prefers-color-scheme:light){.drop{background:#fff;border-color:#cfd4dd}}
.drop:hover{border-color:#5b8cff}.drop img{width:100%;height:100%;object-fit:contain;position:absolute;inset:0}.drop span{opacity:.6;font-size:13px;padding:12px}
label.lbl{font-size:13px;font-weight:600;display:block;margin:0 0 6px}
.opts{display:flex;gap:14px;margin-top:16px}.opts>div{flex:1}
input[type=number]{width:100%;border-radius:10px;border:1px solid #3a4050;background:#171a21;color:inherit;padding:10px;font:inherit}
@media(prefers-color-scheme:light){input[type=number]{background:#fff;border-color:#cfd4dd}}
button{margin-top:16px;width:100%;padding:13px;border:0;border-radius:10px;background:#5b8cff;color:#fff;font-weight:600;font-size:15px;cursor:pointer}button:disabled{opacity:.5}
#status{margin-top:16px;font-size:14px;min-height:20px}
#result{margin-top:16px;display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
#result figure{margin:0}#result img{width:100%;border-radius:10px;display:block}#result a{font-size:12px;color:#5b8cff}
.spin{display:inline-block;width:14px;height:14px;border:2px solid #5b8cff;border-top-color:transparent;border-radius:50%;animation:s .8s linear infinite;vertical-align:-2px;margin-right:6px}@keyframes s{to{transform:rotate(360deg)}}
</style></head><body>
<h1>One-click Pose Generator</h1>
<div class="sub">Upload one character image &rarr; it auto-generates pose / action variations.</div>
<label class="lbl">Character image</label>
<div class="drop" id="d"><span>Click or drop an image</span><input type="file" accept="image/*" hidden id="f"></div>
<div class="opts">
  <div><label class="lbl">Number of poses</label><input type="number" id="count" value="9" min="1" max="20"></div>
  <div><label class="lbl">Seed (optional)</label><input type="number" id="seed" placeholder="random"></div>
</div>
<button id="go">Generate</button>
<div id="status"></div><div id="result"></div>
<script>
const f=document.getElementById('f'),d=document.getElementById('d');
d.onclick=()=>f.click();['dragover','dragleave','drop'].forEach(e=>d.addEventListener(e,ev=>{ev.preventDefault();if(e==='drop'&&ev.dataTransfer.files[0]){f.files=ev.dataTransfer.files;show()}}));
f.onchange=show;function show(){if(f.files[0])d.innerHTML='<img src="'+URL.createObjectURL(f.files[0])+'">';}
const go=document.getElementById('go'),stat=document.getElementById('status'),res=document.getElementById('result');
go.onclick=async()=>{
 if(!f.files[0]){stat.textContent='Please add an image.';return;}
 go.disabled=true;res.innerHTML='';stat.innerHTML='<span class=spin></span>Submitting...';
 const fd=new FormData();fd.append('image',f.files[0]);fd.append('count',document.getElementById('count').value);fd.append('seed',document.getElementById('seed').value);
 try{const j=await(await fetch('/generate',{method:'POST',body:fd})).json();
  if(j.error){stat.textContent='Error: '+j.error;go.disabled=false;return;}
  const id=j.request_id;let t=0;
  const poll=async()=>{const s=await(await fetch('/status/'+id)).json();
   if(s.status==='completed'){stat.textContent='Done in '+t+'s - '+(s.images||[]).length+' image(s).';res.innerHTML=(s.images||[]).map((u,i)=>'<figure><img src="'+u+'"><a download="pose_'+i+'.png" href="'+u+'">download</a></figure>').join('')||'(no images)';go.disabled=false;return;}
   if(s.status==='failed'){stat.textContent='Failed: '+(s.error||'');go.disabled=false;return;}
   t+=3;stat.innerHTML='<span class=spin></span>'+(s.status||'working')+'... '+t+'s'+(s.queue_position?(' (queue '+s.queue_position+')'):'');setTimeout(poll,3000);};
  poll();
 }catch(e){stat.textContent='Error: '+e;go.disabled=false;}
};
</script></body></html>"""

if __name__ == "__main__":
    print(f">> runcomfy deployment {DEP} | token {'set' if TOKEN else 'MISSING'} | image={IMAGE_NODE} count={COUNT_NODE} seed={SEED_NODE}")
    print(">> open http://localhost:5000")
    app.run(host="0.0.0.0", port=5000)
