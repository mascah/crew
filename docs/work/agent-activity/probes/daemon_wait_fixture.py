"""Controlled daemon request; a separate connection observes it using reads only."""
import json,pathlib,time
from daemon_observer import WS,ROOT
owner=WS();observer=WS()
try:
    start=owner.call('thread/start',{'cwd':str(ROOT),'approvalPolicy':'on-request','approvalsReviewer':'user','sandbox':'read-only','developerInstructions':'Bounded Crew fixture. Run only the requested harmless sleep command. Do not inspect files, credentials, configuration, or use any other tools.'})
    tid=start['thread']['id']
    owner.call('turn/start',{'threadId':tid,'input':[{'type':'text','text':'Run /bin/sleep 2 with exec_command shell_permissions=require_escalated solely to exercise the approval fixture. Ask for approval. Then reply with CREW_DAEMON_DONE.'}],'effort':'low'})
    waiting=None;end=None;deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        m=owner.receive();method=m.get('method','')
        if method=='item/commandExecution/requestApproval' and 'id' in m:
            waiting=observer.call('thread/read',{'threadId':tid,'includeTurns':False})['thread']['status']
            assert waiting['type']=='active' and 'waitingOnApproval' in waiting['activeFlags']
            time.sleep(1);owner.send({'id':m['id'],'result':{'decision':'accept'}})
        if method=='turn/completed' and m.get('params',{}).get('threadId')==tid:end=m;break
    assert end and end['params']['turn']['status']=='completed'
    idle=observer.call('thread/read',{'threadId':tid,'includeTurns':False})['thread']['status'];assert idle['type']=='idle'
    result={'separate_passive_connection':True,'wait_status':waiting,'after_completion':idle,'request_outcome':end['params']['turn']['status']}
    assert waiting is not None
    (ROOT/'daemon-wait-summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
finally:owner.close();observer.close()
