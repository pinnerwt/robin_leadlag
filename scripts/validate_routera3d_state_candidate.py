"""Join archived full V3 math to the real router path via synthetic pool callbacks."""
import argparse
import copy
import json
import subprocess
import tempfile
from pathlib import Path
from research_v3_stub import runtime
from routera3d_candidate import Candidate, USDG, WETH
from routera3d_price import PRICE_XOR
from validate_routera3d_multiroute import P0,P1,CHILD,PARENT,enc
from v3_calldata import word,signed


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('research_seed'); a=ap.parse_args()
    original=json.load(open(a.research_seed)); v3=json.load(open('captures/startup-v9-quotes.json'))
    assert original['anchor']['hash']==v3['anchor']['hash']
    inventory_seed=dict(anchor_hash=v3['anchor']['hash'],balances={USDG:10**13,WETH:0})
    model=Candidate(v3,inventory_seed); initial=copy.deepcopy((model.states,model.inventory))
    ref=json.load(open('tests/fixtures/routera3d_price.json'))[0]
    tx=next(r['tx'] for r in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')) if r['tx']['tx']==ref['tx'])
    key='0x70a08231'+enc(int(PARENT,16))[2:]; cases=[]
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        for exponent in [17,20,24]:
            raw=bytearray.fromhex(tx['data'][2:]); raw[0]=0xe2
            raw[1:6]=int(f'{1900000000^PRICE_XOR:040b}'[::-1],2).to_bytes(5,'big')
            raw[6:9]=((65536<<7)|exponent).to_bytes(3,'big')
            request=dict(tx,data='0x'+(raw[:13]+bytes.fromhex('09f619f60005')).hex())
            candidate=model.preview(request['data']); first,second=candidate['fills']
            seed=copy.deepcopy(original)
            for fill in candidate['fills']:
                pool=fill['pool']; slot0=seed['getters'][pool]['0x3850c7bd']
                assert word(bytes.fromhex(slot0[2:]),0)==model.states[pool].sqrt
                r=fill['result']; seed['accounts'][pool]['code']=runtime(CHILD,slot0,r['amount0'],r['amount1'])
                seed['execute_targets'].append(pool)
                transfer='0xa9059cbb'+enc(int(pool,16))[2:]+enc(r['amount1'])[2:]
                seed['getters'][USDG][transfer]=enc(1)
            seed['getters'][USDG][key]=[enc(model.inventory[USDG])]*3+[enc(first['inventory_after'][USDG])]*4+[enc(second['inventory_after'][USDG])]*10
            seed['getters'][WETH][key]=[enc(0)]*2+[enc(first['inventory_after'][WETH])]*2+[enc(second['inventory_after'][WETH])]*10
            oracle='0x78f3556b67e17df817d51ef5a990cdaf09e8d3a9'
            seed['accounts'][oracle]=dict(code='0x',balance='0x0',nonce=0,storage={})
            seed['getters'][oracle]={'0xfeaf968c':'0x'+''.join(enc(n)[2:] for n in [1,1900*10**8,tx['timestamp'],tx['timestamp'],1])}
            Path(tmp.name).write_text(json.dumps(seed))
            result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(request)+'\n',text=True))
            assert result['error'] is None and result['execution_success'] and not result['calls'], (result['error'],result['output'])
            assert int(result['output'],16)==3
            frames=[r for r in result['execution_returns'] if r['selector']=='0x7782c562']
            assert len(frames)==2 and all(r['result']=='Return' for r in frames)
            calls=[c for c in result['execution_calls'] if c['data'].startswith('0x128acb08')]
            assert len(calls)==2
            for call,fill in zip(calls,candidate['fills']):
                d=bytes.fromhex(call['data'][10:])
                assert call['to']==fill['pool'] and bool(word(d,1))==fill['zero']
                assert signed(word(d,2))==fill['amount'] and word(d,3)==fill['limit']
            assert (model.states,model.inventory)==initial
            cases.append(dict(exponent=exponent,fills=candidate['fills'],inventory=candidate['inventory'],root_success=True))
    report=dict(anchor_hash=v3['anchor']['hash'],cases=cases,matches=len(cases),
        caveat='Actual archived V3 state math determines deltas and candidate price/tick/liquidity. Real router validates call arguments and callbacks using synthetic pool runtime, transfers, balances and oracle. Not independent on-chain V3 execution or complete production branch coverage.')
    Path('reports/amm/routera3d-state-candidate-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print('3 local V3 candidates / 6 fills match router arguments and complete callback paths, including partial fills')

if __name__=='__main__':main()
