"""Offline controlled hook config interventions; no state or network writes."""
import argparse,copy,json,subprocess,tempfile
from pathlib import Path
from routera3d_v4 import HOOK,MANAGER
CONFIG='0x1d5f0817977a65a8a9c2638b77a39c03de637f72975a7eb2bca7a735fb40899a'
IMPL='0x3328004ae3b4ee272f25f3a2873f47c2fb678000'

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');a=ap.parse_args()
    original=json.load(open(a.seed));doc=json.loads(Path('reports/amm/routera3d-index6-probe-10-settlement.json').read_text())
    call=next(c for c in doc['result']['execution_calls'] if c['to']==HOOK and c['scheme']=='Call' and c['data'].startswith('0x575e24b4'))
    tx=dict(doc['transaction'],to=HOOK,data=call['data'],**{'from':MANAGER})
    old=int(original['accounts'][HOOK]['storage'][CONFIG],16);cases=[]
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        for field,value in [(5,40),(5,10),(5,80),(5,200),(6,320),(3,100),(5,0),(5,20),(5,30),(7,200),(9,200),(0,400)]:
            seed=copy.deepcopy(original);new=(old&~(0xffffff<<(24*field)))|(value<<(24*field))
            seed['accounts'][HOOK]['storage'][CONFIG]=hex(new)
            seed['execute_targets']=[MANAGER];seed['delegate_targets']=[IMPL]
            seed['control_targets']=[HOOK];seed['math_targets']=[HOOK]
            Path(tmp.name).write_text(json.dumps(seed))
            row=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
            assert row['error'] is None and row['execution_success'] and not row['calls'],row['error']
            raw=bytes.fromhex(row['output'][2:]);assert len(raw)==96
            cases.append(dict(field=field,value=value,config_before=hex(old),config_after=hex(new),output=row['output'],fee_override=int.from_bytes(raw[64:96],'big'),result=row))
    Path('reports/amm/routera3d-hook-fee-probe.json').write_text(json.dumps(dict(cases=cases,
        caveat='Controlled config interventions with archived hook/manager and fixed beforeSwap input. Fields are numbered low-to-high uint24, not yet general semantic names. Not complete fee function.'),indent=2)+'\n')
    print([(c['field'],c['value'],c['fee_override']) for c in cases])

if __name__=='__main__':main()
