"""Outer router continuation after an explicit successful holder response."""
import argparse,copy,json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--cleanup',action='store_true');ap.add_argument('--credit-output',action='store_true');ap.add_argument('--consume-input',action='store_true');args=ap.parse_args()
 if args.consume_input and not args.credit_output:ap.error('--consume-input requires --credit-output')
 if args.credit_output and not args.cleanup:ap.error('--credit-output requires --cleanup')
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());seed['trace_execution']=True
 c=json.loads(Path('reports/amm/delegated-batch-full-credit.json').read_text())['cases'][1];tx=c['tx']
 seed['accounts'][tx['to']]['storage'].update(c['synthetic_patches'])
 for a in c['synthetic_accounts']:seed['accounts'][a]=dict(code='0x',balance='0x0',nonce='0x0',storage={})
 seed['execute_targets']=['0x'+'00'*19+'01'];seed['getters']=copy.deepcopy(c['synthetic_getters'])
 if args.credit_output:
  usd='0x5fc5360d0400a0fd4f2af552add042d716f1d168'
  for key in seed['getters'].get(usd,{}):
   if key.startswith('0x70a08231'):seed['getters'][usd][key]=['0x'+bytes(32).hex(),'0x'+(1843011).to_bytes(32,'big').hex()]
 if args.consume_input:
  token='0x'+bytes.fromhex(tx['data'][10:])[44:64].hex()
  for key,value in seed['getters'][token].items():
   if key.startswith('0x70a08231'):
    if not isinstance(value,list) or len(value)<3:raise ValueError('unexpected input balance history')
    seed['getters'][token][key]=value[:3]+['0x'+bytes(32).hex()]
 holder=c['result']['calls'][0];ret=json.loads(Path('reports/amm/delegated-settler-tail-callback-output-4000000-paid.json').read_text())['result']['output']
 seed['getters'].setdefault(holder['to'],{})[holder['data']]=ret
 r=run(seed,tx);stages=[r]
 if args.cleanup:
  for _ in range(5):
   if r['error'] or not r['calls']:break
   changed=False
   for call in r['calls']:
    value=None
    if call['data'].startswith('0x095ea7b3') and int(call['data'][-64:],16)==0:value='0x'+(1).to_bytes(32,'big').hex()
    elif call['data'].startswith('0x70a08231') and call['to']=='0x5fc5360d0400a0fd4f2af552add042d716f1d168':value='0x'+(1843011).to_bytes(32,'big').hex()
    if value is None:continue
    entries=seed['getters'].setdefault(call['to'],{})
    if call['data'] not in entries:entries[call['data']]=value;changed=True
   if not changed:break
   r=run(seed,tx);stages.append(r)
 Path('reports/amm/delegated-outer-completion'+('-consumed' if args.consume_input else '-credited' if args.credit_output else '-cleanup' if args.cleanup else '')+'.json').write_text(json.dumps(dict(tx=tx,synthetic_holder_result=ret,stages=stages,synthetic_getters=seed['getters'],synthetic_patches=c['synthetic_patches'],synthetic_accounts=c['synthetic_accounts'],result=r,caveat='Actual outer code, synthetic successful holder result from separate high-output scenario. Funding/profile/signer assumptions inherited; not full transaction replay.'),indent=2)+'\n')
 print(r['error'],r['execution_success'],r['output'],r['calls'])
if __name__=='__main__':main()
