"""Parent execute child setters plus balance-dependent parent tier postlude."""
import argparse,copy,json,subprocess,tempfile
from pathlib import Path
from routera3d_settings import CHILD,PARENT,transaction_update
from validate_routera3d_multiroute import enc
TIER2='0xb9e903f5a66a840f655da68c2b72cc9dda6305a0'
TIER1='0x5685f0b21126d87f60810780ce23c43ea45cb61e'

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');a=ap.parse_args()
    seed=json.load(open(a.seed));child=json.load(open('reports/amm/routera3d-child-code.json'))
    seed['accounts'][CHILD]['storage'].update(child['storage'])
    owner=int(seed['accounts'][PARENT]['storage']['0x1'],16)&((1<<160)-1)
    owner='0x'+owner.to_bytes(20,'big').hex()
    seed.setdefault('getters',{}).setdefault(PARENT,{})['0x8da5cb5b']=enc(int(PARENT,16))
    seed['getters'][PARENT]['0x6d70f7ae'+enc(int(PARENT,16))[2:]]=enc(1)
    reference=json.loads(Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()[0])['tx']
    fixtures=json.load(open('tests/fixtures/routera3d_settings.json'))[:8];requests=[]
    for case in fixtures:
        payload=bytes.fromhex(case['calldata'][2:])
        data='0xb61d27f6'+enc(int(CHILD,16))[2:]+enc(0)[2:]+enc(96)[2:]+enc(len(payload))[2:]+payload.hex()+bytes((-len(payload))%32).hex()
        requests.append(dict(reference,to=PARENT,**{'from':owner},data=data,value='0x0'))
    cases=[]
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        for tier2,tier1 in [(0,0),(0,1),(1,1)]:
            scenario=copy.deepcopy(seed)
            parent_state=dict(slot0=seed['accounts'][PARENT]['storage']['0x0'],tier2_balance=tier2,tier1_balance=tier1)
            for token,balance in [(TIER2,tier2),(TIER1,tier1)]:
                scenario['accounts'][token]=dict(code='0x',balance='0x0',nonce=0,storage={})
                scenario['getters'][token]={'0x70a08231'+enc(int(PARENT,16))[2:]:enc(balance)}
            Path(tmp.name).write_text(json.dumps(scenario))
            output=subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in requests),text=True)
            rows=list(map(json.loads,output.splitlines()));assert len(rows)==len(requests)
            for request,row,fixture in zip(requests,rows,fixtures):
                assert row['error'] is None and row['execution_success'] and not row['calls'],(row['error'],row['output'])
                expected=transaction_update(PARENT,request['data'],seed['accounts'][CHILD]['storage'],parent_state)
                post=expected['parent_postlude'];writes=row['storage_writes']
                assert len(writes)==1+post['write_required']
                child_writes=[w for w in writes if w['address']==CHILD]
                assert len(child_writes)==1 and child_writes[0]['slot']==expected['slot']
                assert int(child_writes[0]['value'],16)==expected['after']==fixture['expected']['after']
                parent_writes=[w for w in writes if w['address']==PARENT]
                if post['write_required']:
                    assert len(parent_writes)==1 and parent_writes[0]['slot']=='0x0' and int(parent_writes[0]['value'],16)==post['after']
                calls=[c for c in row['execution_calls'] if c['to']==CHILD]
                assert len(calls)==1 and calls[0]['data']==fixture['calldata']
                cases.append(dict(calldata=request['data'],child_calldata=fixture['calldata'],parent_state=parent_state,expected=expected))
    Path('reports/amm/routera3d-settings-wrapper-validation.json').write_text(json.dumps(dict(matches=len(cases),
        caveat='Pinned research code with synthetic child authorization and tier-token balances. Exact child/parent writes for canonical zero-value execute; other forwarding/upgrades remain uncovered.'),indent=2)+'\n')
    Path('tests/fixtures/routera3d_settings_wrapper.json').write_text(json.dumps(cases,indent=2)+'\n')
    print('24 parent wrappers match child writes and all three parent tier postludes')

if __name__=='__main__':main()
