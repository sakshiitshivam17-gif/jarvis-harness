#!/usr/bin/env python3
"""Capture the JARVIS UI through the Chrome DevTools Protocol."""
import base64, json, sys, time, urllib.request
import websocket

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/?demo=1"
OUT = sys.argv[2] if len(sys.argv) > 2 else "data/ui.png"
W = int(sys.argv[3]) if len(sys.argv) > 3 else 1600
H = int(sys.argv[4]) if len(sys.argv) > 4 else 1000
WAIT = float(sys.argv[5]) if len(sys.argv) > 5 else 5.0

def http(path, method="GET"):
    req = urllib.request.Request(f"http://127.0.0.1:9222{path}", method=method)
    return json.load(urllib.request.urlopen(req, timeout=10))

# create a fresh tab
target = http("/json/new?" + urllib.parse.quote(URL, safe=":/?=&"), "PUT")
ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=30,
                                 suppress_origin=True)
seq = 0
def send(method, params=None):
    global seq
    seq += 1
    ws.send(json.dumps({"id": seq, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == seq:
            if "error" in msg:
                print("CDP ERROR", method, msg["error"])
            return msg.get("result", {})

send("Page.enable")
send("Runtime.enable")
send("Emulation.setDeviceMetricsOverride", {"width": W, "height": H, "deviceScaleFactor": 1, "mobile": False})
send("Page.navigate", {"url": URL})
time.sleep(WAIT)
res = send("Runtime.evaluate", {"expression": "JSON.stringify({title:document.title,state:document.body.dataset.state,engaged:!document.getElementById('app').classList.contains('is-locked'),entries:document.querySelectorAll('.msg').length,boot:getComputedStyle(document.getElementById('boot')).display})", "returnByValue": True})
print("PAGE", res.get("result", {}).get("value"))
shot = send("Page.captureScreenshot", {"format": "png", "fromSurface": True, "captureBeyondViewport": False})
open(OUT, "wb").write(base64.b64decode(shot["data"]))
print("WROTE", OUT)
ws.close()
http(f"/json/close/{target['id']}")
