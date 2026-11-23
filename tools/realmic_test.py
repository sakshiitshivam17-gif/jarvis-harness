import json,time,urllib.request,urllib.parse,websocket,subprocess
PORT="9225"
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
time.sleep(5); send("Runtime.evaluate",{"expression":"document.getElementById('engage').click()"})
time.sleep(4)
print("playing")
subprocess.run(["ffplay","-nodisp","-autoexit","-loglevel","error","/home/sakshit/Music/jarvis_voice_test.wav"])
for i in range(4):
    time.sleep(3)
    r=send("Runtime.evaluate",{"expression":"JSON.stringify({snap:window.__jarvis.snapshot,interim:document.getElementById('interim-text').textContent,entries:[...document.querySelectorAll('.msg-body')].map(t=>t.textContent.slice(0,90)),toasts:[...document.querySelectorAll('.toast')].map(t=>t.textContent)})","returnByValue":True})
    print(i,r.get("result",{}).get("value"))
ws.close()
