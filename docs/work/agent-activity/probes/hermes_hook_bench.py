"""Native dispatcher replay timings; this script does not call a model."""
from pathlib import Path
import sys,time,json,math
ROOT=Path(__file__).resolve().parent;active=Path.home()/'.hermes/hermes-agent';current=ROOT/'hermes-current'
sys.path.insert(0,str(active));import hermes_bootstrap
stale=[name for name,module in list(sys.modules.items()) if name!='hermes_bootstrap' and str(getattr(module,'__file__','')).startswith(str(active))]
for name in stale:sys.modules.pop(name,None)
sys.path.insert(0,str(ROOT/'hermes-deps'));sys.path.insert(0,str(current))
from hermes_cli import plugins
assert str(plugins.__file__).startswith(str(current))
plugins.discover_plugins()
from hermes_cli.lifecycle import invoke_hook
log=ROOT/'hermes-current-home/observations.jsonl';before=len(log.read_text().splitlines());values=[]
for i in range(200):
    t=time.perf_counter_ns();invoke_hook('pre_llm_call',session_id='crew-dispatch-fixture',turn_id=str(i),platform='cli');values.append((time.perf_counter_ns()-t)/1e6)
after=len(log.read_text().splitlines());assert after-before==200
values.sort();r={'kind':'native-dispatch payload replay, no model','n':200,'events_written':after-before,'p50_ms':round(values[99],3),'p95_ms':round(values[189],3),'p99_ms':round(values[197],3),'max_ms':round(max(values),3),'source_verified':True}
(ROOT/'hermes-dispatch-benchmark-summary.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
