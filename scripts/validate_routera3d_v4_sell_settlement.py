"""Validate sell route settlement frames and actual WETH storage writes."""
import argparse,json,subprocess
from pathlib import Path
from routera3d_v4 import WETH
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');a=ap.parse_args()
cases=json.loads(Path('tests/fixtures/routera3d_v4_sell.json').read_text())['cases'];records=[]
for index,c in enumerate(cases):
    subprocess.run(['python3','scripts/probe_routera3d_v4_sell_settlement.py',a.seed,'--case',str(index)],check=True,capture_output=True,text=True)
    doc=json.loads(Path(f'reports/amm/routera3d-v4-sell-settlement-probe-{index}.json').read_text());r=doc['result']
    assert not r['calls']
    assert r['error']=='database error: unknown account 0x78F3556b67E17Df817D51Ef5a990cDaF09E8d3A9'
    for selector in ('0x7782c562','0x48c89491','0x91dd7346'):
        frames=[x for x in r['execution_returns'] if x['selector']==selector]
        assert len(frames)==1 and frames[0]['result']=='Return'
    amount=-c['intent']['amount'];parent,child=doc['synthetic_storage']
    pw=[int(w['value'],16) for w in r['storage_writes'] if w['address']==WETH and int(w['slot'],16)==int(parent['slot'],16)]
    cw=[int(w['value'],16) for w in r['storage_writes'] if w['address']==WETH and int(w['slot'],16)==int(child['slot'],16)]
    assert pw==[10**18-amount] and cw==[amount,0],(pw,cw)
    assert int(doc['synthetic_transfer']['data'][-64:],16)==-c['result']['amount1']
    records.append(dict(case=index,weth_debit=amount,usdg_credit=-c['result']['amount1'],child_weth_final=0,route_success=True))
Path('reports/amm/routera3d-v4-sell-settlement-validation.json').write_text(json.dumps(dict(matches=len(records),records=records,
    caveat='Actual WETH transfer/withdraw/balance getters with explicit synthetic initial balances; USDG transfer and parent balance replies synthetic. Route/unlock return but final oracle absent, not historical root parity.'),indent=2)+'\n')
print(f'{len(records)} sell settlements match actual WETH writes and successful route/unlock frames')
