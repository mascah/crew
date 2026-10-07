"""Disposable Claude CLI probe using installed stream-json and native hooks."""
import argparse, collections, json, pathlib, queue, subprocess, threading, time, uuid

ROOT=pathlib.Path(__file__).resolve().parent

def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['normal','resume','permission','question','subagents','helper_resume','continuation','tools']);args=ap.parse_args()
    command=str(ROOT/'emit')+' '+str(ROOT/'claude-hook-inputs.jsonl')
    hooks={e:[{'hooks':[{'type':'command','command':command,'timeout':1}]}] for e in ['SessionStart','SessionEnd','UserPromptSubmit','PreToolUse','PostToolUse','PostToolUseFailure','PermissionRequest','Notification','Stop','StopFailure','SubagentStart','SubagentStop','Elicitation','ElicitationResult']}
    if args.action=='continuation':
        hooks['Stop'].append({'hooks':[{'type':'command','command':'python3 '+str(ROOT/'continue_once.py'),'timeout':2}]})
    settings=ROOT/('claude-'+args.action+'-settings.json');settings.write_text(json.dumps({'hooks':hooks,'enableAllProjectMcpServers':False}))
    session=(ROOT/'claude-session-id').read_text().strip() if args.action=='resume' else str(uuid.uuid4())
    if args.action=='helper_resume':session=json.loads((ROOT/'claude-subagents-summary.json').read_text())['session_id']
    cmd=[str(pathlib.Path.home()/'.local/bin/claude'),'--print','--input-format','stream-json','--output-format','stream-json','--verbose','--include-hook-events','--setting-sources','','--settings',str(settings),'--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--effort','low','--max-budget-usd','2','--permission-mode','manual' if args.action=='permission' else 'default','--tools','Bash,Agent,SendMessage,AskUserQuestion','--system-prompt','You are running a bounded Crew validation. Do only the explicit harmless probe. Do not read user configuration, credentials, repositories, or other files. Do not use skills, MCP, or network tools. Reply briefly.']
    cmd+=['--resume',session] if args.action in ('resume','helper_resume') else ['--session-id',session]
    if args.action not in ('permission','question'):
        cmd+=['--allowedTools','Bash(/bin/sleep *)']
    else:
        cmd+=['--permission-prompt-tool','stdio']
    q=queue.Queue();events=[];started=time.monotonic()
    stderr=(ROOT/('claude-'+args.action+'.stderr')).open('w');raw=(ROOT/('claude-'+args.action+'.wire.jsonl')).open('w')
    p=subprocess.Popen(cmd,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,text=True,bufsize=1)
    def reader():
        for line in p.stdout:
            try:m=json.loads(line)
            except ValueError:continue
            e={'received_ns':time.time_ns(),'message':m};events.append(e);raw.write(json.dumps(e)+'\n');raw.flush();q.put(m)
        q.put({'probe_eof':True})
    t=threading.Thread(target=reader,daemon=True);t.start()
    prompts={
        'normal':'Run exactly this harmless Bash command: /bin/sleep 2. Then reply with only CREW_CLAUDE_DONE.',
        'resume':'Reply with only CREW_CLAUDE_RESUMED. Do not call any tools.',
        'permission':'Run exactly this harmless Bash command: /bin/sleep 2. Do not substitute another command. Then reply with only CREW_PERMISSION_DONE.',
        'question':'Use AskUserQuestion to ask me to choose Red or Blue. Wait for the answer, then reply with only the chosen color.',
        'subagents':'Use the Agent tool to launch one helper that replies with only CREW_CHILD_DONE without tools. Wait for the helper, then reply with only CREW_PARENT_DONE.',
        'continuation':'Reply with only CREW_FIRST_STOP. Do not call tools.',
        'tools':'Call Bash separately and sequentially twenty times, each running /bin/sleep 0.01. Do not combine the calls. Then reply with CREW_CLAUDE_TOOLS_DONE.',
        'helper_resume':'placeholder'}
    if args.action=='helper_resume':
        records=[json.loads(x)['payload'] for x in (ROOT/'claude-hook-inputs.jsonl').read_text().splitlines()]
        child=next(r['agent_id'] for r in records if r.get('hook_event_name')=='SubagentStop' and r.get('session_id')==session)
        prompts['helper_resume']='Use SendMessage targeting '+child+' to resume that SAME helper and ask it to reply with CREW_CHILD_RESUMED without tools or file reads. Do not spawn a replacement. Wait for the helper response, then reply with CREW_PARENT_RESUMED.'
    p.stdin.write(json.dumps({'type':'user','session_id':session,'message':{'role':'user','content':prompts[args.action]},'parent_tool_use_id':None})+'\n');p.stdin.flush()
    # Stream-json --print waits for EOF after its submitted request. Keep stdin
    # open only for hosted permission/question control messages.
    if args.action not in ('permission','question'):p.stdin.close()
    controls=[];result=None
    try:
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            try:m=q.get(timeout=1)
            except queue.Empty:
                if p.poll() is not None:break
                continue
            if m.get('probe_eof'):break
            if m.get('type')=='control_request':
                req=m.get('request',{});controls.append({'subtype':req.get('subtype'),'tool_name':req.get('tool_name')})
                if req.get('subtype')=='can_use_tool':
                    # A native hosted approval is held open briefly and answered
                    # by this controlled fixture; it is not a human UI timing test.
                    time.sleep(7 if args.action=='permission' else 2)
                    inp=req.get('input',{})
                    if req.get('tool_name')=='AskUserQuestion':
                        inp=dict(inp);inp['answers']={x['question']:'Blue' for x in inp.get('questions',[])}
                    response={'type':'control_response','response':{'subtype':'success','request_id':m['request_id'],'response':{'behavior':'allow','updatedInput':inp}}}
                    p.stdin.write(json.dumps(response)+'\n');p.stdin.flush()
            if m.get('type')=='result':result=m;break
        if result is None:raise RuntimeError('no result before exit/timeout')
    finally:
        if not p.stdin.closed:p.stdin.close()
        try:p.wait(timeout=8)
        except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=5)
        t.join(timeout=1);raw.close();stderr.close()
    summary={'action':args.action,'session_id':session,'process_exit':p.returncode,'wall_seconds':round(time.monotonic()-started,3),'event_types':dict(collections.Counter(e['message'].get('type') for e in events)),'system_subtypes':dict(collections.Counter(e['message'].get('subtype') for e in events if e['message'].get('type')=='system')),'controls':controls,'result':{k:result.get(k) for k in ('subtype','is_error','stop_reason','num_turns','duration_ms','total_cost_usd','session_id')},'assistant_tool_names':[b.get('name') for e in events if e['message'].get('type')=='assistant' for b in e['message'].get('message',{}).get('content',[]) if b.get('type')=='tool_use']}
    (ROOT/('claude-'+args.action+'-summary.json')).write_text(json.dumps(summary,indent=2))
    if args.action=='normal':(ROOT/'claude-session-id').write_text(session)
    print(json.dumps(summary))

if __name__=='__main__':main()
