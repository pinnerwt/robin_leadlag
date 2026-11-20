"""Research settlement after running probe_router777_callback.py.
Uses its final synthetic seed; stub V3 proceeds and token transfers explicitly.
Not a recorder or historical transaction replay.
"""
import json,subprocess,sys
sys.path.insert(0,'scripts');from router777_plan import plan;from v3_calldata import word
index=int(sys.argv[1]) if len(sys.argv)>1 else -1
p=json.load(open('/tmp/router777-sequence-seed.json'));tx=next(row['tx'] for row in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')) if row['tx']['tx']==json.load(open('reports/amm/router777-sequence-prefix.json'))[index]['tx']);r=plan(tx['data']);tr=json.load(open('reports/amm/router777-sequence-prefix.json'))[index];call=tr['calls'][0];d=bytes.fromhex(call['data'][10:]);zero=bool(word(d,1));amt=word(d,2);out=r['amount']+100
pair=(amt,-out) if zero else (-out,amt)
p['getters'].setdefault(call['to'],{})[call['data']]='0x'+b''.join((v%(1<<256)).to_bytes(32,'big') for v in pair).hex()
k='0x70a08231'+int('7777857616fb37f0cfa262e9bb945e828312df17',16).to_bytes(32,'big').hex();before=p['getters'][r['token_in']][k];base=int(before[0] if isinstance(before,list) else before,16);
received=p['getters'][r['token_out']][k];old_out=int(received[0] if isinstance(received,list) else received,16);p['getters'][r['token_out']][k]=['0x'+v.to_bytes(32,'big').hex() for v in [old_out,old_out+amt,old_out+amt,old_out+amt]];
p['getters'][r['token_in']][k]=['0x'+v.to_bytes(32,'big').hex() for v in [*([base]*3),*([base+out]*2),base+out-r['amount']]]
for i in range(6):
 open('/tmp/router777-tail-seed.json','w').write(json.dumps(p));x=json.loads(subprocess.check_output(['target/release/examples/router_prefix','/tmp/router777-tail-seed.json'],input=json.dumps(tx),text=True));print(i,x['error'],x['execution_success'],[(c['to'],c['data'][:10]) for c in x['calls']],x['output'][:80] if x['output'] else None)
 if not x['calls']:break
 for c in x['calls']:
  if c['to'] not in (r['token_in'],r['token_out']) or c['data'][:10] not in ['0x095ea7b3','0xa9059cbb','0x23b872dd']:raise ValueError(c)
  p['getters'].setdefault(c['to'],{})[c['data']]='0x'+(1).to_bytes(32,'big').hex()
open(f'reports/amm/router777-tail-{index}.json','w').write(json.dumps(x,indent=2))

from hub_state import HUB,primary_keys,withdraw,deposit
assert x['execution_success'] and x['error'] is None
pushes=[c for c in x['execution_calls'] if c['to']==HUB and c['data'].startswith('0x47d72768')]
assert len(pushes)==1 and word(bytes.fromhex(pushes[0]['data'][10:]),4)==r['amount']
keys=primary_keys(r['primary'])['token_slots']
storage={int(k,16):int(v,16) for k,v in p['accounts'][HUB]['storage'].items()}
writes=[w for w in x['storage_writes'] if w['address']==HUB]
assert len(writes)==3
old=storage[int(keys[r['token_in']],16)]
assert int(writes[-1]['value'],16)==deposit(withdraw(old,r['amount']*125000//10**9),r['amount'])
print('Successful synthetic root; full original input deposited; allocation net of protocol fee matches')

refunds=[c for c in x['execution_calls'] if c['to']==r['token_in'] and c['data'].startswith('0xa9059cbb')]
assert len(refunds)==1 and word(bytes.fromhex(refunds[0]['data'][10:]),1)==100
print('Refund is exactly synthetic V3 profit after Aqua repayment')
