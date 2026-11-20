"""Bounded initialization probe, never imported/called by runtime follower.

Executes synthetic local probes to discover exact missing keys, reads those keys
at the existing anchor, verifies its hash and saves evidence. Unknown accounts or
intercepted calls stop discovery. This is not continuous execution coverage.
"""
import argparse,json,re,subprocess
from pathlib import Path
from bootstrap_state import Bootstrap
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('checkpoint');ap.add_argument('observations');ap.add_argument('--steps',type=int,default=8);ap.add_argument('--probe-script',default='scripts/probe_index4_fresh.py');ap.add_argument('--report',default='reports/amm/routera3d-index4-fresh-local-probe.json');a=ap.parse_args()
if not 1<=a.steps<=16:raise ValueError('bounded initialization steps required')
p=Path(a.checkpoint);s=json.loads(p.read_text());block=s['anchor']['number'];b=Bootstrap('https://rpc.mainnet.chain.robinhood.com',interval=.1);evidence=[]
for step in range(a.steps):
 subprocess.run(['python3',a.probe_script,str(p),a.observations],check=True,capture_output=True,text=True)
 report=json.load(open(a.report))
 keys=set()
 for r in report['results']:
  m=re.fullmatch(r'database error: unknown slot (0x[0-9a-fA-F]{40}) (0x[0-9a-fA-F]+)',r.get('error') or '')
  if m:keys.add((m[1].lower(),hex(int(m[2],16))))
 if not keys:break
 updates=[]
 for address,key in sorted(keys):
  if address not in s['accounts']:raise ValueError('unknown account')
  if int(key,16) in {int(k,16) for k in s['accounts'][address].get('storage',{})}:raise ValueError('known slot reported missing')
  updates.append((address,key,b.rpc('eth_getStorageAt',[address,key,block])))
 if b.rpc('eth_getBlockByNumber',[block,False])['hash']!=s['anchor']['hash']:raise ValueError('anchor changed')
 for address,key,value in updates:s['accounts'][address].setdefault('storage',{})[key]=value
 evidence.append(dict(step=step,updates=updates));p.write_text(json.dumps(s,indent=2)+'\n')
 print('initialized step',step,'slots',len(updates),flush=True)
s['rpc_calls']+=b.calls;s.setdefault('initialization_slot_probes',[]).append(dict(anchor_hash=s['anchor']['hash'],steps=evidence,rpc_calls=b.calls));p.write_text(json.dumps(s,indent=2)+'\n')
subprocess.run(['python3',a.probe_script,str(p),a.observations],check=True)
