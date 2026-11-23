import json,sys,urllib.request
port=sys.argv[1]; expr=sys.argv[2]
def http(path,method="GET"):
    req=urllib.request.Request(f"http://127.0.0.1:{port}{path}",method=method); return json.load(urllib.request.urlopen(req,timeout=10))
targets=http("/json/list")
# pick newest page to 8765
pages=[t for t in targets if t.get("type")=="page" and "8765" in t.get("url","")]
if not pages:
    print("NO PAGE"); sys.exit()
import websocket
ws=websocket.create_connection(pages[0]["webSocketDebuggerUrl"],timeout=20,suppress_origin=True)
ws.send(json.dumps({"id":1,"method":"Runtime.evaluate","params":{"expression":expr,"returnByValue":True}}))
while True:
    m=json.loads(ws.recv())
    if m.get("id")==1:
        print(json.dumps(m.get("result",{}),indent=2)[:4000]); break
ws.close()
