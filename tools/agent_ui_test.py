import json,time,urllib.request,urllib.parse,websocket
def http(p,m="GET"):
    r=urllib.request.Request("http://127.0.0.1:9222"+p,method=m); return json.load(urllib.request.urlopen(r,timeout=10))
t=http("/json/new?"+urllib.parse.quote("http://127.0.0.1:8765/",safe=':/?=&'),"PUT")
ws=websocket.create_connection(t["webSocketDebuggerUrl"],timeout=30,suppress_origin=True); q=0
def send(m,p=None):
    global q; q+=1; ws.send(json.dumps({"id":q,"method":m,"params":p or {}}))
    while True:
        r=json.loads(ws.recv())
        if r.get("id")==q: return r.get("result",{})
send("Runtime.enable"); send("Page.enable"); send("Page.navigate",{"url":"http://127.0.0.1:8765/"}); time.sleep(5)
send("Runtime.evaluate",{"expression":"document.getElementById('engage').click()"}); time.sleep(3)
send("Runtime.evaluate",{"expression":"document.getElementById('manual-input').value='click 7 in the calculator'; document.getElementById('manual-form').dispatchEvent(new Event('submit'))"})
for i in range(30):
    time.sleep(1)
    r=send("Runtime.evaluate",{"expression":"JSON.stringify({bar:!document.getElementById('agent-bar').hidden,rows:document.querySelectorAll('#agent-trace li').length,step:document.getElementById('agent-step').textContent,badges:[...document.querySelectorAll('.badge')].map(b=>b.textContent),last:[...document.querySelectorAll('.agent-trace li')].map(l=>l.textContent).slice(-2)})","returnByValue":True})
    d=json.loads(r.get("result",{}).get("value","{}"))
    if d.get("bar"): print(i,d)
    if "AGENT" in (d.get("badges") or []) and not d.get("bar"): print("done",d); break
ws.close()
