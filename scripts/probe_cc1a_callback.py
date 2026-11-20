"""Read-only local bytecode experiment with an explicitly synthetic V3 callback.

Requires: cargo build --release --example router_prefix
No chain calls, transaction submission, or real pool execution occurs.
The mock ignores callback success and returns no swap deltas. Only downstream
argument dependence is tested, never successful settlement or state parity.
"""
import json, subprocess, tempfile

root='0xcc1ae96cd8479f896a8dba85eab09a694b929b6c';pool='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca'
base=next(json.loads(line)['tx'] for line in open('reports/amm/optimistic-target-corpus.jsonl') if json.loads(line)['tx']['tx']=='0x741ba04c991324462bbba86bf50b4f5c9a5319ff6a008e5a34fd55d9ba201dd7');capture=json.load(open('reports/amm/routercc1-calldata-reads.jsonl'));call=capture['calls'][0];raw=bytes.fromhex(call['data'][10:]);off=int.from_bytes(raw[128:160],'big');size=int.from_bytes(raw[off:off+32],'big');cb=raw[off+32:off+32+size]
def word(n):return (n%(1<<256)).to_bytes(32,'big')
def push(n):
 b=n.to_bytes(max(1,(n.bit_length()+7)//8),'big');return bytes([0x5f+len(b)])+b
cases=[]
for output in [1,10**18,12345678901234567890]:
 callback=bytes.fromhex('fa461e33')+word(-output)+word(778206544)+word(96)+word(len(cb))+cb+bytes((-len(cb))%32)
 # Fixed-width PUSH2 permits code-offset replacement without changing layout.
 code=push(len(callback))+b'\x61\x00\x00'+push(0)+b'\x39'
 code+=push(0)+push(0)+push(len(callback))+push(0)+push(0)+bytes.fromhex('73'+root[2:])+b'\x5a\xf1\x50\x00'
 start=len(code);code=code[:len(push(len(callback)))+1]+start.to_bytes(2,'big')+code[len(push(len(callback)))+3:]+callback
 p=json.load(open('reports/amm/routercc1-synthetic-seed.json'));p['accounts'][pool]={'code':'0x'+code.hex(),'balance':'0x0','storage':{}};p['execute_targets']=[root,pool]
 
 for token in ['0x5fc5360d0400a0fd4f2af552add042d716f1d168','0x0bd7d308f8e1639fab988df18a8011f41eacad73','0xaf2640f82a499abfcf143fec309f1d8953b4a3ab']:p['accounts'].setdefault(token,{'code':'0x','balance':'0x0','storage':{}})
 temp=tempfile.NamedTemporaryFile(suffix='.json');path=temp.name; probes=[]
 for attempt in range(5):
  json.dump(p,open(path,'w'));r=json.loads(subprocess.check_output(['target/release/examples/router_prefix',path],input=json.dumps(base),text=True));probes.append(r)
  added=False
  for c in r['calls']:
   if c['data'][:10] in ('0x70a08231','0xa9059cbb','0x23b872dd'):
    p.setdefault('getters',{}).setdefault(c['to'],{})[c['data']]='0x'+word(10**30 if c['data'].startswith('0x70a08231') else 1).hex();added=True
  if not added:break
 temp.close()
 cases.append(dict(synthetic_output=output,callback='0x'+callback.hex(),probes=probes,result=r))
 print(output,r['error'],[(c['to'],c['data'][:10]) for c in r['calls']])
json.dump(dict(purpose='Synthetic pool callback to expose downstream router argument dependencies; no swap math or success claim',cases=cases),open('reports/amm/routercc1-callback-probe.json','w'),indent=2)

# Independently assert the causal relationship across the three interventions.
for case in cases:
 calls=case['result']['calls']
 assert case['result']['error'] is None and len(calls)==1
 call=calls[0]
 assert call['to']=='0xaf2640f82a499abfcf143fec309f1d8953b4a3ab'
 assert call['data'].startswith('0xe24f0884')
 data=bytes.fromhex(call['data'][10:])
 assert int.from_bytes(data[64:96], 'big')==case['synthetic_output']
print('3/3 downstream Metric amounts follow synthetic V3 output')
