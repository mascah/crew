"""Disposable Hermes CLI run with scratch home, profile, and observer plugin."""
import argparse, collections, json, os, pathlib, subprocess, sys, time, pty, select, fcntl, termios, struct
ROOT=pathlib.Path(__file__).resolve().parent

PLUGIN = '''import json, pathlib, time
from hermes_cli.plugins import VALID_HOOKS
LOG=pathlib.Path(__file__).resolve().parents[2]/"observations.jsonl"
FIELDS=("session_id","turn_id","task_id","completed","failed","interrupted","turn_exit_reason","parent_session_id","parent_turn_id","parent_subagent_id","child_session_id","child_subagent_id","child_status","child_role","kind","request_id","session_key","platform","outcome","tool_name","tool_call_id","status","reason","old_session_id","new_session_id")
def register(ctx):
    for event in ("on_session_start","pre_llm_call","post_llm_call","pre_tool_call","post_tool_call","on_session_end","on_session_finalize","on_session_reset","pre_approval_request","post_approval_response","on_human_input_request","on_human_input_resolved","subagent_start","subagent_stop","agent_loop_stopped"):
        if event not in VALID_HOOKS: continue
        def observe(_event=event,**kwargs):
            start=time.perf_counter_ns()
            entry={"received_ns":time.time_ns(),"event":_event,"fields":{k:kwargs[k] for k in FIELDS if k in kwargs}}
            response=kwargs.get("assistant_response")
            if response is not None:entry["response_marker"]="CREW_" in str(response)
            with LOG.open("a") as f:f.write(json.dumps(entry,default=str)+"\\n")
            return None
        ctx.register_hook(event,observe)
'''

def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['normal','resume','tool','subagents','question']);ap.add_argument('--revision',choices=['installed','current'],default='installed');ap.add_argument('--tty',action='store_true');args=ap.parse_args()
    active=pathlib.Path.home()/'.hermes'
    source=active/'hermes-agent' if args.revision=='installed' else ROOT/'hermes-current'
    home=ROOT/('hermes-'+args.revision+'-home')
    home.mkdir(exist_ok=True);os.chmod(home,0o700)
    # Use this host's existing credentials without printing or transferring them.
    # Copies isolate any authentication refresh from the active Hermes profile.
    import shutil
    for name in ['auth.json','.env']:
        src=active/name;dst=home/name
        if src.exists() and not dst.exists():shutil.copyfile(src,dst);os.chmod(dst,0o600)
    plugin=home/'plugins/crew_probe';plugin.mkdir(parents=True,exist_ok=True)
    (plugin/'plugin.yaml').write_text('name: crew_probe\nversion: 0.0.1\ndescription: Disposable local observer\nprovides_hooks: true\n')
    (plugin/'__init__.py').write_text(PLUGIN)
    (home/'config.yaml').write_text('model:\n  default: gpt-6.1-sol\n  provider: openai-codex\nagent:\n  max_turns: 8\n  reasoning_effort: low\n  run_budget_seconds: 90\nplugins:\n  enabled: [crew_probe]\nmcp_servers: {}\napprovals:\n  mode: manual\n')
    interpreter=active/'tools/python-3.14.7+20260901-darwin-arm64/bin/python3'
    if not interpreter.exists():raise RuntimeError('installed Hermes interpreter not found')
    prompts={
        'normal':'This is a bounded Crew validation. Do not inspect any files or use tools. Reply with only CREW_HERMES_DONE.',
        'resume':'Do not inspect files or use tools. Reply with only CREW_HERMES_RESUMED.',
        'tool':'This is a bounded Crew validation. Run only the harmless terminal command /bin/sleep 2, then reply with CREW_HERMES_TOOL_DONE. Do not inspect any files or use any other tool.',
        'subagents':'This is a bounded Crew validation. Delegate one task to one helper: reply with only CREW_HERMES_CHILD_DONE without using tools or inspecting files. Wait for the helper, then reply with CREW_HERMES_PARENT_DONE. No other actions.',
        'question':'This is a bounded Crew validation. Use clarify to ask me to choose Red or Blue. Do not read any files or use other tools. After receiving the answer, reply with that color.'}
    argv=['hermes','chat','--ignore-rules','--reasoning','low','--max-turns','8','--run-budget','90','--format','stream-json','--in',str(ROOT),'-q',prompts[args.action]]
    if args.tty:
        argv.remove('--format');argv.remove('stream-json');argv.insert(2,'--cli')
    if args.action=='resume':argv+=['--resume',(ROOT/('hermes-'+args.revision+'-session-id')).read_text().strip()]
    env=os.environ.copy();env['HERMES_HOME']=str(home);env['HERMES_PYTHON_SRC_ROOT']=str(source)
    # The installed managed launcher's dependency environment is resolved by
    # its bootstrap. Reuse those packages, then put the chosen source first.
    code='import sys; sys.path.insert(0,'+repr(str(active/'hermes-agent'))+'); import hermes_bootstrap; '
    if args.revision=='current':
        code+='old_root='+repr(str(active/'hermes-agent'))+'; stale=[name for name,module in list(sys.modules.items()) if name != "hermes_bootstrap" and str(getattr(module,"__file__","")).startswith(old_root)]; [sys.modules.pop(name,None) for name in stale]; '
    code+='sys.path.insert(0,'+repr(str(ROOT/'hermes-deps'))+'); sys.path.insert(0,'+repr(str(source))+'); from hermes_cli.main import main; import hermes_cli.plugins as plugins; '
    code+='import json,pathlib; provenance={"main":sys.modules["hermes_cli.main"].__file__,"plugins":plugins.__file__,"generic_human_input":"on_human_input_request" in plugins.VALID_HOOKS}; pathlib.Path('+repr(str(ROOT/('hermes-'+args.revision+'-provenance.json')))+').write_text(json.dumps(provenance)); '
    if args.revision=='current':code+='assert provenance["main"].startswith('+repr(str(source))+') and provenance["plugins"].startswith('+repr(str(source))+') and provenance["generic_human_input"], "wrong source revision loaded"; '
    code+='sys.argv='+repr(argv)+'; sys.exit(main())'
    start=time.monotonic();stderr=(ROOT/('hermes-'+args.revision+'-'+args.action+'.stderr')).open('w')
    if args.tty:
        master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0));env['TERM']='xterm-256color'
        proc=subprocess.Popen([str(interpreter),'-I','-c',code],env=env,cwd=ROOT,stdin=slave,stdout=slave,stderr=stderr)
        os.close(slave);output=bytearray();answered=False;exited=False;began_ns=time.time_ns();deadline=time.monotonic()+60;answer_attempts=0;last_answer=0
        log=home/'observations.jsonl'
        try:
            while time.monotonic()<deadline and proc.poll() is None:
                ready,_,_=select.select([master],[],[],.1)
                if ready:
                    try:
                        chunk=os.read(master,65536);output.extend(chunk)
                        if b'\x1b[6n' in chunk:os.write(master,b'\x1b[1;1R')
                    except OSError:break
                recent=[]
                if log.exists():
                    for line in log.read_text().splitlines():
                        try:r=json.loads(line)
                        except ValueError:continue
                        if r['received_ns']>=began_ns:recent.append(r)
                if not answered and any(r['event']=='on_human_input_request' and r['fields'].get('kind')=='clarify' for r in recent):
                    time.sleep(2);os.write(master,b'\x1b[B\r');answered=True;answer_attempts=1;last_answer=time.monotonic()
                if answered and answer_attempts<3 and time.monotonic()-last_answer>2 and not any(r['event']=='on_human_input_resolved' for r in recent):
                    os.write(master,b'2\r' if answer_attempts==1 else b'Blue\r');answer_attempts+=1;last_answer=time.monotonic()
                if not exited and any(r['event']=='on_session_end' for r in recent):
                    time.sleep(.3);os.write(master,b'/exit\n');exited=True
            if proc.poll() is None:proc.terminate()
            proc.wait(timeout=8)
        finally:os.close(master)
        p=type('Result',(),{'stdout':output.decode(errors='replace'),'returncode':proc.returncode})()
    else:p=subprocess.run([str(interpreter),'-I','-c',code],env=env,cwd=ROOT,stdout=subprocess.PIPE,stderr=stderr,text=True,timeout=120)
    stderr.close();raw=ROOT/('hermes-'+args.revision+'-'+args.action+('-tty' if args.tty else '')+'.wire.jsonl');raw.write_text(p.stdout)
    native=[]
    for ln in p.stdout.splitlines():
        try:native.append(json.loads(ln))
        except ValueError:continue
    observations=[];log=home/'observations.jsonl'
    if log.exists():observations=[json.loads(x) for x in log.read_text().splitlines()]
    new=[r for r in observations if r['received_ns']>=int((time.time()-(time.monotonic()-start))*1e9)]
    sessions=[r['fields']['session_id'] for r in new if r['fields'].get('session_id')]
    if args.action=='normal' and sessions:(ROOT/('hermes-'+args.revision+'-session-id')).write_text(sessions[0])
    summary={'revision':args.revision,'action':args.action,'tty':args.tty,'process_exit':p.returncode,'wall_seconds':round(time.monotonic()-start,3),'native_event_types':dict(collections.Counter(r.get('type',r.get('event','unknown')) for r in native)),'observed_events':dict(collections.Counter(r['event'] for r in new)),'observations':new}
    (ROOT/('hermes-'+args.revision+'-'+args.action+('-tty' if args.tty else '')+'-summary.json')).write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
    if p.returncode:print('probe_stderr_tail', (ROOT/('hermes-'+args.revision+'-'+args.action+'.stderr')).read_text()[-1200:])

if __name__=='__main__':main()
