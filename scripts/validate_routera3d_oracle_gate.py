"""Controlled oracle/gas sensitivity after actual sell settlement."""
import argparse,json,subprocess
from pathlib import Path
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');a=ap.parse_args();cases=[]
for price,gas,age in [(1800,0,0),(100,0,0),(10000,0,0),(1800,0,86400),(1800,100000000,0),(10000,100000000,0)]:
    subprocess.run(['python3','scripts/probe_routera3d_v4_sell_settlement.py',a.seed,'--oracle-price',str(price),'--gas-price',str(gas),'--oracle-age',str(age)],check=True,capture_output=True,text=True)
    doc=json.loads(Path(f'reports/amm/routera3d-v4-sell-settlement-probe-0-oracle-{price}-{gas}-{age}.json').read_text());r=doc['result']
    frames=[x for x in r['execution_returns'] if x['selector']=='0x7782c562']
    assert r['error'] is None and not r['calls']
    assert len(frames)==1 and frames[0]['result']=='Return'
    if price==10000:
        assert r['execution_success'] is False and r['output'].startswith('0xb7a91f17')
    else:
        assert r['execution_success'] is True and int(r['output'],16)==64
    cases.append(dict(price=price,gas_price=gas,age=age,error=r['error'],root_success=r['execution_success'],output=r['output'],unresolved_calls=r['calls'],route_results=[x['result'] for x in frames]))
Path('reports/amm/routera3d-oracle-gate-validation.json').write_text(json.dumps(dict(cases=cases,
    caveat='Synthetic oracle and initial balances/USDG delivery; actual router, manager, hook and WETH execution. Sensitivity only, not real feed state or historical parity.'),indent=2)+'\n')
print(cases)
