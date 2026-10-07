"""Controlled fixture only: ask for one continuation, separate from the observer."""
import json,pathlib,sys
r=json.load(sys.stdin)
if not r.get('stop_hook_active'):
    print(json.dumps({'decision':'block','reason':'This is the controlled continuation probe. Reply with only CREW_CONTINUED, then finish.'}))
else:print('{}')
