"""Same-block reverse hook matrix from three actually reached reference states."""
import argparse,copy,json,subprocess,tempfile
from pathlib import Path
from routera3d_v4 import HOOK,MANAGER
from probe_routera3d_hook_fee import IMPL
from probe_routera3d_hook_sequence import STATE
from v3_state import tick_sqrt

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');ap.add_argument('--forward',action='store_true');a=ap.parse_args()
    original=json.load(open(a.seed));doc=json.loads(Path('reports/amm/routera3d-index6-probe-10-settlement.json').read_text())
    call=next(c for c in doc['result']['execution_calls'] if c['to']==HOOK and c['scheme']=='Call' and c['data'].startswith('0x575e24b4'))
    tx=dict(doc['transaction'],to=HOOK,data=call['data'],**{'from':MANAGER})
    if a.forward:
        from v3_state import MIN_SQRT
        raw=bytearray.fromhex(tx['data'][2:]);raw[4+6*32:4+7*32]=(1).to_bytes(32,'big')
        raw[4+8*32:4+9*32]=(MIN_SQRT+1).to_bytes(32,'big');tx['data']='0x'+raw.hex()
    sequence=json.loads(Path('reports/amm/routera3d-hook-sequence-probe.json').read_text())['cases'];cases=[]
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        for source in (sequence[0],sequence[1],sequence[8]):
            state=int(source['after'],16);reference=(state>>40)&((1<<160)-1);block=state&((1<<40)-1)
            for ppm in (-100,-10,-1,0,1,10,100):
                seed=copy.deepcopy(original);seed['accounts'][HOOK]['storage'][STATE]=hex(state)
                seed['execute_targets']=[MANAGER];seed['delegate_targets']=[IMPL]
                seed['math_targets']=[HOOK];seed['control_targets']=[HOOK]
                packed=int(seed['accounts'][MANAGER]['storage'][doc['slot']],16)
                sqrt=reference*(1000000+ppm)//1000000
                seed['accounts'][MANAGER]['storage'][doc['slot']]=hex((packed&~((1<<184)-1))|sqrt|((tick_sqrt(sqrt)&0xffffff)<<160))
                Path(tmp.name).write_text(json.dumps(seed))
                row=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(dict(tx,sequence=block))+'\n',text=True))
                assert row['error'] is None and row['execution_success'] and not row['calls'] and not row['storage_writes']
                raw=bytes.fromhex(row['output'][2:]);assert len(raw)==96
                cases.append(dict(state=hex(state),sqrt=sqrt,ppm=ppm,fee=int.from_bytes(raw[64:],'big')&0x3fffff,result=row))
    Path('reports/amm/routera3d-hook-sameblock'+('-forward' if a.forward else '')+'-probe.json').write_text(json.dumps(dict(forward=a.forward,cases=cases,
        caveat='Controlled price interventions from three real prior hook-write outputs; explicit forward/reverse beforeSwap calldata. No general config coverage or full transaction execution.'),indent=2)+'\n')
    print([(c['ppm'],c['fee']) for c in cases])

if __name__=='__main__':main()
