"""Validate observed parent final sell value-loss tolerance."""
import argparse,json,subprocess
from pathlib import Path
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');a=ap.parse_args()
fill=json.loads(Path('tests/fixtures/routera3d_v4_sell.json').read_text())['cases'][0]['result'];cases=[]
for price,bps in [(2000,0),(2000,500),(2000,1000),(2027,1000),(2028,1000)]:
    subprocess.run(['python3','scripts/probe_routera3d_v4_sell_settlement.py',a.seed,'--oracle-price',str(price),'--parent-tolerance-bps',str(bps)],check=True,capture_output=True,text=True)
    r=json.loads(Path(f'reports/amm/routera3d-v4-sell-settlement-probe-0-oracle-{price}-0-0-bps-{bps}.json').read_text())['result']
    marked=fill['amount0']*price*10**6//10**18;delta=-fill['amount1']-marked;tolerance=marked*bps//10000+10
    assert r['error'] is None and not r['calls']
    assert r['execution_success']==(delta>=-tolerance)
    frames=[x for x in r['execution_returns'] if x['selector']=='0x7782c562'];assert len(frames)==1 and frames[0]['result']=='Return'
    if not r['execution_success']:
        assert r['output'].startswith('0xb7a91f17')
        raw=bytes.fromhex(r['output'][10:]);actual=int.from_bytes(raw[:32],'big');actual=actual-(1<<256) if actual>>255 else actual
        assert actual==delta and int.from_bytes(raw[32:],'big')==tolerance
    cases.append(dict(price=price,bps=bps,marked=marked,delta=delta,tolerance=tolerance,root_success=r['execution_success']))
Path('reports/amm/routera3d-value-gate-validation.json').write_text(json.dumps(dict(cases=cases,matches=len(cases),
    caveat='Controlled single sell with synthetic oracle and funding/delivery. Formula scope excludes buys, mixed routes, price fallback/clamps and other parent branches.'),indent=2)+'\n')
print(cases)
