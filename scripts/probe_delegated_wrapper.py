"""Actual saved wrapper/inner prefix with explicit condition metadata getters."""
import json
from pathlib import Path
from delegated_wrapper import inspect
from probe_delegated_kind8 import run
from probe_delegated_callback import callback_code

def main():
 tx=next(t for t in map(json.loads,Path('reports/amm/delegated-router-txs.jsonl').read_text().splitlines()) if t['data'].startswith('0x31abd933'))
 plan=inspect(tx['data']);seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());root=tx['to'].lower()
 seed['trace_execution']=True;seed['delegate_targets']=[root];seed['getters']={}
 for r in plan['plan']['condition']['records']:seed['getters'].setdefault(r['target'],{})[r['calldata']]='0x'+r['value'].to_bytes(32,'big').hex()
 for action in plan['plan']['actions']:
  if action['kind']==1:
   for selector,key in [('0x0dfe1681','currency0'),('0xd21220a7','currency1')]:seed['getters'].setdefault(action['target'],{})[selector]='0x'+int(action[key],16).to_bytes(32,'big').hex()
 result=run(seed,tx)
 stages=[]
 if len(result['calls'])==1 and result['calls'][0]['data'].startswith('0x48c89491'):
  unlock=result['calls'][0];manager=unlock['to'];cb=bytes.fromhex('91dd7346'+unlock['data'][10:])
  seed['accounts'][manager]=dict(code='0x'+callback_code(cb,root).hex(),balance='0x0',nonce='0x0',storage={})
  seed['execute_calls']=[manager+':'+unlock['data']];seed['execute_targets']=[root]
  balance='0x70a08231'+'00'*12+root[2:]
  for action in plan['plan']['actions']:
   for token in (action['token_in'],action['token_out']):seed['getters'].setdefault(token,{})[balance]='0x'+'00'*32
  for _ in range(3):
   current=run(seed,tx);stages.append(current)
   calls=current['calls']
   if len(calls)!=1 or calls[0]['to']!=manager or not calls[0]['data'].startswith('0x0b0d9c09'):break
   seed['getters'].setdefault(manager,{})[calls[0]['data']]='0x'
   token=plan['plan']['actions'][0]['token_in'];seed['getters'][token][balance]=['0x'+'00'*32,'0x'+plan['plan']['header'][3].to_bytes(32,'big').hex()]
  print('callback',current['error'],[(c['to'],c['data'][:10]) for c in current['calls']])
 Path('reports/amm/delegated-wrapper-prefix-probe.json').write_text(json.dumps(dict(callback_stages=stages,tx=tx,plan=plan,synthetic_getters=seed['getters'],result=result,caveat='Actual wrapper and delegated implementation, synthetic condition/metadata returns; synthetic callback/funding/full input credit in callback stages, prefix only.'),indent=2)+'\n')
 print(result['error'],[(c['to'],c['data'][:10],c['scheme']) for c in result['calls']])
if __name__=='__main__':main()
