#!/usr/bin/env python3
"""
Local web UI for the Change-background workflow deployed on RunComfy serverless.

Run:
    pip install flask requests
    export RUNCOMFY_TOKEN=your_api_token
    export RUNCOMFY_DEPLOYMENT_ID=f9c1e1f5-e4c6-4f4c-8a10-899b45d47aa4
    # node IDs in YOUR deployed workflow (defaults match change_background):
    #   export PERSON_NODE=22  SCENE_NODE=35  PROMPT_NODE=21
    python app_runcomfy.py            # -> http://localhost:5000

RunComfy overrides inputs by node id; LoadImage accepts a data: base64 URI or an http URL.
Results come back as image URLs (persist 7 days). Your token stays server-side.
"""
import os, base64, pathlib, requests
from flask import Flask, request, jsonify, Response

TOKEN   = os.environ.get("RUNCOMFY_TOKEN", "")
DEP     = os.environ.get("RUNCOMFY_DEPLOYMENT_ID", "f9c1e1f5-e4c6-4f4c-8a10-899b45d47aa4")
BASE    = f"https://api.runcomfy.net/prod/v2/deployments/{DEP}"
PERSON  = os.environ.get("PERSON_NODE", "22")
SCENE   = os.environ.get("SCENE_NODE", "35")
PROMPT  = os.environ.get("PROMPT_NODE", "21")

app = Flask(__name__)
def hdr(): return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


@app.get("/")
def index():
    return Response(PAGE.replace("__PROMPT__", DEFAULT_PROMPT), mimetype="text/html")


@app.post("/generate")
def generate():
    if not TOKEN:
        return jsonify(error="RUNCOMFY_TOKEN is not set on the server"), 400
    person, scene = request.files.get("person"), request.files.get("scene")
    prompt = (request.form.get("prompt") or "").strip()
    if not person or not scene:
        return jsonify(error="Both images are required"), 400

    def datauri(f):
        mime = f.mimetype or "image/png"
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()

    overrides = {
        PERSON: {"inputs": {"image": datauri(person)}},
        SCENE:  {"inputs": {"image": datauri(scene)}},
    }
    if prompt:
        overrides[PROMPT] = {"inputs": {"prompt": prompt}}

    r = requests.post(f"{BASE}/inference", headers=hdr(), json={"overrides": overrides}, timeout=120)
    if r.status_code not in (200, 201):
        return jsonify(error=f"RunComfy inference {r.status_code}: {r.text[:300]}"), 502
    return jsonify(request_id=r.json().get("request_id"))


@app.get("/status/<request_id>")
def status(request_id):
    s = requests.get(f"{BASE}/requests/{request_id}/status", headers=hdr(), timeout=60).json()
    st = s.get("status")
    if st == "completed":
        res = requests.get(f"{BASE}/requests/{request_id}/result", headers=hdr(), timeout=60).json()
        urls = []
        for node in (res.get("outputs") or {}).values():
            for im in node.get("images", []):
                if im.get("url"):
                    urls.append(im["url"])
        return jsonify(status="completed", images=urls)
    if st in ("failed", "error"):
        return jsonify(status="failed", error=str(s)[:400])
    return jsonify(status=st, queue_position=s.get("queue_position"))


DEFAULT_PROMPT = ("将图1中的角色移至图2中，并调整为与图2角色相似的姿势。保持图1角色的外貌特征一致性，"
                  "重新进行光线处理，使其与图2场景的光线和整体氛围自然融合，确保无明显人工痕迹。")

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Change Background</title>
<style>
:root{color-scheme:light dark}*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:960px;margin:0 auto;padding:24px;background:#0f1115;color:#e7e9ee}
@media(prefers-color-scheme:light){body{background:#f6f7f9;color:#1a1d24}}
h1{font-size:20px;margin:0 0 4px}.sub{opacity:.6;font-size:13px;margin-bottom:20px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:640px){.row{grid-template-columns:1fr}}
.drop{border:2px dashed #3a4050;border-radius:12px;min-height:200px;display:flex;align-items:center;justify-content:center;text-align:center;cursor:pointer;overflow:hidden;position:relative;background:#171a21}
@media(prefers-color-scheme:light){.drop{background:#fff;border-color:#cfd4dd}}
.drop:hover{border-color:#5b8cff}.drop img{width:100%;height:100%;object-fit:contain;position:absolute;inset:0}.drop span{opacity:.6;font-size:13px;padding:12px}
label.lbl{font-size:13px;font-weight:600;display:block;margin:0 0 6px}
textarea{width:100%;min-height:70px;border-radius:10px;border:1px solid #3a4050;background:#171a21;color:inherit;padding:10px;font:inherit;margin-top:16px}
@media(prefers-color-scheme:light){textarea{background:#fff;border-color:#cfd4dd}}
button{margin-top:16px;width:100%;padding:13px;border:0;border-radius:10px;background:#5b8cff;color:#fff;font-weight:600;font-size:15px;cursor:pointer}button:disabled{opacity:.5}
#status{margin-top:16px;font-size:14px;min-height:20px}#result{margin-top:16px}#result img{max-width:100%;border-radius:12px;display:block;margin-bottom:10px}a.dl{font-size:13px;color:#5b8cff}
.spin{display:inline-block;width:14px;height:14px;border:2px solid #5b8cff;border-top-color:transparent;border-radius:50%;animation:s .8s linear infinite;vertical-align:-2px;margin-right:6px}@keyframes s{to{transform:rotate(360deg)}}
</style></head><body>
<h1>Change Background</h1>
<div class="sub">Upload a person and a scene &rarr; the character is placed into the scene with matched lighting. (RunComfy)</div>
<div class="row">
  <div><label class="lbl">1 &middot; Character / person</label><div class="drop" id="d1"><span>Click or drop image</span><input type="file" accept="image/*" hidden id="f1"></div></div>
  <div><label class="lbl">2 &middot; Scene / background</label><div class="drop" id="d2"><span>Click or drop image</span><input type="file" accept="image/*" hidden id="f2"></div></div>
</div>
<label class="lbl" style="margin-top:16px">Instruction (optional)</label>
<textarea id="prompt">__PROMPT__</textarea>
<button id="go">Generate</button>
<div id="status"></div><div id="result"></div>
<script>
const f1=document.getElementById('f1'),f2=document.getElementById('f2');
function wire(d,f){d.onclick=()=>f.click();['dragover','dragleave','drop'].forEach(e=>d.addEventListener(e,ev=>{ev.preventDefault();if(e==='drop'&&ev.dataTransfer.files[0]){f.files=ev.dataTransfer.files;show(d,f)}}));f.onchange=()=>show(d,f);}
function show(d,f){if(!f.files[0])return;d.innerHTML='<img src="'+URL.createObjectURL(f.files[0])+'">';}
wire(document.getElementById('d1'),f1);wire(document.getElementById('d2'),f2);
const go=document.getElementById('go'),stat=document.getElementById('status'),res=document.getElementById('result');
go.onclick=async()=>{
 if(!f1.files[0]||!f2.files[0]){stat.textContent='Please add both images.';return;}
 go.disabled=true;res.innerHTML='';stat.innerHTML='<span class=spin></span>Submitting...';
 const fd=new FormData();fd.append('person',f1.files[0]);fd.append('scene',f2.files[0]);fd.append('prompt',document.getElementById('prompt').value);
 try{const j=await(await fetch('/generate',{method:'POST',body:fd})).json();
  if(j.error){stat.textContent='Error: '+j.error;go.disabled=false;return;}
  const id=j.request_id;let t=0;
  const poll=async()=>{const s=await(await fetch('/status/'+id)).json();
   if(s.status==='completed'){stat.textContent='Done in '+t+'s.';res.innerHTML=(s.images||[]).map((u,i)=>'<img src="'+u+'"><a class=dl download="result_'+i+'.png" href="'+u+'">Download image '+(i+1)+'</a>').join('')||'(no images returned)';go.disabled=false;return;}
   if(s.status==='failed'){stat.textContent='Failed: '+(s.error||'');go.disabled=false;return;}
   t+=3;stat.innerHTML='<span class=spin></span>'+(s.status||'working')+'... '+t+'s'+(s.queue_position?(' (queue '+s.queue_position+')'):'');setTimeout(poll,3000);};
  poll();
 }catch(e){stat.textContent='Error: '+e;go.disabled=false;}
};
</script></body></html>"""

if __name__ == "__main__":
    print(f">> runcomfy deployment {DEP} | token {'set' if TOKEN else 'MISSING'} | nodes person={PERSON} scene={SCENE} prompt={PROMPT}")
    print(">> open http://localhost:5000")
    app.run(host="0.0.0.0", port=5000)
