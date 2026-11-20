"""Controlled single-route probes; research code, not historical parity."""
import argparse,json,subprocess,tempfile
from pathlib import Path
from routera3d_price import PRICE_XOR
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');a=ap.parse_args()
seed=json.load(open(a.seed));ref=json.loads(Path('tests/fixtures/routera3d_price.json').read_text())[0]
# Explicit synthetic funding for both directions, independent of archived balances.
seed['getters']['0x0bd7d308f8e1639fab988df18a8011f41eacad73']['0x70a08231000000000000000000000000000000000000a3d2e62895f55d5a4304d2f3c998']='0x'+(10**18).to_bytes(32,'big').hex()
seed.setdefault('execute_calls',[]).extend([
 '0xfae65eaa11943f45e83d5b45dc7a7c801c51bfb0:0x3850c7bd',
 '0xfae65eaa11943f45e83d5b45dc7a7c801c51bfb0:0xddca3f43',
 '0x8366a39cc670b4001a1121b8f6a443a643e40951:0x1e2eaeafbeb46db5363df9ad4aa124f91c0559bef5cc5ac34326fb367975a7844aa8ff30'])
seed['execute_calls'].extend('0x06a889870c8f83640d6816319f72e2aa579b6080:0x15452022bac3aa3b91584a53a579b3c999a56756e954e59247e497bad1d25a4334bde551'+n.to_bytes(32,'big').hex() for n in (0,1))
tx=next(r['tx'] for r in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')) if r['tx']['tx']==ref['tx'])
requests=[];specs=[]
for index in (0,1,2,5):
 for side in (1,2):
  raw=bytearray.fromhex(tx['data'][2:]);raw[0]=0xe1
  price=1900000000 if side==1 else 1750000000
  raw[1:6]=int(f'{price ^ PRICE_XOR:040b}'[::-1],2).to_bytes(5,'big')
  raw[6:9]=((65536<<7)|8).to_bytes(3,'big')
  data='0x'+(raw[:13]+bytes([index<<4|9,246,0,side])).hex()
  requests.append(dict(tx,data=data));specs.append((index,side))
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 Path(tmp.name).write_text(json.dumps(seed))
 rows=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in requests),text=True).splitlines()))
cases=[dict(index=i,side=s,transaction=t,result=r) for (i,s),t,r in zip(specs,requests,rows)]
Path('reports/amm/routera3d-identities-probe.json').write_text(json.dumps(dict(cases=cases,caveat='Synthetic single-route envelopes and mixed-era research seed; no historical fill or root success claim.'),indent=2)+'\n')
for c in cases:
 print(c['index'],c['side'],c['result']['error'],[(x['to'],x['data'][:10]) for x in c['result']['calls']])
