"""Synthetic isolated reverse V4 settlement: zero minimum output, flag=true,
explicit token-transfer success and manager balance before/after funding.
No RPC or transaction submission; not historical execution parity.
"""
import json,sys,subprocess
sys.path.insert(0,'scripts')
from bootstrap_state import word,mapping
from v3_calldata import word as getword,array
M='0x8366a39cc670b4001a1121b8f6a443a643e40951';H='0x4adbfa936020fb330587ee1862478316da5ba0cc';R='0x204faca1764b154221e35c0d20abb3c525710498'
s=json.load(open('captures/startup-v9-dependencies.json'));c=next(c for c in json.load(open('tests/fixtures/universal_v4_intent.json')) if not c['expected']['zero']);t=next(r['tx'] for r in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')) if r['tx']['tx']==c['tx']);op=c['expected'];s['accounts'][H]['storage'][mapping(int(t['from'],16),0)]='0x1'
def dyn(b):return word(len(b))+b+bytes((-len(b))%32)
payload=bytearray.fromhex(c['payload']);body=array(payload,getword(payload,1))[0];start=payload.find(body);payload[start+8*32:start+9*32]=word(0);payload=bytes(payload);raw=word(96)+word(160)+word(t['timestamp']+3600)+dyn(b'\x10')+word(1)+word(32)+dyn(payload);tx=dict(t,data='0x3593564c'+raw.hex(),value='0x0')
p=dict(accounts=s['accounts'],trace_execution=True,execute_targets=[R,M,H],getters={})
bal='0x70a08231'+word(int(M,16)).hex();p['getters'][op['currency1']]={bal:['0x'+word(0).hex(),'0x'+word(-op['amount']).hex()]}
for i in range(5):
 open('/tmp/v4-settle-seed.json','w').write(json.dumps(p));r=json.loads(subprocess.check_output(['target/release/examples/router_prefix','/tmp/v4-settle-seed.json'],input=json.dumps(tx),text=True));print(i,r['error'],r['execution_success'],r['calls'])
 if not r['calls']:break
 call=r['calls'][0]
 if call['to'] not in (op['currency0'],op['currency1']) or call['data'][2:10] not in ('a9059cbb','23b872dd'):break
 p['getters'].setdefault(call['to'],{})[call['data']]='0x'+word(1).hex()
assert r['execution_success'] and r['error'] is None
transfers=[x for x in r['execution_calls'] if x['data'].startswith('0xa9059cbb')]
assert len(transfers)==2
funding,delivery=transfers
fb=bytes.fromhex(funding['data'][10:]);db=bytes.fromhex(delivery['data'][10:])
assert funding['to']==op['currency1'] and getword(fb,0)==int(M,16) and getword(fb,1)==-op['amount']
assert delivery['to']==op['currency0'] and getword(db,0)==int(t['from'],16)
open('reports/amm/v4-reverse-settlement-validation.json','w').write(json.dumps(dict(
 input_amount=str(-op['amount']),output_amount=str(getword(db,1)),output_recipient=t['from'],
 result=r,caveat='Synthetic isolated successful settlement; minimum output zeroed; no historical parity'),indent=2)+'\n')
