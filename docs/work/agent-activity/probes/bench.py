"""Disposable emitter/collector and Git identity experiments; no model calls."""
import collections, concurrent.futures, json, math, os, pathlib, resource, statistics, subprocess, tempfile, threading, time
ROOT=pathlib.Path(__file__).resolve().parent

def stats(values):
    s=sorted(values)
    return {'n':len(s),'p50_ms':round(s[math.ceil(.50*len(s))-1],3),'p95_ms':round(s[math.ceil(.95*len(s))-1],3),'p99_ms':round(s[math.ceil(.99*len(s))-1],3),'max_ms':round(s[-1],3),'total_ms':round(sum(s),3)}

def emitter_bench():
    payload=json.dumps({'hook_event_name':'PostToolUse','session_id':'fixture','turn_id':'turn','tool_use_id':'tool','cwd':str(ROOT)}).encode()
    rows={}
    for name,command in [('process_baseline',['/usr/bin/true']),('compiled_emitter',[str(ROOT/'emit'),str(ROOT/'bench-events.jsonl')])]:
        samples=[]
        for _ in range(200):
            start=time.perf_counter_ns();subprocess.run(command,input=payload,stdout=subprocess.DEVNULL,check=True);samples.append((time.perf_counter_ns()-start)/1e6)
        rows[name]=stats(samples)
    return rows

class Collector:
    """Incrementally consume the scratch journal, retaining metadata only."""
    def __init__(self,path):self.path=path;self.offset=0;self.tail=b'';self.count=0;self.states={};self.errors=0
    def poll(self):
        if not self.path.exists():return
        with self.path.open('rb') as f:f.seek(self.offset);data=f.read();self.offset=f.tell()
        if not data:return
        lines=(self.tail+data).split(b'\n');self.tail=lines.pop()
        for line in lines:
            try:
                r=json.loads(line);p=r['payload'];key=p.get('session_id','unknown');self.states[key]=p.get('hook_event_name');self.count+=1
            except (ValueError,KeyError):self.errors+=1

def collector_bench():
    path=ROOT/'collector-events.jsonl';path.write_bytes(b'');c=Collector(path);rows={}
    wall=time.monotonic();cpu=time.process_time()
    for _ in range(200):c.poll();time.sleep(.05)
    elapsed=time.monotonic()-wall;used=time.process_time()-cpu
    rows['idle']={'seconds':round(elapsed,3),'cpu_seconds':round(used,6),'percent_one_core':round(used/elapsed*100,3)}
    stop=threading.Event()
    def poller():
        while not stop.is_set():c.poll();stop.wait(.02)
        c.poll()
    t=threading.Thread(target=poller);t.start();wall=time.monotonic();cpu=time.process_time();children_before=resource.getrusage(resource.RUSAGE_CHILDREN)
    def emit(i):
        payload=json.dumps({'hook_event_name':'PostToolUse','session_id':'fixture-'+str(i%8),'turn_id':'turn','tool_use_id':str(i)}).encode()
        subprocess.run([str(ROOT/'emit'),str(path)],input=payload,stdout=subprocess.DEVNULL,check=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(emit,range(800)))
    stop.set();t.join();elapsed=time.monotonic()-wall;used=time.process_time()-cpu;child=resource.getrusage(resource.RUSAGE_CHILDREN)
    rows['synthetic_burst']={'seconds':round(elapsed,3),'events_sent':800,'events_read':c.count,'parse_errors':c.errors,'remaining_partial_bytes':len(c.tail),'parent_cpu_seconds_including_driver':round(used,6),'child_cpu_seconds':round((child.ru_utime+child.ru_stime)-(children_before.ru_utime+children_before.ru_stime),6),'peak_rss_bytes_macos':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'bytes_read':c.offset}
    return rows

def identity_bench():
    base=pathlib.Path(tempfile.mkdtemp(prefix='git-identity-',dir=ROOT));repo=base/'a/crew';repo.mkdir(parents=True)
    def git(path,*args):return subprocess.check_output(['git','-C',str(path),*args],stderr=subprocess.DEVNULL,text=True).strip()
    git(repo,'init','-q');git(repo,'-c','user.name=Crew probe','-c','user.email=probe@example.invalid','commit','--allow-empty','-qm','Disposable fixture')
    git(repo,'remote','add','origin','git@github.com:mascah/crew.git');wt=base/'crew-worktree';git(repo,'worktree','add','-q','--detach',str(wt))
    clone=base/'b/crew';clone.parent.mkdir();subprocess.run(['git','clone','-q',str(repo),str(clone)],check=True,stderr=subprocess.DEVNULL);git(clone,'remote','set-url','origin','https://github.com/mascah/crew.git')
    other=base/'c/crew';other.mkdir(parents=True);git(other,'init','-q');git(other,'remote','add','origin','git@github.com:unrelated/crew.git')
    rows={str(p.relative_to(base)):{'common_dir':git(p,'rev-parse','--path-format=absolute','--git-common-dir'),'origin':git(p,'remote','get-url','origin')} for p in [repo,wt,clone,other]}
    assert rows['a/crew']['common_dir']==rows['crew-worktree']['common_dir']
    assert rows['a/crew']['common_dir']!=rows['b/crew']['common_dir']
    assert rows['a/crew']['origin']==rows['crew-worktree']['origin']
    def github_identity(url):return url.replace('git@github.com:','github.com/').replace('https://github.com/','github.com/').removesuffix('.git')
    assert github_identity(rows['a/crew']['origin'])==github_identity(rows['b/crew']['origin'])
    assert github_identity(rows['a/crew']['origin'])!=github_identity(rows['c/crew']['origin'])
    return {'local_worktree_common_dir':True,'clone_common_dir_distinct':True,'ssh_https_same_origin_identity':True,'unrelated_same_basename_distinct':True}

def main():
    result={'emitter_only':emitter_bench(),'collector_prototype':collector_bench(),'git_fixtures':identity_bench()}
    (ROOT/'benchmark-summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
