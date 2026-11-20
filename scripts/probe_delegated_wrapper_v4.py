"""Actual wrapper continuation with explicit synthetic upstream output credit."""
import argparse,json
from pathlib import Path
from probe_delegated_kind8 import run
from probe_delegated_callback import callback_code

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--authorization-code',action='store_true');args=ap.parse_args()
 e=json.loads(Path('reports/amm/delegated-wrapper-prefix-probe.json').read_text());tx=e['tx'];plan=e['plan']['plan'];root=tx['to'].lower()
 unlock=e['result']['calls'][0];manager=unlock['to'];s=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
 s['trace_execution']=True;s['getters']=e['synthetic_getters'];s['delegate_targets']=[root];s['execute_targets']=[root]
 s['execute_calls']=[manager+':'+unlock['data']]
 s['accounts'][manager]=dict(code='0x'+callback_code(bytes.fromhex('91dd7346'+unlock['data'][10:]),root).hex(),balance='0x0',nonce='0x0',storage={})
 current=e['callback_stages'][-1];stages=[];outputs=[10**17,10**18]
 for i,output in enumerate(outputs):
  a=plan['actions'][i];call=current['calls'][0];assert call['to']==a['target'] and call['data'].startswith('0x128acb08')
  d=bytes.fromhex(call['data'][10:]);amount=int.from_bytes(d[64:96],'big');zero=bool(int.from_bytes(d[32:64],'big'))
  deltas=(amount,-output) if zero else (-output,amount)
  s['getters'].setdefault(call['to'],{})[call['data']]='0x'+''.join((v%(1<<256)).to_bytes(32,'big').hex() for v in deltas)
  recipient='0x'+d[:32][-20:].hex();s['getters'].setdefault(a['token_out'],{})['0x70a08231'+'00'*12+recipient[2:]]=['0x'+'00'*32,'0x'+output.to_bytes(32,'big').hex()]
  current=run(s,tx);stages.append(current);print(i,current['error'],[(c['to'],c['data'][:10]) for c in current['calls']],flush=True)
  if len(current['calls'])==1 and current['calls'][0]['to']==manager and current['calls'][0]['data'].startswith('0x0b0d9c09'):
   take=current['calls'][0];s['getters'].setdefault(manager,{})[take['data']]='0x'
   current=run(s,tx);stages.append(current);print('after take',current['error'],[(c['to'],c['data'][:10]) for c in current['calls']],flush=True)
 synthetic_accounts=[]
 if current['error'] and 'unknown account 0xc348F6953705CD6dBF6d681b79b1e75F843D8A48' in current['error']:
  address='0xc348f6953705cd6dbf6d681b79b1e75f843d8a48';s['accounts'][address]=dict(code='0x00',balance='0x0',nonce='0x0',storage={});synthetic_accounts.append(address)
  current=run(s,tx);stages.append(current);print('placeholder',current['error'],[(c['to'],c['data'][:10]) for c in current['calls']],flush=True)
 code_evidence=None
 if args.authorization_code:
  code_evidence=json.loads(Path('reports/amm/delegated-wrapper-external-code.json').read_text());assert code_evidence['anchor_verified']
  address=code_evidence['address'];s['accounts'][address]=dict(code=code_evidence['code'],balance='0x0',nonce='0x0',storage={})
  for number in (0,1):s['accounts']['0x'+number.to_bytes(20,'big').hex()]=dict(code='0x',balance='0x0',nonce='0x0',storage={})
  s['execute_targets'].extend([address,'0x'+'00'*19+'01'])
  current=run(s,tx);stages.append(current);print('authorization',current['error'],[(c['to'],c['data'][:10]) for c in current['calls']],flush=True)
 for _ in range(6):
  if current['error'] or len(current['calls'])!=1:break
  c=current['calls'][0];reply=None
  if c['to']==manager and c['data'].startswith('0xa5841194'):reply='0x'
  if c['to']==manager and (c['data']=='0x11da60b4' or c['data']=='0x3dd45adb'+'00'*12+'c348f6953705cd6dbf6d681b79b1e75f843d8a48'):reply='0x'+outputs[-1].to_bytes(32,'big').hex()
  if c['to']==plan['actions'][2]['token_in'] and c['data'].startswith('0xa9059cbb'):reply='0x'+(1).to_bytes(32,'big').hex()
  if reply is None:break
  s['getters'].setdefault(c['to'],{})[c['data']]=reply;current=run(s,tx);stages.append(current)
  print('continue',current['error'],[(c['to'],c['data'][:10]) for c in current['calls']],flush=True)
 Path('reports/amm/delegated-wrapper-v4-'+('authorization-code' if args.authorization_code else 'probe')+'.json').write_text(json.dumps(dict(code_research_anchor=code_evidence['anchor']['hash'] if code_evidence else None,synthetic_accounts=synthetic_accounts,tx=tx,plan=plan,synthetic_outputs=outputs,stages=stages,result=current,
  caveat='Original wrapper with synthetic conditions, manager funding/settlement and upstream output credit. V4 argument evidence only.'),indent=2)+'\n')
if __name__=='__main__':main()
