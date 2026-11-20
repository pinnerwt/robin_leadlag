"""Offline compressed-header block-window boundaries against router bytecode."""
import argparse,copy,json,subprocess,tempfile
from pathlib import Path
from routera3d_settings import CHILD
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');a=ap.parse_args()
original=json.load(open(a.seed));ref=json.loads(Path('tests/fixtures/routera3d_price.json').read_text())[0]
tx=next(r['tx'] for r in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')) if r['tx']['tx']==ref['tx']);cases=[]
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
    for future in (1,3,5):
        seed=copy.deepcopy(original);old=int(seed['accounts'][CHILD]['storage']['0x9'],16)
        setting=(old&~(0xffff<<144))|(future<<144);seed['accounts'][CHILD]['storage']['0x9']=hex(setting)
        requests=[];expected=[]
        for expiry in (0,tx['sequence']-1,tx['sequence'],tx['sequence']+1,tx['sequence']+2,tx['sequence']+3,tx['sequence']+4,tx['sequence']+100):
            for offset in (-1,0,1,2,3):
                raw=bytearray.fromhex(tx['data'][2:]);raw[9:13]=expiry.to_bytes(4,'big')
                request=dict(tx,data='0x'+raw.hex(),sequence=tx['sequence']+offset)
                requests.append(request);expected.append((expiry,request['sequence']))
        Path(tmp.name).write_text(json.dumps(seed))
        rows=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in requests),text=True).splitlines()))
        assert len(rows)==len(requests)
        for request,(expiry,block),row in zip(requests,expected,rows):
            invalid=not block<=expiry<=block+future;got=row['output']=='0x203d82d8'
            assert invalid==got,(future,expiry,block,row['output'])
            if invalid:assert row['execution_success'] is False and row['error'] is None and not row['calls']
            cases.append(dict(calldata=request['data'],block=block,expiry=expiry,slot9=hex(setting),max_future_blocks=future,invalid=invalid))
Path('reports/amm/routera3d-expiry-validation.json').write_text(json.dumps(dict(matches=len(cases),cases=cases,
    caveat='Controlled config future-window fields 1/3/5; entry block-window gate only. Later swap/root success not implied.'),indent=2)+'\n')
print(f'{len(cases)} exact block-window boundaries match')
