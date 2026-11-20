"""Offline single index-6 sell route; explicit synthetic parent inventory."""
import argparse,json,subprocess,tempfile
from pathlib import Path
from routera3d_v4 import MANAGER,HOOK,WETH,USDG
from routera3d_settings import CHILD,PARENT
from routera3d_price import PRICE_XOR,route_fields,forward_v3_limit
from validate_routera3d_multiroute import enc
from v3_calldata import word,signed

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');a=ap.parse_args()
    seed=json.load(open(a.seed));ref=json.load(open('tests/fixtures/routera3d_price.json'))[0]
    tx=next(r['tx'] for r in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')) if r['tx']['tx']==ref['tx'])
    seed['execute_targets'] += [MANAGER,HOOK]
    seed.setdefault('delegate_targets',[]).append('0x3328004ae3b4ee272f25f3a2873f47c2fb678000')
    key='0x70a08231'+enc(int(PARENT,16))[2:]
    seed['getters'][WETH][key]=enc(10**18);seed['getters'][USDG][key]=enc(10**12)
    requests=[]
    for price in (1750000000,1800000000):
        for exponent in (8,10,12):
            raw=bytearray.fromhex(tx['data'][2:]);raw[0]=0xe1
            raw[1:6]=int(f'{price ^ PRICE_XOR:040b}'[::-1],2).to_bytes(5,'big')
            raw[6:9]=((65536<<7)|exponent).to_bytes(3,'big')
            requests.append(dict(tx,data='0x'+(raw[:13]+bytes.fromhex('69f60002')).hex()))
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        Path(tmp.name).write_text(json.dumps(seed))
        rows=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in requests),text=True).splitlines()))
    cases=[]
    for request,row in zip(requests,rows):
        swaps=[c for c in row['execution_calls'] if c['data'].startswith('0xf3cd914c')]
        cases.append(dict(transaction=request,result=row,swap_count=len(swaps)))
    Path('reports/amm/routera3d-v4-sell-probe.json').write_text(json.dumps(dict(cases=cases,
        caveat='Synthetic parent inventory; mixed-era seed; manager/hook executed, unknown token calls stop. Not successful settlement.'),indent=2)+'\n')
    print([(c['swap_count'],c['result']['error'],[(x['to'],x['data'][:10]) for x in c['result']['calls']]) for c in cases])

if __name__=='__main__':main()
