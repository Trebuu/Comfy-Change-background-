"""
RunPod Serverless handler for ComfyUI (Trebuu/Comfy stack).

Request format (job["input"]):
{
  "workflow": { ... },                 # REQUIRED, ComfyUI *API-format* graph
  "images":  [                         # OPTIONAL input images to inject
     {"name": "person.jpg", "image": "<base64>"},
     {"name": "garment.jpg", "image": "<base64>"}
  ]
}
The workflow's LoadImage nodes must reference the given image `name`s.

Response:
{ "images": [ {"filename": "...", "type": "base64", "data": "<base64>"} ] }
"""
import base64
import os
import time
import uuid
import json
import urllib.request
import urllib.parse

import runpod

COMFY = "http://127.0.0.1:8188"
BOOT_TIMEOUT = int(os.environ.get("COMFY_BOOT_TIMEOUT", "300"))   # wait for server
JOB_TIMEOUT = int(os.environ.get("COMFY_JOB_TIMEOUT", "1800"))    # per generation
POLL = 0.5


def _post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{COMFY}{path}", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def _get(path):
    with urllib.request.urlopen(f"{COMFY}{path}") as r:
        return r.read()


def _get_json(path):
    return json.loads(_get(path))


def wait_for_comfy():
    deadline = time.time() + BOOT_TIMEOUT
    while time.time() < deadline:
        try:
            _get("/system_stats")
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("ComfyUI did not come up within COMFY_BOOT_TIMEOUT")


def upload_image(name, b64):
    """Upload a base64 image to ComfyUI's input dir under the given name."""
    raw = base64.b64decode(b64)
    boundary = uuid.uuid4().hex
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'.encode()
    body += b"Content-Type: application/octet-stream\r\n\r\n"
    body += raw + b"\r\n"
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{COMFY}/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def queue_prompt(workflow, client_id):
    return _post("/prompt", {"prompt": workflow, "client_id": client_id})


def collect_outputs(prompt_id):
    """Poll /history until the prompt finishes, then return output images as base64."""
    deadline = time.time() + JOB_TIMEOUT
    while time.time() < deadline:
        hist = _get_json(f"/history/{prompt_id}")
        if prompt_id in hist:
            entry = hist[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI reported error: {json.dumps(status)}")
            if entry.get("outputs"):
                images = []
                for node_out in entry["outputs"].values():
                    for img in node_out.get("images", []):
                        q = urllib.parse.urlencode({
                            "filename": img["filename"],
                            "subfolder": img.get("subfolder", ""),
                            "type": img.get("type", "output"),
                        })
                        data = _get(f"/view?{q}")
                        images.append({
                            "filename": img["filename"],
                            "type": "base64",
                            "data": base64.b64encode(data).decode(),
                        })
                if images:
                    return images
        time.sleep(POLL)
    raise RuntimeError("Timed out waiting for ComfyUI generation (COMFY_JOB_TIMEOUT)")


def handler(job):
    inp = job.get("input") or {}
    workflow = inp.get("workflow")
    if not workflow:
        return {"error": "missing 'workflow' (must be ComfyUI API-format graph)"}

    for im in inp.get("images", []):
        try:
            upload_image(im["name"], im["image"])
        except Exception as e:
            return {"error": f"failed to upload image {im.get('name')}: {e}"}

    client_id = str(uuid.uuid4())
    try:
        resp = queue_prompt(workflow, client_id)
    except Exception as e:
        return {"error": f"failed to queue prompt: {e}"}

    prompt_id = resp.get("prompt_id")
    if not prompt_id:
        return {"error": f"no prompt_id returned: {resp}"}

    try:
        images = collect_outputs(prompt_id)
    except Exception as e:
        return {"error": str(e)}

    return {"images": images}


wait_for_comfy()
runpod.serverless.start({"handler": handler})
