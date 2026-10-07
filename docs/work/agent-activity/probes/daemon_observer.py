"""Read-only installed Codex Unix-WebSocket metadata observer; no thread resume."""
import base64, collections, json, os, pathlib, socket, struct, time
ROOT=pathlib.Path(__file__).resolve().parent

class WS:
    def __init__(self):
        self.s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.s.settimeout(5)
        self.s.connect(str(pathlib.Path.home()/'.codex/app-server-control/app-server-control.sock'))
        nonce=base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(('GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: '+nonce+'\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        header=bytearray()
        while b'\r\n\r\n' not in header:header.extend(self.s.recv(1))
        if not header.startswith(b'HTTP/1.1 101'):raise RuntimeError('WebSocket upgrade rejected')
        self.i=0;self.events=[]
        self.call('initialize',{'clientInfo':{'name':'crew_observer_probe','title':'Read-only Crew observer probe','version':'0.0.1'},'capabilities':{'experimentalApi':True}})
        self.send({'method':'initialized'})
    def send(self,message,opcode=1):
        data=json.dumps(message).encode();mask=os.urandom(4);n=len(data)
        header=bytes([0x80|opcode,0x80|n]) if n<126 else bytes([0x80|opcode,0x80|126])+struct.pack('>H',n)
        self.s.sendall(header+mask+bytes(x^mask[i%4] for i,x in enumerate(data)))
    def readn(self,n):
        data=bytearray()
        while len(data)<n:
            chunk=self.s.recv(n-len(data))
            if not chunk:raise EOFError('WebSocket closed')
            data.extend(chunk)
        return bytes(data)
    def receive(self):
        chunks=bytearray()
        while True:
            a,b=self.readn(2);opcode=a&15;n=b&127
            if n==126:n=struct.unpack('>H',self.readn(2))[0]
            elif n==127:n=struct.unpack('>Q',self.readn(8))[0]
            mask=self.readn(4) if b&128 else None;payload=self.readn(n)
            if mask:payload=bytes(x^mask[i%4] for i,x in enumerate(payload))
            if opcode==8:raise EOFError('WebSocket close frame')
            if opcode==9:continue
            chunks.extend(payload)
            if a&128:return json.loads(chunks)
    def call(self,method,params):
        self.i+=1;rid=self.i;self.send({'id':rid,'method':method,'params':params})
        while True:
            result=self.receive()
            if result.get('id')==rid and ('result' in result or 'error' in result):
                if 'error' in result:raise RuntimeError(str(result['error']))
                return result['result']
            self.events.append(result.get('method','other'))
    def close(self):self.s.close()

def main():
    client=WS()
    try:
        loaded=client.call('thread/loaded/list',{})['data'];snapshots=[]
        for tid in loaded:
            thread=client.call('thread/read',{'threadId':tid,'includeTurns':False})['thread']
            snapshots.append({'id':tid,'status':thread.get('status'),'source':thread.get('source'),'metadata_field_names':sorted(thread)})
        result={'transport':'Unix WebSocket','loaded_count':len(loaded),'snapshots':snapshots,'notification_methods':dict(collections.Counter(client.events))}
        (ROOT/'daemon-observer-summary.json').write_text(json.dumps(result,indent=2))
        print(json.dumps({'transport':result['transport'],'loaded_count':len(loaded),'statuses':[x['status'] for x in snapshots],'notification_methods':result['notification_methods']}))
    finally:client.close()
if __name__=='__main__':main()
