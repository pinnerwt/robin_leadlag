"""Controlled sequential hook execution; synthetic price path, real hook writes."""
import argparse,json,subprocess,tempfile
from pathlib import Path
from routera3d_v4 import HOOK,MANAGER
from probe_routera3d_hook_fee import IMPL
from v3_state import tick_sqrt
STATE='0x39268bb581114c0d9d797906ff1e7a584ef3dfc667652c317379e25ada21deef'

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');ap.add_argument('--forward',action='store_true');a=ap.parse_args()
    seed=json.load(open(a.seed));doc=json.loads(Path('reports/amm/routera3d-index6-probe-10-settlement.json').read_text())
    call=next(c for c in doc['result']['execution_calls'] if c['to']==HOOK and c['scheme']=='Call' and c['data'].startswith('0x575e24b4'))
    tx=dict(doc['transaction'],to=HOOK,data=call['data'],**{'from':MANAGER})
    if a.forward:
        from v3_state import MIN_SQRT
        raw=bytearray.fromhex(tx['data'][2:]);raw[4+6*32:4+7*32]=(1).to_bytes(32,'big')
        raw[4+8*32:4+9*32]=(MIN_SQRT+1).to_bytes(32,'big');tx['data']='0x'+raw.hex()
    first=json.loads(Path('reports/amm/routera3d-hook-fee-probe.json').read_text())['cases'][0]['result']
    for w in first['storage_writes']:seed['accounts'][w['address']]['storage'][w['slot']]=w['value']
    seed['execute_targets']=[MANAGER];seed['delegate_targets']=[IMPL];seed['control_targets']=[HOOK];seed['math_targets']=[HOOK]
    packed=int(seed['accounts'][MANAGER]['storage'][doc['slot']],16);initial=packed&((1<<160)-1)
    path=[(0,100),(1,100),(1,101),(2,101),(3,90),(3,80),(4,80),(7,80),(8,0),(9,0)]
    cases=[]
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        for offset,ppm in path:
            sqrt=initial*(1000000+ppm)//1000000;tick=tick_sqrt(sqrt)
            seed['accounts'][MANAGER]['storage'][doc['slot']]=hex((packed&~((1<<184)-1))|sqrt|((tick&0xffffff)<<160))
            before=seed['accounts'][HOOK]['storage'][STATE]
            request=dict(tx,sequence=tx['sequence']+offset)
            Path(tmp.name).write_text(json.dumps(seed))
            row=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(request)+'\n',text=True))
            assert row['error'] is None and row['execution_success'] and not row['calls']
            for w in row['storage_writes']:
                assert w['address']==HOOK and w['slot']==STATE
                seed['accounts'][HOOK]['storage'][STATE]=w['value']
            out=bytes.fromhex(row['output'][2:]);assert len(out)==96
            cases.append(dict(offset=offset,ppm=ppm,block=request['sequence'],sqrt=sqrt,before=before,after=seed['accounts'][HOOK]['storage'][STATE],fee=int.from_bytes(out[64:],'big')&0x3fffff,result=row))
    Path('reports/amm/routera3d-hook-sequence'+('-forward' if a.forward else '')+'-probe.json').write_text(json.dumps(dict(forward=a.forward,cases=cases,
        caveat='Real hook state chained after each successful standalone beforeSwap; synthetic controlled pool price path. Swap direction fixed per experiment. Not full swap/transaction replay.'),indent=2)+'\n')
    print([(c['offset'],c['ppm'],c['fee'],(int(c['after'],16)>>200)&0xffffff,(int(c['after'],16)>>224)&0xffffff) for c in cases])

if __name__=='__main__':main()
