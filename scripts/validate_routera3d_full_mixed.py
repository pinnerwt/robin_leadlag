"""Whole router path under explicit synthetic fills, balances, transfers and oracle.
No claim that the synthetic pool runtime reconstructs actual AMM state.
"""
import argparse
import copy
import json
import subprocess
import tempfile
from pathlib import Path
from math import isqrt
from research_v3_stub import runtime
from routera3d_price import PRICE_XOR
from validate_routera3d_multiroute import P0, P1, CHILD, PARENT, USDG, WETH, enc

ORACLE='0x78f3556b67e17df817d51ef5a990cdaf09e8d3a9'

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('seed'); a=ap.parse_args()
    original=json.load(open(a.seed)); reference=json.load(open('tests/fixtures/routera3d_price.json'))[0]
    tx=next(r['tx'] for r in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')) if r['tx']['tx']==reference['tx'])
    raw=bytearray.fromhex(tx['data'][2:]); raw[0]=0xe2
    raw[1:6]=int(f'{1900000000 ^ PRICE_XOR:040b}'[::-1],2).to_bytes(5,'big')
    raw[6:9]=((65536<<7)|20).to_bytes(3,'big')
    tx=dict(tx,data='0x'+(raw[:13]+bytes.fromhex('09f619f60009')).hex())
    key='0x70a08231'+enc(int(PARENT,16))[2:]; cases=[]
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        for buy_spent in [10**9,10**10]:
            for divisor in [2,3]:
                seed=copy.deepcopy(original); initial_usdg=80*10**9
                buy_received=buy_spent*600000000; sell_spent=buy_received//divisor
                sell_received=sell_spent*2000*10**6//10**18
                slot0=seed['getters'][P0]['0x3850c7bd']
                slot1=bytearray.fromhex(slot0[2:]); slot1[:32]=isqrt((2000000000<<192)//10**18).to_bytes(32,'big')
                seed['accounts'][P0]['code']=runtime(CHILD,slot0,-buy_received,buy_spent)
                seed['accounts'][P1]['code']=runtime(CHILD,'0x'+slot1.hex(),sell_spent,-sell_received)
                seed['execute_targets'].extend([P0,P1])
                for token,pool,spent in [(USDG,P0,buy_spent),(WETH,P1,sell_spent)]:
                    data='0xa9059cbb'+enc(int(pool,16))[2:]+enc(spent)[2:]
                    seed['getters'][token][data]=enc(1)
                after_buy=initial_usdg-buy_spent; final_usdg=after_buy+sell_received
                final_weth=buy_received-sell_spent
                seed['getters'][USDG][key]=[enc(initial_usdg)]*3+[enc(after_buy)]*3+[enc(final_usdg)]*10
                seed['getters'][WETH][key]=[enc(0)]*2+[enc(buy_received)]*3+[enc(final_weth)]*10
                seed['accounts'][ORACLE]=dict(code='0x',balance='0x0',nonce=0,storage={})
                seed['getters'][ORACLE]={'0xfeaf968c':'0x'+''.join(enc(v)[2:] for v in [1,1900*10**8,tx['timestamp'],tx['timestamp'],1])}
                Path(tmp.name).write_text(json.dumps(seed))
                result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
                assert result['error'] is None and result['execution_success'] and not result['calls']
                frames=[r for r in result['execution_returns'] if r['selector']=='0x7782c562']
                callbacks=[r for r in result['execution_returns'] if r['selector']=='0xfa461e33']
                assert len(frames)==len(callbacks)==2
                assert all(r['result']=='Return' for r in frames+callbacks)
                assert int(result['output'],16)==3
                cases.append(dict(initial_usdg=str(initial_usdg),buy_spent=str(buy_spent),buy_received=str(buy_received),
                    sell_spent=str(sell_spent),sell_received=str(sell_received),final_usdg=str(final_usdg),final_weth=str(final_weth),
                    root_success=True,successful_frames=2,successful_callbacks=2,root_output=result['output']))
    report=dict(cases=cases,matches=len(cases),synthetic=['pool code and fixed deltas','ERC20 transfer success',
        'coherent balanceOf sequence','latestRoundData reply','zero research gas price'],
        caveat='Real router code path succeeds with synthetic external behavior. Not actual pool pricing, token storage parity or historical execution.')
    Path('reports/amm/routera3d-full-mixed-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print('4 full mixed router paths succeed with two callbacks and coherent synthetic balances')

if __name__=='__main__': main()
