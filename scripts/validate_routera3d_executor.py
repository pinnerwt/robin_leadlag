"""Verify executor replacement slot updates with local parent/child bytecode."""
import argparse,copy,json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import hashhex
from routera3d_settings import CHILD,PARENT,executor_update
from validate_routera3d_multiroute import enc

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');a=ap.parse_args()
    original=json.load(open(a.seed)); reference=json.loads(Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()[0])['tx']
    owner=int(original['accounts'][PARENT]['storage']['0x1'],16)&((1<<160)-1)
    new='0x'+'aa'*20;code_hash=hashhex(bytes.fromhex(original['accounts'][CHILD]['code'][2:]))
    cases=[]
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        for reserved,paused in [(0,0),(0xabcdef,0),(0xabcdef,1)]:
            seed=copy.deepcopy(original)
            old=int(seed['accounts'][PARENT]['storage']['0x0'],16)|(reserved<<232)|(paused<<160)|(2<<168)
            seed['accounts'][PARENT]['storage']['0x0']=hex(old)
            seed['accounts'][new]=copy.deepcopy(seed['accounts'][CHILD]);seed['execute_targets'].append(new)
            specs=[(CHILD,int(code_hash,16)),(new,int(code_hash,16)),('0x'+'00'*20,0)]
            requests=[dict(reference,to=PARENT,**{'from':'0x'+owner.to_bytes(20,'big').hex()},
                data='0x63f8683b'+enc(int(target,16))[2:]+enc(h)[2:],value='0x0') for target,h in specs]
            Path(tmp.name).write_text(json.dumps(seed))
            rows=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in requests),text=True).splitlines()))
            assert len(rows)==len(requests)
            for request,row in zip(requests,rows):
                assert row['error'] is None and row['execution_success'] and not row['calls']
                writes=row['storage_writes'];assert len(writes)==4 and all(w['address']==PARENT and w['slot']=='0x0' for w in writes)
                expected=executor_update(request['data'],old,code_hash)
                assert int(writes[-1]['value'],16)==expected['after']
                assert expected['requires_reinitialization']==(expected['executor']!=CHILD or expected['paused'])
                cases.append(dict(calldata=request['data'],slot0=hex(old),code_hash=code_hash,expected=expected))
    Path('reports/amm/routera3d-executor-validation.json').write_text(json.dumps(dict(matches=len(cases),
        caveat='Local real parent code; replacement target is a synthetic clone at a new address. No mainnet mutation. Same hash at new address still invalidates old state.'),indent=2)+'\n')
    Path('tests/fixtures/routera3d_executor.json').write_text(json.dumps(cases,indent=2)+'\n')
    print('9 executor replacements match slot0, pause semantics and state invalidation decisions')

if __name__=='__main__':main()
