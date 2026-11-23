import json,time,urllib.request,urllib.parse,websocket
PORT="9224"
def http(path,method="GET"):
    req=urllib.request.Request(f"http://127.0.0.1:{PORT}{path}",method=method); return json.load(urllib.request.urlopen(req,timeout=10))
t=http("/json/new?"+urllib.parse.quote("http://127.0.0.1:8765/",safe=':/?=&'),"PUT")
ws=websocket.create_connection(t["webSocketDebuggerUrl"],timeout=30,suppress_origin=True); seq=0
def send(m,p=None):
    global seq; seq+=1; ws.send(json.dumps({"id":seq,"method":m,"params":p or {}}))
    while True:
        r=json.loads(ws.recv())
        if r.get("id")==seq: return r.get("result",{})
send("Runtime.enable"); send("Page.enable"); send("Page.navigate",{"url":"http://127.0.0.1:8765/"})
time.sleep(5)
send("Runtime.evaluate",{"expression":"document.getElementById('engage').click()"})
for i in range(6):
    time.sleep(5)
    r=send("Runtime.evaluate",{"expression":"JSON.stringify({snap:window.__jarvis.snapshot,interim:document.getElementById('interim-text').textContent,toasts:[...document.querySelectorAll('.toast')].map(t=>t.textContent),entries:[...document.querySelectorAll('.msg-body')].map(t=>t.textContent.slice(0,120))})","returnByValue":True})
    print(i, r.get("result",{}).get("value"))
ws.close()
