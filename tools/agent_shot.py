import json,time,urllib.request,urllib.parse,websocket,base64
def http(p,m="GET"):
    r=urllib.request.Request("http://127.0.0.1:9222"+p,method=m); return json.load(urllib.request.urlopen(r,timeout=10))
t=http("/json/new?"+urllib.parse.quote("http://127.0.0.1:8765/",safe=':/?=&'),"PUT")
ws=websocket.create_connection(t["webSocketDebuggerUrl"],timeout=30,suppress_origin=True); q=0
def send(m,p=None):
    global q; q+=1; ws.send(json.dumps({"id":q,"method":m,"params":p or {}}))
    while True:
        r=json.loads(ws.recv())
        if r.get("id")==q: return r.get("result",{})
send("Runtime.enable"); send("Page.enable")
send("Emulation.setDeviceMetricsOverride",{"width":1600,"height":1000,"deviceScaleFactor":1,"mobile":False})
send("Page.navigate",{"url":"http://127.0.0.1:8765/?demo=1"}); time.sleep(6)
send("Page.captureScreenshot",{"format":"png"}); 
shot=send("Page.captureScreenshot",{"format":"png","fromSurface":True})
open("docs/preview.png","wb").write(base64.b64decode(shot["data"]))
# agent trace visual
send("Runtime.evaluate",{"expression":"document.getElementById('agent-bar').hidden=false; document.getElementById('agent-task').textContent='clear the calculator and compute 8 times 6'; const rows=[['01','click','C',0],['02','click','8',0],['03','click','×',0],['04','click','6',0],['05','click','=',0]]; document.getElementById('agent-trace').innerHTML=rows.map(r=>`<li class=\"${r[3]?'fail':'ok'}\"><b>${r[0]}</b><span class=\"verb\">${r[1]}</span><span>${r[2]}</span></li>`).join(''); document.getElementById('agent-step').textContent='STEP 5';"})
time.sleep(1)
shot=send("Page.captureScreenshot",{"format":"png","fromSurface":True})
open("docs/agent.png","wb").write(base64.b64decode(shot["data"]))
ws.close()
