"""Controlled Claude TUI continuation; inspect its saved terminal boundary."""
import fcntl,json,os,pathlib,pty,re,select,struct,subprocess,termios,time,uuid
ROOT=pathlib.Path(__file__).resolve().parent;sid=str(uuid.uuid4())
settings=ROOT/'claude-continuation-settings.json'
assert settings.exists()
cmd=[str(pathlib.Path.home()/'.local/bin/claude'),'--setting-sources','','--settings',str(settings),'--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--tools','','--effort','low','--session-id',sid,'--system-prompt','Run only the bounded response fixture. Do not inspect files or call tools.','Reply with only CREW_FIRST_STOP.']
master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',30,120,0,0));env=os.environ.copy();env['TERM']='xterm-256color'
stderr=(ROOT/'claude-tui.stderr').open('w');p=subprocess.Popen(cmd,cwd=ROOT,env=env,stdin=slave,stdout=slave,stderr=stderr);os.close(slave)
raw=bytearray();trusted=False;done=False;sent_exit=False;deadline=time.monotonic()+75
transcript=pathlib.Path.home()/'.claude/projects/-private-tmp-crew-validation-20261006'/(sid+'.jsonl')
try:
    while time.monotonic()<deadline and p.poll() is None:
        ready,_,_=select.select([master],[],[],.1)
        if ready:
            try:
                chunk=os.read(master,65536);raw.extend(chunk)
                if b'\x1b[6n' in chunk:os.write(master,b'\x1b[1;1R')
            except OSError:break
        text=re.sub(rb'\x1b\[[0-?]*[ -/]*[@-~]',b'',bytes(raw)).lower()
        if not trusted and (b'do you trust' in text or b'yes, i trust' in text):
            os.write(master,b'\r');trusted=True
        if transcript.exists():
            rows=[]
            for line in transcript.read_text().splitlines():
                try:rows.append(json.loads(line))
                except ValueError:continue
            if any(r.get('subtype')=='turn_duration' for r in rows) and not sent_exit:
                done=True;time.sleep(.4);os.write(master,b'/exit\r');sent_exit=True
            if sent_exit and p.poll() is None and time.monotonic()>deadline-2:break
    if p.poll() is None:p.terminate()
    try:p.wait(timeout=8)
    except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
finally:os.close(master);stderr.close()
(ROOT/'claude-tui.raw').write_bytes(raw)
rows=[json.loads(x) for x in transcript.read_text().splitlines()] if transcript.exists() else []
summaries=[{'hasOutput':r.get('hasOutput'),'preventedContinuation':r.get('preventedContinuation'),'stopReason':r.get('stopReason'),'errors_count':len(r.get('hookErrors',[]))} for r in rows if r.get('subtype')=='stop_hook_summary']
result={'session_id':sid,'process_exit':p.returncode,'trusted_scratch_only':trusted,'turn_duration_observed':done,'stop_summaries':summaries,'saved_record_subtypes':[r.get('subtype') for r in rows if r.get('type')=='system'],'assistant_markers':[('CREW_FIRST_STOP' in str(r.get('message')), 'CREW_CONTINUED' in str(r.get('message'))) for r in rows if r.get('type')=='assistant']}
(ROOT/'claude-tui-summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
