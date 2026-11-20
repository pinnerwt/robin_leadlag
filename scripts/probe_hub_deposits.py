"""Synthetic deposit-state interventions against archived hub bytecode."""
import copy,json,subprocess,tempfile
from pathlib import Path
from hub_state import HUB,MASK248,deposit
from v3_calldata import word,address
from bootstrap_state import word as encode_word
seed=json.loads(Path('reports/amm/routerc9-c7-synthetic-seed.json').read_text())
base=json.loads(Path('reports/amm/hub-deposit-prefix.json').read_text())['request']
body=bytes.fromhex(base['data'][10:]);maker=address(word(body,0));token=address(word(body,3))
slot='0x7859253a4480e2de5a80daaf02b83b6e3c3feb0da9d367dba702d67452cf1f5f'
cases=[]
variants=[(f,b,a,1) for f in (0,1,2,254,255) for b,a in ((100,0),(100,5),(MASK248,1))]
variants.append((2,100,5,0))
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 for flags,balance,amount,token_success in variants:
    p=copy.deepcopy(seed);p['execute_targets']=[];p['delegate_targets']=[]
    old=(flags<<248)|balance;p['accounts'][HUB]['storage'][slot]=hex(old)
    tx=dict(base);raw=bytearray.fromhex(tx['data'][2:]);raw[132:164]=encode_word(amount);tx['data']='0x'+raw.hex()
    transfer='0x23b872dd'+b''.join(encode_word(int(v,16) if isinstance(v,str) else v) for v in (tx['from'],maker,amount)).hex()
    p.setdefault('getters',{}).setdefault(token,{})[transfer]='0x'+encode_word(token_success).hex()
    Path(tmp.name).write_text(json.dumps(p))
    r=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx),text=True))
    assert r['error'] is None
    try:expected=deposit(old,amount)
    except ValueError:expected=None
    assert r['execution_success']==(expected is not None and bool(token_success))
    writes=[w for w in r['storage_writes'] if w['address']==HUB]
    if expected is not None:assert len(writes)==1 and int(writes[0]['value'],16)==expected
    else:assert not writes
    cases.append(dict(flags=flags,balance=str(balance),amount=str(amount),token_success=bool(token_success),
                      expected_pending_value=hex(expected) if expected is not None else None,result=r))
Path('reports/amm/hub-deposit-validation.json').write_text(json.dumps(dict(
 purpose='Synthetic local bytecode validation with explicit token transfer return values; no actual transaction',cases=cases),indent=2)+'\n')
print(f'{len(cases)} cases match deposit arithmetic, flag guards, overflow and failed settlement')
