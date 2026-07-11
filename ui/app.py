#!/usr/bin/env python3
"""
Generic local web UI for RunComfy serverless deployments.

Pick any of your deployments; the app reads its workflow, auto-detects the inputs
(LoadImage -> image upload, prompt/text nodes -> text fields, KSampler -> seed) and
renders the right form. Works for the Change-background, Pose Generator, etc.

Run:
    pip install flask requests
    export RUNCOMFY_TOKEN=your_api_token
    python app.py            # -> http://localhost:5000
Your token stays server-side. Results come back as image URLs (valid 7 days).
"""
import os, base64, requests
from flask import Flask, request, jsonify, Response

TOKEN = os.environ.get("RUNCOMFY_TOKEN", "")
API   = "https://api.runcomfy.net/prod/v2/deployments"
app = Flask(__name__)
def hdr(): return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def detect_inputs(wf):
    """Return ordered user-facing fields from a workflow_api_json."""
    imgs, texts, seeds = [], [], []
    for nid, n in wf.items():
        ct = n.get("class_type", ""); ins = n.get("inputs", {})
        title = (n.get("_meta") or {}).get("title") or ct
        if ct in ("LoadImage", "LoadImageOutput"):
            imgs.append({"node": nid, "kind": "image", "label": f"{title}  (node {nid})"})
            continue
        for k in ("prompt", "text"):   # main editable text inputs
            if k in ins and isinstance(ins[k], str):
                texts.append({"node": nid, "kind": "text", "input": k, "default": ins[k],
                              "label": f"{title} [{k}]  (node {nid})",
                              "long": len(ins[k]) > 120})
        if ct == "KSampler" and not isinstance(ins.get("seed"), list):
            seeds.append({"node": nid, "kind": "seed", "input": "seed",
                          "label": f"Seed  (node {nid})", "default": ins.get("seed")})
    return imgs + texts + seeds


@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")


@app.get("/api/deployments")
def deployments():
    if not TOKEN:
        return jsonify(error="RUNCOMFY_TOKEN is not set on the server"), 400
    r = requests.get(API, headers=hdr(), timeout=30)
    if r.status_code != 200:
        return jsonify(error=f"list {r.status_code}: {r.text[:200]}"), 502
    return jsonify([{"id": d["id"], "name": d.get("name", d["id"]),
                     "hardware": d.get("hardware"), "status": d.get("status")} for d in r.json()])


@app.get("/api/schema/<dep>")
def schema(dep):
    r = requests.get(f"{API}/{dep}", headers=hdr(), timeout=30)
    if r.status_code != 200:
        return jsonify(error=f"schema {r.status_code}: {r.text[:200]}"), 502
    wf = (r.json().get("payload") or {}).get("workflow_api_json") or {}
    return jsonify(fields=detect_inputs(wf), name=r.json().get("name"))


@app.post("/api/generate/<dep>")
def generate(dep):
    if not TOKEN:
        return jsonify(error="RUNCOMFY_TOKEN is not set"), 400
    overrides = {}
    # images: form file field name = node id
    for node, f in request.files.items():
        mime = f.mimetype or "image/png"
        uri = f"data:{mime};base64," + base64.b64encode(f.read()).decode()
        overrides.setdefault(node, {"inputs": {}})["inputs"]["image"] = uri
    # text/seed: form fields named "<node>:<input>"
    for key, val in request.form.items():
        if ":" not in key or val == "":
            continue
        node, inp = key.split(":", 1)
        v = int(val) if inp == "seed" and val.lstrip("-").isdigit() else val
        overrides.setdefault(node, {"inputs": {}})["inputs"][inp] = v
    if not overrides:
        return jsonify(error="nothing to submit"), 400
    r = requests.post(f"{API}/{dep}/inference", headers=hdr(), json={"overrides": overrides}, timeout=120)
    if r.status_code not in (200, 201):
        return jsonify(error=f"inference {r.status_code}: {r.text[:300]}"), 502
    return jsonify(request_id=r.json().get("request_id"))


@app.get("/api/status/<dep>/<req>")
def status(dep, req):
    s = requests.get(f"{API}/{dep}/requests/{req}/status", headers=hdr(), timeout=60).json()
    st = s.get("status")
    if st in ("completed", "succeeded"):
        res = requests.get(f"{API}/{dep}/requests/{req}/result", headers=hdr(), timeout=60).json()
        urls = [im["url"] for node in (res.get("outputs") or {}).values()
                for im in node.get("images", []) if im.get("url")]
        return jsonify(status="completed", images=urls)
    if st in ("failed", "error"):
        return jsonify(status="failed", error=str(s)[:400])
    return jsonify(status=st, queue_position=s.get("queue_position"))


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>RunComfy Dashboard</title>
<style>
:root{color-scheme:light dark}*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:900px;margin:0 auto;padding:24px;background:#0f1115;color:#e7e9ee}
@media(prefers-color-scheme:light){body{background:#f6f7f9;color:#1a1d24}}
h1{font-size:20px;margin:0 0 12px}
select,input,textarea{width:100%;border-radius:10px;border:1px solid #3a4050;background:#171a21;color:inherit;padding:10px;font:inherit}
@media(prefers-color-scheme:light){select,input,textarea{background:#fff;border-color:#cfd4dd}}
label.lbl{font-size:13px;font-weight:600;display:block;margin:16px 0 6px}
.drop{border:2px dashed #3a4050;border-radius:12px;min-height:160px;display:flex;align-items:center;justify-content:center;text-align:center;cursor:pointer;overflow:hidden;position:relative;background:#171a21}
@media(prefers-color-scheme:light){.drop{background:#fff;border-color:#cfd4dd}}
.drop:hover{border-color:#5b8cff}.drop img{width:100%;height:100%;object-fit:contain;position:absolute;inset:0}.drop span{opacity:.6;font-size:13px;padding:12px}
.imgs{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
button{margin-top:18px;width:100%;padding:13px;border:0;border-radius:10px;background:#5b8cff;color:#fff;font-weight:600;font-size:15px;cursor:pointer}button:disabled{opacity:.5}
#status{margin-top:14px;font-size:14px;min-height:20px}
#result{margin-top:16px;display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
#result figure{margin:0}#result img{width:100%;border-radius:10px;display:block}#result a{font-size:12px;color:#5b8cff}
.spin{display:inline-block;width:14px;height:14px;border:2px solid #5b8cff;border-top-color:transparent;border-radius:50%;animation:s .8s linear infinite;vertical-align:-2px;margin-right:6px}@keyframes s{to{transform:rotate(360deg)}}
small{opacity:.55}
</style></head><body>
<h1>RunComfy Dashboard</h1>
<label class="lbl">Deployment</label>
<select id="dep"></select>
<form id="form"></form>
<button id="go" disabled>Generate</button>
<div id="status"></div><div id="result"></div>
<script>
const depSel=document.getElementById('dep'),form=document.getElementById('form'),go=document.getElementById('go'),stat=document.getElementById('status'),res=document.getElementById('result');
let fields=[];
async function loadDeps(){
 const r=await fetch('/api/deployments');const d=await r.json();
 if(d.error){stat.textContent='Error: '+d.error;return;}
 depSel.innerHTML=d.map(x=>'<option value="'+x.id+'">'+x.name+'  ['+(x.hardware||'')+']</option>').join('');
 loadSchema();
}
async function loadSchema(){
 go.disabled=true;form.innerHTML='<small>loading inputs...</small>';res.innerHTML='';stat.textContent='';
 const r=await fetch('/api/schema/'+depSel.value);const d=await r.json();
 if(d.error){form.innerHTML='<small>Error: '+d.error+'</small>';return;}
 fields=d.fields;let h='';const imgs=fields.filter(f=>f.kind==='image');
 if(imgs.length){h+='<div class=imgs>'+imgs.map(f=>'<div><label class=lbl>'+f.label+'</label><div class=drop data-node="'+f.node+'"><span>Click or drop image</span><input type=file accept=image/* hidden></div></div>').join('')+'</div>';}
 fields.filter(f=>f.kind==='text').forEach(f=>{h+='<label class=lbl>'+f.label+'</label>'+(f.long?'<textarea rows=3 name="'+f.node+':'+f.input+'">':'<input name="'+f.node+':'+f.input+'" value="')+(f.long?(f.default||''):(f.default||'').toString().replace(/"/g,'&quot;'))+(f.long?'</textarea>':'">');});
 fields.filter(f=>f.kind==='seed').forEach(f=>{h+='<label class=lbl>'+f.label+' <small>(blank = keep '+f.default+')</small></label><input type=number name="'+f.node+':seed" placeholder="'+f.default+'">';});
 form.innerHTML=h;
 form.querySelectorAll('.drop').forEach(d=>{const inp=d.querySelector('input');d.onclick=()=>inp.click();['dragover','dragleave','drop'].forEach(e=>d.addEventListener(e,ev=>{ev.preventDefault();if(e==='drop'&&ev.dataTransfer.files[0]){inp.files=ev.dataTransfer.files;show(d,inp);}}));inp.onchange=()=>show(d,inp);});
 go.disabled=false;
}
function show(d,inp){if(inp.files[0])d.innerHTML='<img src="'+URL.createObjectURL(inp.files[0])+'">';}
depSel.onchange=loadSchema;
go.onclick=async()=>{
 const fd=new FormData();
 form.querySelectorAll('.drop').forEach(d=>{const inp=d.querySelector('input');if(inp.files[0])fd.append(d.dataset.node,inp.files[0]);});
 form.querySelectorAll('[name]').forEach(el=>{if(el.value!=='')fd.append(el.name,el.value);});
 go.disabled=true;res.innerHTML='';stat.innerHTML='<span class=spin></span>Submitting...';
 try{const j=await(await fetch('/api/generate/'+depSel.value,{method:'POST',body:fd})).json();
  if(j.error){stat.textContent='Error: '+j.error;go.disabled=false;return;}
  const id=j.request_id;let t=0;
  const poll=async()=>{const s=await(await fetch('/api/status/'+depSel.value+'/'+id)).json();
   if(s.status==='completed'){stat.textContent='Done in '+t+'s - '+(s.images||[]).length+' image(s).';res.innerHTML=(s.images||[]).map((u,i)=>'<figure><img src="'+u+'"><a download="out_'+i+'.png" href="'+u+'">download</a></figure>').join('')||'(no images)';go.disabled=false;return;}
   if(s.status==='failed'){stat.textContent='Failed: '+(s.error||'');go.disabled=false;return;}
   t+=3;stat.innerHTML='<span class=spin></span>'+(s.status||'working')+'... '+t+'s'+(s.queue_position?(' (queue '+s.queue_position+')'):'');setTimeout(poll,3000);};
  poll();
 }catch(e){stat.textContent='Error: '+e;go.disabled=false;}
};
loadDeps();
</script></body></html>"""

if __name__ == "__main__":
    print(f">> RunComfy dashboard | token {'set' if TOKEN else 'MISSING'} | open http://localhost:5000")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
