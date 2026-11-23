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
send("Page.enable"); send("Runtime.enable"); send("Page.navigate",{"url":"http://127.0.0.1:8765/"}); time.sleep(5)
send("Runtime.evaluate",{"expression":"document.getElementById('engage').click()"}); time.sleep(4)
print(send("Runtime.evaluate",{"expression":"document.getElementById('screen-btn').click(); 'clicked'","returnByValue":True}).get("result",{}).get("value"))
for i in range(18):
    time.sleep(1)
    r=send("Runtime.evaluate",{"expression":"JSON.stringify({state:document.body.dataset.state,imgs:[...document.querySelectorAll('.msg-image')].map(i=>i.src),badges:[...document.querySelectorAll('.badge')].map(b=>b.textContent),code:document.querySelectorAll('.code-block').length,body:[...document.querySelectorAll('.msg-body')].map(n=>n.textContent.slice(0,50))})","returnByValue":True})
    d=json.loads(r.get("result",{}).get("value","{}"))
    if d.get("imgs"): print("GOT",i,d); break
else: print("NO",d)
ws.close()
