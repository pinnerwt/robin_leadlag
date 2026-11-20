"""Synthetic first-pool callback to test the next route's inventory/budget input.
Router code is real research bytecode; pool fill and ERC20 replies are synthetic.
"""
import argparse
import copy
import json
import subprocess
import tempfile
from pathlib import Path
from research_v3_stub import runtime
from routera3d_price import PRICE_XOR, input_cap
from v3_calldata import word, signed

P0='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca'
P1='0x69bfaf19c9f377bb306a89aed9f6b07e2c1a8d9a'
CHILD='0xe3c90972c6462bb4a4c75cf49dcf4189c5b42880'
PARENT='0x000000000000a3d2e62895f55d5a4304d2f3c998'
USDG='0x5fc5360d0400a0fd4f2af552add042d716f1d168'
WETH='0x0bd7d308f8e1639fab988df18a8011f41eacad73'

def enc(n): return '0x'+(n % (1<<256)).to_bytes(32, 'big').hex()

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('seed'); a=ap.parse_args()
    original=json.load(open(a.seed)); reference=json.load(open('tests/fixtures/routera3d_price.json'))[0]
    tx=next(r['tx'] for r in map(json.loads, open('reports/amm/optimistic-target-corpus.jsonl')) if r['tx']['tx']==reference['tx'])
    raw=bytearray.fromhex(tx['data'][2:]); raw[0]=0xe2
    raw[1:6]=int(f'{1900000000 ^ PRICE_XOR:040b}'[::-1], 2).to_bytes(5, 'big')
    raw[6:9]=((65536<<7)|20).to_bytes(3, 'big')
    tx=dict(tx, data='0x'+(raw[:13]+bytes.fromhex('09f619f60005')).hex())
    cap=input_cap(tx['data']); key='0x70a08231'+enc(int(PARENT,16))[2:]; cases=[]
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        for inventory in [80*10**9, 10**12]:
            for spent in [10**9, 10**10, 20*10**9]:
                seed=copy.deepcopy(original); output=spent*600000000
                seed['getters'][P1]['0x3850c7bd']=seed['getters'][P0]['0x3850c7bd']
                seed['accounts'][P0]['code']=runtime(CHILD, seed['getters'][P0]['0x3850c7bd'], -output, spent)
                seed['execute_targets'].append(P0)
                seed['getters'][USDG][key]=[enc(inventory)]*3+[enc(inventory-spent)]*16
                seed['getters'][WETH][key]=[enc(0)]*2+[enc(output)]*16
                transfer='0xa9059cbb'+enc(int(P0,16))[2:]+enc(spent)[2:]
                seed['getters'][USDG][transfer]=enc(1)
                Path(tmp.name).write_text(json.dumps(seed))
                result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
                # Later oracle account is not initialized. It must not conceal an
                # earlier failure or allow a different unknown dependency.
                assert result['error'] in (None, 'database error: unknown account 0x78F3556b67E17Df817D51Ef5a990cDaF09E8d3A9')
                frames=[r for r in result['execution_returns'] if r['selector']=='0x7782c562']
                assert len(frames)==2 and frames[0]['result']=='Return' and frames[1]['result']=='Revert'
                callbacks=[r for r in result['execution_returns'] if r['selector']=='0xfa461e33']
                assert len(callbacks)==1 and callbacks[0]['result']=='Return'
                calls=[c for c in result['calls'] if c['data'].startswith('0x128acb08')]
                assert len(calls)==1 and calls[0]['to']==P1
                d=bytes.fromhex(calls[0]['data'][10:]); amount=signed(word(d,2))
                assert amount==min(inventory-spent,cap), (inventory,spent,amount)
                assert amount != min(inventory-spent, cap-spent)
                cases.append(dict(inventory=str(inventory),first_spent=str(spent),first_output=str(output),
                    cap=str(cap),second_amount=str(amount),first_callback_success=True,first_frame_success=True,
                    final_error=result['error']))
    report=dict(cases=cases, matches=len(cases),
        caveat='Synthetic fills/transfer success with coherent balance replies. First frame succeeds; second swap intentionally unexecuted and final oracle state incomplete. Not historical execution or full settlement.')
    Path('reports/amm/routera3d-multiroute-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print('6 successful first callbacks: second input=min(updated inventory, original per-route cap)')

if __name__=='__main__': main()
