"""Disposable installed-Codex protocol probe. Raw logs remain in scratch only."""
import argparse, collections, json, os, pathlib, queue, subprocess, threading, time, tomllib

ROOT = pathlib.Path(__file__).resolve().parent

class RPC:
    def __init__(self, name, extra=None, proxy=False):
        self.name=name; self.n=0; self.pending={}; self.events=[]; self.q=queue.Queue()
        self.stderr=(ROOT/(name+'.stderr')).open('w')
        cmd=[str(pathlib.Path.home()/'.local/bin/codex'),'app-server']
        if proxy: cmd+=['proxy']
        else:
            cmd+=['--stdio','-c','model_reasoning_effort="low"','-c','analytics.enabled=false']
        cmd+=extra or []
        env=os.environ.copy();env['PATH']=str(pathlib.Path.home()/'.local/bin')+':/opt/homebrew/bin:'+env.get('PATH','/usr/bin:/bin')
        self.p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,text=True,bufsize=1,cwd=ROOT,env=env)
        self.raw=(ROOT/(name+'.wire.jsonl')).open('w')
        self.t=threading.Thread(target=self.read,daemon=True); self.t.start()
        self.call('initialize',{'clientInfo':{'name':'crew_validation','title':'Crew disposable validation','version':'0.0.1'},'capabilities':{'experimentalApi':True}})
        self.send({'method':'initialized'})
    def read(self):
        for line in self.p.stdout:
            try:msg=json.loads(line)
            except ValueError:continue
            entry={'received_ns':time.time_ns(),'message':msg}
            self.raw.write(json.dumps(entry)+'\n');self.raw.flush()
            self.events.append(entry);self.q.put(msg)
    def send(self,msg):
        self.p.stdin.write(json.dumps(msg)+'\n'); self.p.stdin.flush()
    def call(self,method,params=None,timeout=45):
        self.n+=1; req=self.n; self.send({'id':req,'method':method,'params':params or {}})
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:msg=self.q.get(timeout=max(.01,deadline-time.monotonic()))
            except queue.Empty:break
            if msg.get('id')==req and ('result' in msg or 'error' in msg):
                if 'error' in msg:raise RuntimeError(str(msg['error']))
                return msg['result']
        raise TimeoutError(method)
    def wait(self,predicate,timeout=120,handler=None):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:msg=self.q.get(timeout=min(1,max(.01,deadline-time.monotonic())))
            except queue.Empty:continue
            if handler:handler(msg)
            if predicate(msg):return msg
        raise TimeoutError('event wait')
    def close(self):
        try:self.p.stdin.close();self.p.wait(timeout=8)
        except subprocess.TimeoutExpired:self.p.terminate();self.p.wait(timeout=5)
        self.t.join(timeout=1);self.stderr.close();self.raw.close()

def hook_args(log):
    args=[]
    command=str(ROOT/'emit')+' '+str(ROOT/log)
    for event in ['SessionStart','SessionEnd','UserPromptSubmit','PreToolUse','PostToolUse','PermissionRequest','SubagentStart','SubagentStop','Stop','Interrupt']:
        args+=['-c',f'hooks.{event}=[{{hooks=[{{type="command",command="{command}",timeout=1}}]}}]']
    return args

def summarize(rpc):
    methods=collections.Counter(e['message'].get('method','response') for e in rpc.events)
    statuses=[e['message']['params']['status'] for e in rpc.events if e['message'].get('method')=='thread/status/changed']
    hooks=[{k:e['message']['params']['run'].get(k) for k in ['eventName','durationMs','status','sourcePath','executionMode']} for e in rpc.events if e['message'].get('method')=='hook/completed']
    return {'methods':dict(methods),'statuses':statuses,'hooks':hooks}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['inspect','daemon','normal','resume','permission','deny','question','subagents','tools','interrupt','continuation']); args=ap.parse_args()
    if args.action=='daemon':
        r=RPC('daemon-inspect',proxy=True)
        try:
            result=r.call('thread/loaded/list');print(json.dumps({'loaded_threads_count':len(result.get('data',[]))}))
            result=r.call('thread/list',{'limit':10})
            print(json.dumps({'thread_statuses':[x.get('status') for x in result.get('data',[])]}))
        finally:r.close()
        return
    r=RPC('inspect-'+args.action,hook_args('codex-hook-inputs.jsonl'))
    try:
        result=r.call('hooks/list',{'cwds':[str(ROOT)]})
        selected=[h for e in result['data'] for h in e['hooks'] if h['source']=='sessionFlags']
        (ROOT/'reviewed-hooks.json').write_text(json.dumps(selected))
        print(json.dumps({'hook_count':len(selected),'trust_states':collections.Counter(h['trustStatus'] for h in selected),'keys':[h['key'] for h in selected],'errors':[e['errors'] for e in result['data']]}))
    finally:r.close()
    if args.action=='inspect':return
    overrides=hook_args('codex-hook-inputs.jsonl')
    # The CLI key-path parser does not parse quoted dotted segments. Supply the
    # map as one TOML value; preserve existing trust entries without editing them.
    states=tomllib.loads((pathlib.Path.home()/'.codex/config.toml').read_text()).get('hooks',{}).get('state',{})
    for h in selected:states[h['key']]={'trusted_hash':h['currentHash']}
    inline='{'+','.join(json.dumps(k)+'={'+','.join(json.dumps(a)+'='+json.dumps(b) for a,b in v.items())+'}' for k,v in states.items())+'}'
    overrides+=['-c','hooks.state='+inline]
    if args.action=='continuation':
        command='python3 '+str(ROOT/'continue_once.py')
        overrides+=['-c',f'hooks.Stop=[{{hooks=[{{type="command",command="{str(ROOT/"emit")} {str(ROOT/"codex-hook-inputs.jsonl")}",timeout=1}},{{type="command",command="{command}",timeout=2}}]}}]']
        review=RPC('continuation-review',overrides)
        try:
            result=review.call('hooks/list',{'cwds':[str(ROOT)]})
            selected=[h for e in result['data'] for h in e['hooks'] if h['source']=='sessionFlags']
        finally:review.close()
        for h in selected:states[h['key']]={'trusted_hash':h['currentHash']}
        inline='{'+','.join(json.dumps(k)+'={'+','.join(json.dumps(a)+'='+json.dumps(b) for a,b in v.items())+'}' for k,v in states.items())+'}'
        overrides+=['-c','hooks.state='+inline]
    r=RPC('codex-'+args.action,overrides)
    try:
        config={'cwd':str(ROOT),'approvalPolicy':'on-request','sandbox':'read-only','developerInstructions':'You are running a bounded Crew validation. Do only what the prompt requests. Do not inspect any credentials, user configuration, repository, or other files. Do not use MCP, skills, or network tools.'}
        if args.action in ('permission','deny'):config['approvalsReviewer']='user'
        if args.action=='resume':
            config['threadId']=(ROOT/'codex-thread-id').read_text().strip();start=r.call('thread/resume',config)
        else:start=r.call('thread/start',config)
        thread=start['thread']['id']
        if args.action=='normal':(ROOT/'codex-thread-id').write_text(thread)
        prompts={
          'normal':'Run exactly this harmless shell command: /bin/sleep 2. Then reply with only CREW_PROBE_DONE.',
          'resume':'Reply with only CREW_CODEX_RESUMED. Do not call tools.',
          'permission':'Run /bin/sleep 2 using exec_command with shell_permissions=require_escalated, solely to exercise the permission fixture. Ask approval with a description of this harmless probe. Do not substitute another command. Then reply with CREW_APPROVED.',
          'deny':'Run /bin/sleep 2 using exec_command with shell_permissions=require_escalated to exercise a denial fixture. If approval is denied, do not retry or run any other tool; reply with CREW_DENIED.',
          'question':'Use request_user_input to ask me to choose Red or Blue. Wait for the answer, then reply with only the chosen color. Do not call any other tool.',
          'subagents':'Use spawn_agent to launch one helper which replies with only CREW_CHILD_DONE and uses no tools. Wait for the helper, then use resume_agent or send_input to ask that SAME helper to reply with CREW_CHILD_RESUMED. Wait again and close the helper. Reply with CREW_PARENT_DONE. Do not launch a second helper.',
          'tools':'Call exec_command separately and sequentially twenty times, each with the command /bin/sleep 0.01. Do not combine the calls in one command or code block. Then reply with only CREW_TOOLS_DONE.',
          'interrupt':'Run the command /bin/sleep 30. Then reply with CREW_SHOULD_BE_INTERRUPTED.',
          'continuation':'Reply with only CREW_FIRST_STOP. Do not call tools.'}
        params={'threadId':thread,'input':[{'type':'text','text':prompts[args.action]}],'effort':'low'}
        if args.action=='question':params['collaborationMode']={'mode':'plan','settings':{'model':'gpt-6.1-sol','reasoning_effort':'low','developer_instructions':'Run only the requested question-tool fixture, then finish after receiving the answer.'}}
        turn=r.call('turn/start',params)
        pending=[];interrupted=False
        def handler(msg):
            nonlocal interrupted
            method=msg.get('method','');pl=msg.get('params',{})
            if 'id' in msg and method.endswith('requestApproval'):
                pending.append({'method':method,'request_id':msg['id']});time.sleep(2)
                r.send({'id':msg['id'],'result':{'decision':'decline' if args.action=='deny' else 'accept'}})
            elif 'id' in msg and method=='item/tool/requestUserInput':
                pending.append({'method':method,'request_id':msg['id']});time.sleep(2)
                r.send({'id':msg['id'],'result':{'answers':{q['id']:{'answers':['Blue']} for q in pl.get('questions',[])}}})
            elif args.action=='interrupt' and method=='item/started' and pl.get('item',{}).get('type')=='commandExecution' and not interrupted:
                interrupted=True;r.n+=1;r.send({'id':r.n,'method':'turn/interrupt','params':{'threadId':thread,'turnId':turn['turn']['id']}})
        end=r.wait(lambda m:m.get('method')=='turn/completed' and m.get('params',{}).get('threadId')==thread,timeout=240,handler=handler)
        result=summarize(r);result['thread']=thread;result['outcome']=end.get('params',{}).get('turn',{}).get('status')
        print(json.dumps({'action':args.action,'outcome':result['outcome'],'statuses':result['statuses'],'methods':result['methods'],'hook_count':len(result['hooks'])}))
        result['pending_requests']=pending;result['interrupted_fixture']=interrupted
        (ROOT/('codex-'+args.action+'-summary.json')).write_text(json.dumps(result,indent=2))
    finally:r.close()

if __name__=='__main__':main()
