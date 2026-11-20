"""Controlled sell settlement; explicit USDG transfer reply, no network."""
import argparse,json,subprocess,tempfile
from pathlib import Path
from routera3d_v4 import MANAGER,HOOK,WETH,USDG
from routera3d_settings import PARENT,CHILD
from bootstrap_state import mapping
from validate_routera3d_multiroute import enc

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');ap.add_argument('--case',type=int,default=0);ap.add_argument('--oracle-price',type=int);ap.add_argument('--gas-price',type=int,default=0);ap.add_argument('--oracle-age',type=int,default=0);ap.add_argument('--parent-tolerance-bps',type=int);a=ap.parse_args()
    seed=json.load(open(a.seed));case=json.loads(Path('reports/amm/routera3d-v4-sell-probe.json').read_text())['cases'][a.case]
    tx=case['transaction'];seed['execute_targets'] += [MANAGER,HOOK]
    seed.setdefault('delegate_targets',[]).append('0x3328004ae3b4ee272f25f3a2873f47c2fb678000')
    key='0x70a08231'+enc(int(PARENT,16))[2:]
    seed['getters'][WETH][key]=enc(10**18);seed['getters'][USDG][key]=enc(10**12)
    transfer=case['result']['calls'][0]
    assert transfer['to']==USDG and transfer['data'].startswith('0xa9059cbb')
    seed['getters'][USDG][transfer['data']]=enc(1)
    amount=-int(json.loads(Path('tests/fixtures/routera3d_v4_sell.json').read_text())['cases'][a.case]['intent']['amount'])
    weth_transfer='0xa9059cbb'+enc(int(CHILD,16))[2:]+enc(amount)[2:]
    withdrawal='0x2e1a7d4d'+enc(amount)[2:]
    seed.setdefault('execute_calls',[]).extend([WETH+':'+weth_transfer,WETH+':'+withdrawal,WETH+':'+key])
    delivered=int(transfer['data'][-64:],16)
    seed['getters'][USDG][key]=[enc(10**12)]*2+[enc(10**12+delivered)]*16
    seed['delegate_targets'].append('0xc6b81b429797e0f555440b70cd99e032d7ae947e')
    synthetic_storage=[dict(address=WETH,slot=mapping(int(PARENT,16),0x33),value=enc(10**18)),
                       dict(address=WETH,slot=mapping(int(CHILD,16),0x33),value=enc(0))]
    for entry in synthetic_storage:seed['accounts'][WETH]['storage'][entry['slot']]=entry['value']
    seed['math_targets']=[PARENT,CHILD]
    seed['control_targets']=[PARENT,CHILD]
    if a.parent_tolerance_bps is not None:
        old=int(seed['accounts'][PARENT]['storage']['0x0'],16)
        seed['accounts'][PARENT]['storage']['0x0']=hex((old&~(65535<<176))|(a.parent_tolerance_bps<<176))
    oracle=None
    if a.oracle_price is not None:
        address='0x78f3556b67e17df817d51ef5a990cdaf09e8d3a9'
        oracle=dict(price=a.oracle_price,age=a.oracle_age,gas_price=a.gas_price)
        seed['accounts'][address]=dict(code='0x',balance='0x0',nonce=0,storage={})
        seed['getters'][address]={'0xfeaf968c':'0x'+''.join(enc(v)[2:] for v in [1,a.oracle_price*10**8,tx['timestamp']-a.oracle_age,tx['timestamp']-a.oracle_age,1])}
        tx=dict(tx,research_gas_price=hex(a.gas_price))
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        Path(tmp.name).write_text(json.dumps(seed))
        row=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
    Path(f'reports/amm/routera3d-v4-sell-settlement-probe-{a.case}{f'-oracle-{a.oracle_price}-{a.gas_price}-{a.oracle_age}' if oracle else ''}{f'-bps-{a.parent_tolerance_bps}' if a.parent_tolerance_bps is not None else ''}.json').write_text(json.dumps(dict(synthetic_oracle=oracle,synthetic_storage=synthetic_storage,transaction=tx,synthetic_transfer=transfer,result=row,
        caveat='Synthetic parent inventory and USDG transfer success. Unknown calls remain unresolved. Not historical transaction parity.'),indent=2)+'\n')
    print(json.dumps(dict(error=row['error'],calls=row['calls'],success=row['execution_success'],output=row['output']),indent=2))

if __name__=='__main__':main()
