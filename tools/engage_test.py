#!/usr/bin/env python3
import json, sys, time, urllib.request, urllib.parse
import websocket
PORT = sys.argv[1] if len(sys.argv) > 1 else "9223"
URL = "http://127.0.0.1:8765/"
def http(path, method="GET"):
    req=urllib.request.Request(f"http://127.0.0.1:{PORT}{path}",method=method)
    return json.load(urllib.request.urlopen(req,timeout=10))
t=http("/json/new?"+urllib.parse.quote(URL,safe=':/?=&'),"PUT")
ws=websocket.create_connection(t["webSocketDebuggerUrl"],timeout=30,suppress_origin=True)
seq=0; events=[]
def send(m,params=None,collect=False):
    global seq; seq+=1
    ws.send(json.dumps({"id":seq,"method":m,"params":params or {}}))
    while True:
        msg=json.loads(ws.recv())
        if msg.get("method") in ("Runtime.exceptionThrown","Log.entryAdded","Runtime.consoleAPICalled"):
            events.append(msg)
        if msg.get("id")==seq: return msg.get("result",{})
send("Page.enable"); send("Runtime.enable"); send("Log.enable")
send("Emulation.setDeviceMetricsOverride",{"width":1600,"height":1000,"deviceScaleFactor":1,"mobile":False})
send("Page.navigate",{"url":URL})
time.sleep(5)
print("before", send("Runtime.evaluate",{"expression":"JSON.stringify({boot:document.getElementById('boot').className,engage:!document.getElementById('engage').hidden})","returnByValue":True}).get("result",{}).get("value"))
print("click", send("Runtime.evaluate",{"expression":"document.getElementById('engage').click(); 'clicked'","returnByValue":True}).get("result",{}).get("value"))
time.sleep(9)
expr="""JSON.stringify({
  state:document.body.dataset.state,
  engaged:!document.getElementById('app').classList.contains('is-locked'),
  appOpacity:getComputedStyle(document.getElementById('app')).opacity,
  boot:getComputedStyle(document.getElementById('boot')).display,
  toasts:[...document.querySelectorAll('.toast')].map(t=>t.textContent),
  entries:[...document.querySelectorAll('.msg')].map(m=>m.textContent.slice(0,80)),
  mic:!!(window.__mic),
  audio:document.getElementById('tts-audio').src.slice(0,40),
  audioPaused:document.getElementById('tts-audio').paused,
  note:document.getElementById('boot-note').textContent,
  interim:document.getElementById('interim-text').textContent,
  support:{sr:!!(window.SpeechRecognition||window.webkitSpeechRecognition),gum:!!(navigator.mediaDevices&&navigator.mediaDevices.getUserMedia)}
})"""
r=send("Runtime.evaluate",{"expression":expr,"returnByValue":True})
print("after",r.get("result",{}).get("value")); print("DETAIL", r.get("exceptionDetails",{}).get("text"), r.get("exceptionDetails",{}).get("exception",{}).get("description","")[:300])
print("ERRORS")
for e in events:
    if e.get("method")=="Runtime.exceptionThrown":
        print("EX", e["params"]["exceptionDetails"].get("text"), e["params"]["exceptionDetails"].get("exception",{}).get("description","")[:300])
    elif e.get("method")=="Log.entryAdded":
        print("LOG", e["params"]["entry"].get("level"), e["params"]["entry"].get("text")[:250])
    elif e.get("method")=="Runtime.consoleAPICalled":
        print("CON", e["params"]["type"], [a.get("value") for a in e["params"].get("args",[])][:3])
shot=send("Page.captureScreenshot",{"format":"png","fromSurface":True})
open("data/ui_engaged.png","wb").write(__import__("base64").b64decode(shot["data"]))
ws.close()
try: http(f"/json/close/{t['id']}")
except Exception: pass
