"""Mode40 index4 router bounds at a coherent fresh state; swap intercepted."""
import argparse,json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import word
from routera3d_price import PRICE_XOR,reverse_v3_limit,forward_v3_limit
PARENT='0x000000000000a3d2e62895f55d5a4304d2f3c998';CHILD='0xe3c90972c6462bb4a4c75cf49dcf4189c5b42880';POOL='0x7615926023bb149f36095645c2a81dc367d39750'
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--limited-inventory',action='store_true');options=ap.parse_args()
weth=10**15 if options.limited_inventory else 10**18;usdg=8000000 if options.limited_inventory else 10**12
s=json.load(open('reports/amm/routera3d-index4-blocks-dependencies.json'));h=s['anchor']
s.update(trace_execution=True,trace_hashes=True,execute_targets=[PARENT,CHILD,'0xc0ed888afe87ed1acf01d9f19bb850159e3ce434'],delegate_targets=['0x1642634c8cb1c9f1b84c9a1a08534f8c3f4e89f8'],execute_calls=[POOL+':0x3850c7bd'])
s['getters']={t:{'0x70a08231'+word(int(PARENT,16)).hex():'0x'+word(n).hex()} for t,n in [('0x0bd7d308f8e1639fab988df18a8011f41eacad73',weth),('0x5fc5360d0400a0fd4f2af552add042d716f1d168',usdg)]}
ref=json.load(open('tests/fixtures/routera3d_price.json'))[0];original=next(r['tx'] for r in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')) if r['tx']['tx']==ref['tx']);specs=[];txs=[]
for side,price in [(1,1900000000),(2,1750000000)]:
 for hint in (1,187,500):
  packed=int(f'{price ^ PRICE_XOR:040b}'[::-1],2)
  raw=b'\x41'+packed.to_bytes(5,'big')+((65536<<7)|8).to_bytes(3,'big')+(int(h['number'],16)+1).to_bytes(4,'big')+bytes([0x49,246,0,side])+hint.to_bytes(2,'big')
  txs.append(dict(original,data='0x'+raw.hex(),sequence=int(h['number'],16),timestamp=int(h['timestamp'],16)));specs.append((side,price,hint))
with tempfile.NamedTemporaryFile(suffix='.json') as f:
 Path(f.name).write_text(json.dumps(s));rows=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',f.name],input=''.join(json.dumps(t)+'\n' for t in txs),text=True).splitlines()))
cases=[]
for (side,price,hint),tx,r in zip(specs,txs,rows):
 swaps=[x for x in r['calls'] if x['to']==POOL and x['data'].startswith('0x128acb08')]
 matched=False
 if len(swaps)==1:
  raw=bytes.fromhex(swaps[0]['data'][10:]);args=[int.from_bytes(raw[i:i+32],'big') for i in range(0,160,32)]
  expected_amount=16777216 if side==1 else 16777216*10**18//(price*99990//100000)
  expected_amount=min(expected_amount,usdg if side==1 else weth)
  expected_limit=(reverse_v3_limit if side==1 else forward_v3_limit)(price,10,hint,10)
  assert args[1:4]==[int(side==2),expected_amount,expected_limit],(args,expected_amount,expected_limit)
  matched=True
 cases.append(dict(side=side,price=price,hint=hint,transaction=tx,matched=matched,result=r))
Path('reports/amm/routera3d-index4-bounds'+('-limited' if options.limited_inventory else '')+'-probe.json').write_text(json.dumps(dict(anchor=h,weth_inventory=weth,usdg_inventory=usdg,cases=cases,caveat='Controlled single-route envelopes, synthetic parent balances, pool swap intercepted. Full router economics not proven.'),indent=2)+'\n')
for c in cases:print(c['side'],c['hint'],c['matched'],c['result']['error'],[(x['to'],x['data'][:10]) for x in c['result']['calls']])
