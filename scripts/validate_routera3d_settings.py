"""Offline compare pure setter updates to successful research bytecode SSTOREs."""
import argparse
import copy
import json
import subprocess
import tempfile
from pathlib import Path
from routera3d_settings import update,CHILD
from validate_routera3d_multiroute import enc,PARENT

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');a=ap.parse_args()
    seed=json.load(open(a.seed));child=json.load(open('reports/amm/routera3d-child-code.json'))
    seed['accounts'][CHILD]['storage'].update(child['storage'])
    tx=json.loads(Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()[0])['tx']
    seed.setdefault('getters',{}).setdefault(PARENT,{})['0x8da5cb5b']=enc(int(tx['from'],16))
    seed['getters'][PARENT]['0x6d70f7ae'+enc(int(tx['from'],16))[2:]]=enc(1)
    specs=[('da0dfdc3',[10**18,10**9]),('da0dfdc3',[0,0]),
        ('7098d028',[0,1,10**18,10**12,50000]),('7098d028',[8,0,123,456,2000000]),
        ('875260d6',[1000000,100000000000,4000000000,3]),('875260d6',[1,2,3,1]),
        ('17a41e5a',[5250,6000,67*10**18,110*10**9]),('17a41e5a',[100,200,123,456])]
    cases=[]
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        for reserved in [False,True]:
            scenario=copy.deepcopy(seed); storage=scenario['accounts'][CHILD]['storage']
            if reserved:
                for slot,width in [('0x0',232),('0x8',232),('0x9',160),('0xa',208)]:
                    storage[slot]=hex(int(storage[slot],16)|(0xabcdef<<width))
            requests=[dict(tx,to=CHILD,data='0x'+selector+''.join(enc(v)[2:] for v in args),value='0x0') for selector,args in specs]
            Path(tmp.name).write_text(json.dumps(scenario))
            output=subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in requests),text=True)
            rows=list(map(json.loads,output.splitlines()));assert len(rows)==len(requests)
            for request,row in zip(requests,rows):
                assert row['error'] is None and row['execution_success'] and not row['calls']
                writes=row['storage_writes']; assert len(writes)==1
                expected=update(request['data'],storage); w=writes[0]
                assert w['address']==CHILD and w['slot']==expected['slot'] and int(w['value'],16)==expected['after']
                cases.append(dict(calldata=request['data'],initial_storage=storage,expected=expected,reserved_bits=reserved))
    Path('reports/amm/routera3d-settings-validation.json').write_text(json.dumps(dict(matches=len(cases),
        caveat='Current pinned research bytecode with synthetic owner/authorization replies. Slot packing parity, not complete writer coverage.'),indent=2)+'\n')
    Path('tests/fixtures/routera3d_settings.json').write_text(json.dumps(cases,indent=2)+'\n')
    print('16 setter calls match successful bytecode writes, including preserved upper bits')

if __name__=='__main__':main()
