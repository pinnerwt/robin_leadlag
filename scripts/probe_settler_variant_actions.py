"""Isolate saved settler actions with explicit synthetic balances; no RPC/log inputs."""
import copy,json,re
from pathlib import Path
from probe_delegated_kind8 import run
from delegated_batch_route import HOLDER,ROUTER
WETH='0x0bd7d308f8e1639fab988df18a8011f41eacad73'
def word(n):return n.to_bytes(32,'big')
def action_tx(entry,action):
 p=entry['plan'];inner=bytes.fromhex(p['inner_calldata'][2:])
 a=bytes.fromhex(action['data'][2:])
 data=inner[:164]+word(1)+word(32)+word(len(a))+a+bytes((-len(a))%32)+bytes.fromhex(ROUTER[2:])
 return dict(entry['tx'],to=p['target'],data='0x'+data.hex(),**{'from':HOLDER})
def main():
 base=json.loads(Path('captures/startup-v9-dependencies.json').read_text());rows=[]
 for e in json.loads(Path('reports/amm/batch-unpinned-plans.json').read_text())['transactions']:
  for a in e['plan']['actions']:
   if a['selector'] not in ('0x38c9c147','0x8d68a156'):continue
   if a['selector']=='0x38c9c147' and a['data'][10:74].endswith('eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'):continue
   s=copy.deepcopy(base);s['trace_execution']=True;s['getters']={};s['execute_targets']=[]
   tx=action_tx(e,a);stages=[];mocks=[]
   for _ in range(6):
    r=run(s,tx);stages.append(r)
    unknown=re.search(r'unknown account (0x[0-9a-fA-F]{40})',r.get('error') or '')
    if unknown:
     address=unknown[1].lower();s['accounts'][address]=dict(code='0x',balance='0x0',nonce='0x0',storage={});mocks.append(dict(kind='empty_account',address=address));continue
    if len(r['calls'])!=1:break
    c=r['calls'][0];sel=c['data'][:10]
    if sel=='0x70a08231':value=e['plan']['amount'] if c['to']==e['plan']['token'] else 1000000000000000
    elif sel=='0xdd62ed3e':value=0
    elif sel=='0x095ea7b3':value=1
    else:break
    s['getters'].setdefault(c['to'],{})[c['data']]='0x'+word(value).hex();mocks.append(dict(kind='getter',call=c,value=value))
   rows.append(dict(tx_hash=e['tx']['tx'],action=a,synthetic_inputs=mocks,stages=stages,result=r,entry_code_verified=False))
   print(e['tx']['tx'][:12],a['selector'],r.get('error'),[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
 Path('reports/amm/settler-variant-actions.json').write_text(json.dumps(dict(cases=rows,caveat='Isolated action in saved actual settler; synthetic inventory/token metadata. No upstream output or original transaction success inferred.'),indent=2)+'\n')
if __name__=='__main__':main()
