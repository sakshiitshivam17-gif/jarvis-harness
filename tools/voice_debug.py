import json,time,urllib.request,urllib.parse,websocket,subprocess
def http(p,m="GET"):
 r=urllib.request.Request("http://127.0.0.1:9225"+p,method=m); return json.load(urllib.request.urlopen(r,timeout=10))
t=http("/json/new?"+urllib.parse.quote("http://127.0.0.1:8765/",safe=':/?=&'),"PUT")
ws=websocket.create_connection(t["webSocketDebuggerUrl"],timeout=30,suppress_origin=True); q=0
def send(m,p=None):
 global q; q+=1; ws.send(json.dumps({"id":q,"method":m,"params":p or {}}))
 while True:
  r=json.loads(ws.recv())
  if r.get("id")==q: return r.get("result",{})
send("Runtime.enable"); send("Page.enable"); send("Page.navigate",{"url":"http://127.0.0.1:8765/"}); time.sleep(5)
send("Runtime.evaluate",{"expression":"document.getElementById('engage').click()"}); time.sleep(4)
done=None
for i in range(80):
 r=send("Runtime.evaluate",{"expression":"document.body.dataset.state","returnByValue":True})
 if r.get("result",{}).get("value")!="speaking": done=i; break
 time.sleep(.2)
print("ready",done)
subprocess.run(["ffplay","-nodisp","-autoexit","-loglevel","error","/home/sakshit/Music/jarvis_voice_test.wav"])
for i in range(6):
 time.sleep(2)
 r=send("Runtime.evaluate",{"expression":"JSON.stringify({snap:window.__jarvis.snapshot,interim:document.getElementById('interim-text').textContent,heard:document.getElementById('footer-heard').textContent,entries:[...document.querySelectorAll('.msg-body')].map(t=>t.textContent.slice(0,70))})","returnByValue":True})
 print(i,r.get("result",{}).get("value"))
ws.close()
