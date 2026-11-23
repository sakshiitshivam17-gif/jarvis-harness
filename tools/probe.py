#!/usr/bin/env python3
import json, sys, time, urllib.request
import websocket
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/?demo=1"
WAIT = float(sys.argv[2]) if len(sys.argv) > 2 else 5
EXPR = sys.argv[3] if len(sys.argv) > 3 else """JSON.stringify({
  viewport:[innerWidth,innerHeight],
  scroll:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],
  fonts:{orbitron:document.fonts.check('16px Orbitron'),rajdhani:document.fonts.check('16px Rajdhani')},
  boot:getComputedStyle(document.getElementById('boot')).display,
  panels:[...document.querySelectorAll('.panel')].map(p=>({c:p.className,r:p.getBoundingClientRect().toJSON(),sw:p.scrollWidth,sh:p.scrollHeight,cw:p.clientWidth,ch:p.clientHeight})),
  reactor:document.querySelector('.reactor').getBoundingClientRect().toJSON(),
  feed:{r:document.querySelector('.feed').getBoundingClientRect().toJSON(),sw:document.querySelector('.feed').scrollWidth,sh:document.querySelector('.feed').scrollHeight},
  chips:[...document.querySelectorAll('.chip')].map(c=>({t:c.textContent.trim(),r:c.getBoundingClientRect().toJSON()})),
  status:document.body.dataset.state,
  entries:document.querySelectorAll('.msg').length
})"""
def http(path, method="GET"):
    req = urllib.request.Request(f"http://127.0.0.1:9222{path}", method=method)
    return json.load(urllib.request.urlopen(req, timeout=10))
import urllib.parse
target = http("/json/new?" + urllib.parse.quote(URL, safe=":/?=&"), "PUT")
ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
seq=0
def send(method, params=None):
    global seq; seq+=1
    ws.send(json.dumps({"id":seq,"method":method,"params":params or {}}))
    while True:
        msg=json.loads(ws.recv())
        if msg.get("id")==seq: return msg.get("result",{})
send("Page.enable"); send("Runtime.enable")
import os
send("Emulation.setDeviceMetricsOverride", {"width":int(os.environ.get("PROBE_W","1600")),"height":int(os.environ.get("PROBE_H","1000")),"deviceScaleFactor":1,"mobile":False})
send("Page.navigate", {"url":URL}); time.sleep(WAIT)
r=send("Runtime.evaluate", {"expression":EXPR,"returnByValue":True,"awaitPromise":True})
print(r.get("result",{}).get("value"))
ws.close()
try: http(f"/json/close/{target['id']}")
except Exception: pass
