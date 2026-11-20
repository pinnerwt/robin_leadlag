"""Verify three-leg router amount propagation with explicit synthetic curve outputs."""
import copy,json
from pathlib import Path
from probe_delegated_kind8 import run
from probe_delegated_callback import callback_code
from index4_pool_state import load
from v3_state import MAX_SQRT

def main():
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
 case=next(c for c in json.loads(Path('reports/amm/delegated-single-callback-probe.json').read_text())['cases'] if c['tx']['tx'].startswith('0x9bc1'))
 prior=next(c for c in json.loads(Path('reports/amm/delegated-single-prefix-probe.json').read_text())['cases'] if c['tx']['tx']==case['tx']['tx'])
 tx=case['tx'];root=tx['to'].lower();unlock=prior['result']['calls'][0];manager=unlock['to'];s=copy.deepcopy(seed)
 s['getters']=case['synthetic_getters'];s['trace_execution']=True
 s['accounts'][manager]=dict(code='0x'+callback_code(bytes.fromhex('91dd7346'+unlock['data'][10:]),root).hex(),balance='0x0',nonce='0x0',storage={})
 s['execute_calls']=[manager+':'+unlock['data']];s['execute_targets']=[root]
 first_output=697680484060252927
 a=case['plan']['actions'][1];storage=seed['accounts'][a['target']]['storage'];packed=int(storage['0x6'],16);tick=packed>>160&0xffffff;tick=tick-(1<<24) if tick&(1<<23) else tick
 center=(tick//a['spacing'])>>8;curve=load(storage,effective_fee=511,bitmap_words=range(center-2,center+3))
 second=curve.swap(False,first_output,MAX_SQRT-1);second_output=-second['amount0']
 r=case['result'];stages=[]
 for index,output in enumerate((first_output,second_output)):
  call=r['calls'][0];a=case['plan']['actions'][index];assert call['to']==a['target'] and call['data'].startswith('0x128acb08')
  d=bytes.fromhex(call['data'][10:]);amount=int.from_bytes(d[64:96],'big');assert int.from_bytes(d[32:64],'big')==0
  s['getters'].setdefault(call['to'],{})[call['data']]='0x'+((-output)%(1<<256)).to_bytes(32,'big').hex()+amount.to_bytes(32,'big').hex()
  s['getters'].setdefault(a['token_out'],{})['0x70a08231'+'00'*12+root[2:]]=['0x'+'00'*32,'0x'+output.to_bytes(32,'big').hex()]
  r=run(s,tx);stages.append(r);print(index,r['error'],[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
 calls=r['calls']
 if len(calls)==1 and calls[0]['to']==manager and calls[0]['data'].startswith('0xa5841194'):
  s['getters'].setdefault(manager,{})[calls[0]['data']]='0x'
  r=run(s,tx);stages.append(r);print('after sync',r['error'],[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
 calls=r['calls']
 if len(calls)==1 and calls[0]['data']=='0x70a08231'+'00'*12+manager[2:]:
  c=calls[0];s['getters'].setdefault(c['to'],{})[c['data']]='0x'+'00'*32
  r=run(s,tx);stages.append(r);print('after balance',r['error'],[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
 report=dict(tx=tx,synthetic_first_output=first_output,synthetic_second_fee=511,second_curve=second,synthetic_second_output=second_output,stages=stages,
  caveat='Actual router amount propagation, synthetic funding and full output credit; second curve uses assumed fee511, not verified charged fee. Not historical/settlement parity.')
 Path('reports/amm/delegated-v3-chain-probe.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
