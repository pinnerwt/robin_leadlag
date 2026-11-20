"""One-load finite execution witness replay; no runtime RPC or per-tx reseeding.
Initialization combines first-access prestate witnesses for this finite interval.
This proves no live future dependency coverage and is not a production bootstrap.
"""
import argparse,json,subprocess,tempfile,copy
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixtures',default='captures/signed-continuity-fixtures.json');p.add_argument('--seed-output',default='captures/finite-continuity-seed.json');p.add_argument('--output',default='reports/amm/finite-continuity.json');a=p.parse_args();rows=json.load(open(a.fixtures));accounts={};txs=[]
for f in rows:
 # An EOA transfer executes no opcode, so JS step() cannot capture fee prestate.
 # Reverse its independently known intrinsic-only 21000-gas credit, not a receipt-derived amount.
 if not f['fee_account_witness']['before']:
  assert f['tx']['data']=='0x' and not f['accounts'].get(f['tx']['to'].lower(),{}).get('code','0x').removeprefix('0x')
  from arbos_units import ARBOS,ROOT
  slots={hex(int(k,16)):int(v,16) for k,v in f['accounts'][ARBOS]['storage'].items()}
  base=int(f['header']['baseFeePerGas'],16);minimum=slots['0xe54de2a4cdacc0a0059d2b6e16348103df8c4aff409c31e40ec73d11926c8203'];infra=min(base,minimum)
  for offset,rate in [('03',base-infra),('06',infra)]:
   address='0x'+slots[ROOT+offset].to_bytes(32,'big')[-20:].hex();after=f['fee_account_witness']['after'][address]
   f['fee_account_witness']['before'][address]=dict(after,balance=hex(int(after['balance'],16)-21000*rate)[2:])
  f['fee_seed_note']='EOA transfer: reverse intrinsic 21000 gas system credits from first observed balances'
 pre=copy.deepcopy(f['accounts'])
 for addr,v in f['fee_account_witness']['before'].items():pre[addr]=dict(v,balance='0x'+v['balance'])
 for addr,v in pre.items():
  dst=accounts.setdefault(addr,{k:x for k,x in v.items() if k!='storage'});slots=dst.setdefault('storage',{})
  for key,value in v.get('storage',{}).items():slots.setdefault(key,value)
 t=dict(f['tx'],block_base_fee=f['header']['baseFeePerGas']);txs.append(t)
seed=dict(accounts=accounts,mode='finite_first_access_witness_not_live_bootstrap')
Path(a.seed_output).write_text(json.dumps(seed,indent=2)+'\n')
proc=subprocess.run(['target/release/examples/router_execute',a.seed_output,'--commit','--units-mode=signed'],input=''.join(json.dumps(t)+'\n' for t in txs),text=True,capture_output=True)
local=list(map(json.loads,proc.stdout.splitlines()));checks=[];expected=copy.deepcopy(accounts)
for f,r in zip(rows,local):
 # Expected state is advanced ONLY in this validator, never in the execution process.
 for addr,v in f['diff']['post'].items():
  dst=expected.setdefault(addr,{});dst.update({k:x for k,x in v.items() if k!='storage'});dst.setdefault('storage',{}).update(v.get('storage',{}))
 for addr,v in f['diff']['pre'].items():
  for slot in v.get('storage',{}):
   if slot not in f['diff']['post'].get(addr,{}).get('storage',{}):expected[addr]['storage'][slot]='0x0'
 for addr,v in f['fee_account_witness']['after'].items():expected[addr].update(dict(v,balance='0x'+v['balance']))
 mismatches=[]
 for addr,v in r['accounts'].items():
  e=expected.get(addr,{})
  for key in ('nonce','balance'):
   want=e.get(key,0 if key=='nonce' else '0x0');actual=v[key]
   if key=='balance':want=hex(int(want,16))
   if actual!=want:mismatches.append(dict(address=addr,field=key,expected=want,actual=actual))
 for addr,slots in r['changed_storage'].items():
  e={hex(int(k,16)):hex(int(v,16)) for k,v in expected.get(addr,{}).get('storage',{}).items()}
  for k,v in slots.items():
   if e.get(k)!=v:mismatches.append(dict(address=addr,slot=k,expected=e.get(k),actual=v))
 # Compare exact changed storage set, including absent writes, using chain diff.
 changed={}
 for addr,v in f['diff']['post'].items():
  if v.get('storage'):changed[addr]={hex(int(k,16)):hex(int(x,16)) for k,x in v['storage'].items()}
 for addr,v in f['diff']['pre'].items():
  for slot in v.get('storage',{}):
   if slot not in f['diff']['post'].get(addr,{}).get('storage',{}):changed.setdefault(addr,{})[hex(int(slot,16))]='0x0'
 norm=lambda logs:[dict(address=x['address'].lower(),topics=x['topics'],data=x['data']) for x in logs]
 check=dict(tx=r['tx'],error=r['error'],success=r['success']==(int(f['receipt']['status'],16)==1),gas=r['gas_used']==int(f['receipt']['gasUsed'],16),logs=norm(r['logs'])==norm(f['receipt']['logs']),storage=changed==r['changed_storage'],account_mismatches=mismatches)
 checks.append(check)
report=dict(continuous_checkpoint_loads=1,expected_transactions=len(rows),executed_transactions=len(local),exit_code=proc.returncode,stderr=proc.stderr,checks=checks,production_ready=False,limitations=['finite future dependency keys discovered from diagnostic witnesses','block start/end hooks not applied','base fee supplied from recorded pushed headers'])
report['matched']=proc.returncode==0 and len(local)==len(rows) and all(not c['error'] and c['success'] and c['gas'] and c['logs'] and c['storage'] and not c['account_mismatches'] for c in checks)
Path(a.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if not report['matched']:raise SystemExit(1)
