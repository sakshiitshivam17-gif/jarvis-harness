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
send("Runtime.enable"); send("Page.enable"); send("Page.navigate",{"url":"http://127.0.0.1:8765/"})
time.sleep(5); send("Runtime.evaluate",{"expression":"document.getElementById('engage').click()"}); time.sleep(4)
for _ in range(80):
    r=send("Runtime.evaluate",{"expression":"document.body.dataset.state","returnByValue":True})
    if r.get('result',{}).get('value') != 'speaking': break
    time.sleep(.2)
print('READY', r.get('result',{}).get('value'))
send("Runtime.evaluate",{"expression":"window.__t0=performance.now(); window.__jarvis.say('Jarvis, what time is it?'); 'go'"})
start=time.time(); first=None
for i in range(80):
    time.sleep(.1)
    r=send("Runtime.evaluate",{"expression":"JSON.stringify({paused:document.getElementById('tts-audio').paused,ct:document.getElementById('tts-audio').currentTime,src:document.getElementById('tts-audio').src,state:document.body.dataset.state,entries:[...document.querySelectorAll('.msg-body')].map(n=>n.textContent.slice(0,40))})","returnByValue":True})
    d=json.loads(r.get("result",{}).get("value","{}"))
    if first is None and d.get("ct",0)>0:
        first=time.time()-start; print("FIRST AUDIO",round(first,2),d)
    if d.get("state")=="listening" and first is not None:
        print("RETURN LISTENING",round(time.time()-start,2),d); break
print("entries", d.get("entries"))
ws.close()
