"""Research current dependency code with archived authorization calldata/context."""
import json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 code=json.loads(Path('reports/amm/delegated-wrapper-external-code.json').read_text());assert code['anchor_verified']
 source=json.loads(Path('reports/amm/delegated-wrapper-v4-probe.json').read_text());call=source['result']['calls'][0]
 seed=dict(anchor=code['anchor'],accounts={code['address']:dict(code=code['code'],balance='0x0',nonce='0x0',storage={})},trace_execution=True)
 seed['accounts']['0x'+'00'*19+'01']=dict(code='0x',balance='0x0',nonce='0x0',storage={})
 seed['accounts']['0x'+'00'*20]=dict(code='0x',balance='0x0',nonce='0x0',storage={})
 seed['execute_targets']=['0x'+'00'*19+'01']
 tx=dict(source['tx'],to=call['to'],data=call['data'],**{'from':source['tx']['to']})
 result=run(seed,tx)
 Path('reports/amm/delegated-wrapper-authorization-probe.json').write_text(json.dumps(dict(code_anchor=code['anchor']['hash'],code_hash=code['code_hash'],tx=tx,result=result,
  caveat='New-block code executed with archived caller/time/calldata, synthetic empty persistent storage/account metadata. Research only; not historical code/state parity.'),indent=2)+'\n')
 print(result['error'],result.get('execution_success'),result.get('output'),result['calls'])
if __name__=='__main__':main()
