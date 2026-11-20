"""Offline index4 mode40 tail interventions; actual pool slot0 getter only."""
import argparse,json,subprocess,tempfile
from pathlib import Path
from routera3d_price import PRICE_XOR,reverse_v3_limit
from v3_calldata import word
P4='0x7615926023bb149f36095645c2a81dc367d39750'
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');ap.add_argument('--at-anchor',action='store_true');a=ap.parse_args()
seed=json.load(open(a.seed));ref=json.loads(Path('tests/fixtures/routera3d_price.json').read_text())[0]
tx=next(r['tx'] for r in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')) if r['tx']['tx']==ref['tx'])
if a.at_anchor:
    tx=dict(tx,sequence=int(seed['anchor']['number'],16),timestamp=int(seed['anchor']['timestamp'],16))
seed.setdefault('execute_calls',[]).append(P4+':0x252c09d7'+(239).to_bytes(32,'big').hex())
seed['execute_calls'].append(P4+':0x883bdbfd'+''.join(n.to_bytes(32,'big').hex() for n in (32,2,600,0)))
seed['execute_calls'].append('0xaa48aaef655fb7cd7acc04717f66022a4771a345:0xcd713a43'+P4[2:].zfill(64)+'e3c90972c6462bb4a4c75cf49dcf4189c5b42880'.zfill(64))
seed.setdefault('execute_calls',[]).extend([P4+':0x3850c7bd',P4+':0xddca3f43',P4+':0x099f15f7'])
seed.setdefault('delegate_targets',[]).extend(['0x1642634c8cb1c9f1b84c9a1a08534f8c3f4e89f8','0x1ad7a8703ebff81c0d753190938f228672ec7e42'])
seed['execute_targets'].extend(['0xc0ed888afe87ed1acf01d9f19bb850159e3ce434','0xc63d7338c178e805c544b8f897066bd3bbcbe136'])
requests=[]
for tail in (0,1,40,100,187,500):
    raw=bytearray.fromhex(tx['data'][2:]);raw[0]=0x41
    raw[1:6]=int(f'{1900000000 ^ PRICE_XOR:040b}'[::-1],2).to_bytes(5,'big');raw[6:9]=((65536<<7)|8).to_bytes(3,'big')
    raw[9:13]=(tx['sequence']+1).to_bytes(4,'big')
    requests.append((tail,dict(tx,data='0x'+(raw[:13]+bytes.fromhex('49f60001')+tail.to_bytes(2,'big')).hex())))
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
    Path(tmp.name).write_text(json.dumps(seed))
    rows=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for _,t in requests),text=True).splitlines()))
cases=[]
for (tail,tx),r in zip(requests,rows):
    swaps=[c for c in r['calls'] if c['data'].startswith('0x128acb08')]
    limit=word(bytes.fromhex(swaps[0]['data'][10:]),3) if len(swaps)==1 else None
    cases.append(dict(tail=tail,transaction=tx,limit=limit,fee_hypothesis_limit=reverse_v3_limit(1900000000,10,tail,10),result=r))
Path('reports/amm/routera3d-index4'+('-anchor' if a.at_anchor else '')+'-probe.json').write_text(json.dumps(dict(cases=cases,caveat='Controlled tail values and research seed; actual pool getter, swap intercepted. Tail semantics under investigation.'),indent=2)+'\n')
print([(c['tail'],c['limit'],c['limit']==c['fee_hypothesis_limit'],c['result']['error'],[(x['to'],x['data'][:10]) for x in c['result']['calls']]) for c in cases])
