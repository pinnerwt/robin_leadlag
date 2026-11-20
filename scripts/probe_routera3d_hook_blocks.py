"""Offline block-boundary hook experiments with explicit local state writes."""
import argparse,copy,json,subprocess,tempfile
from pathlib import Path
from routera3d_v4 import HOOK,MANAGER
from probe_routera3d_hook_fee import IMPL

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');a=ap.parse_args()
    original=json.load(open(a.seed));doc=json.loads(Path('reports/amm/routera3d-index6-probe-10-settlement.json').read_text())
    call=next(c for c in doc['result']['execution_calls'] if c['to']==HOOK and c['scheme']=='Call' and c['data'].startswith('0x575e24b4'))
    first=json.loads(Path('reports/amm/routera3d-hook-fee-probe.json').read_text())['cases'][0]['result']
    tx=dict(doc['transaction'],to=HOOK,data=call['data'],**{'from':MANAGER})
    cases=[]
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        for price_state in ('unchanged','after_swap','up_1','up_10','up_100','up_1000','up_49','up_50','up_51'):
            seed=copy.deepcopy(original)
            for write in first['storage_writes']:
                seed['accounts'][write['address']]['storage'][write['slot']]=write['value']
            if price_state=='after_swap':
                for write in doc['result']['storage_writes']:
                    if write['address']==MANAGER:seed['accounts'][MANAGER]['storage'][write['slot']]=write['value']
            if price_state.startswith('up_'):
                from v3_state import tick_sqrt
                packed=int(seed['accounts'][MANAGER]['storage'][doc['slot']],16)
                sqrt=(packed&((1<<160)-1))*(1000000+int(price_state[3:]))//1000000
                tick=tick_sqrt(sqrt)
                seed['accounts'][MANAGER]['storage'][doc['slot']]=hex((packed&~((1<<184)-1))|sqrt|((tick&0xffffff)<<160))
            seed['execute_targets']=[MANAGER];seed['delegate_targets']=[IMPL]
            seed['control_targets']=[HOOK];seed['math_targets']=[HOOK]
            Path(tmp.name).write_text(json.dumps(seed))
            requests=[dict(tx,sequence=tx['sequence']+offset) for offset in (0,1,2,3,10)]
            rows=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in requests),text=True).splitlines()))
            assert len(rows)==len(requests)
            for request,row in zip(requests,rows):
                assert row['error'] is None and row['execution_success'] and not row['calls']
                output=bytes.fromhex(row['output'][2:]);assert len(output)==96
                cases.append(dict(price_state=price_state,block_offset=request['sequence']-tx['sequence'],fee_override=int.from_bytes(output[64:],'big'),result=row))
    Path('reports/amm/routera3d-hook-blocks-probe.json').write_text(json.dumps(dict(cases=cases,
        caveat='Synthetic second beforeSwap after successful standalone first hook writes. after_swap additionally applies manager writes from controlled settlement experiment. Independent block offsets, not a sequential series. No full transaction parity.'),indent=2)+'\n')
    print([(c['price_state'],c['block_offset'],c['fee_override']&0x3fffff,len(c['result']['storage_writes'])) for c in cases])

if __name__=='__main__':main()
