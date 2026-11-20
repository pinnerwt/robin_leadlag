"""Compare recorded-first local preview with saved actual V3 pool bytecode prefix."""
import json,subprocess,tempfile
from pathlib import Path
from delegated_single_local import preview
from v3_state import State

def main():
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
 cases=json.loads(Path('reports/amm/delegated-single-callback-probe.json').read_text())['cases']
 case=next(c for c in cases if c['tx']['tx'].startswith('0x7b104a4de6'))
 metadata={p['pool']:p for p in json.loads(Path('captures/startup-v9-quotes.json').read_text())['pools']}
 result=preview(case['tx']['data'],{a:State.load(p) for a,p in metadata.items()},metadata,metadata)
 expected=result['fills'][0];pool=expected['pool'];call=case['result']['calls'][0]
 tx=dict(case['tx'],to=pool,data=call['data'],**{'from':case['tx']['to']})
 raw={int(k,16):int(v,16) for k,v in seed['accounts'][pool]['storage'].items()}
 slot0=raw[0];index=(slot0>>184)&65535;card=(slot0>>200)&65535;now=int(seed['anchor']['timestamp'],16)
 tx['timestamp']=now;synthetic={}
 for obs,value in [(8+index,now|(1<<248)),(8+(index+1)%card,0)]:
  if obs not in raw:seed['accounts'][pool]['storage'][hex(obs)]=hex(value);synthetic[hex(obs)]=hex(value)
 seed['trace_execution']=True
 with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
  Path(tmp.name).write_text(json.dumps(seed))
  actual=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
 assert actual['error'] is None and len(actual['calls'])==1,actual.get('error')
 transfer=actual['calls'][0]
 assert transfer['to']==metadata[pool]['tokens'][0]
 assert transfer['data'].startswith('0xa9059cbb') and int(transfer['data'][-64:],16)==-expected['amount0']
 writes=[w for w in actual['storage_writes'] if w['address']==pool and int(w['slot'],16)==0]
 assert int(writes[-1]['value'],16)&((1<<160)-1)==expected['sqrt']
 report=dict(anchor=seed['anchor']['hash'],synthetic_observations=synthetic,expected=expected,result=actual,
  skipped_suffix=result['skipped_suffix'],stale_dependencies=result['stale_dependencies'],
  caveat='Same-checkpoint curve prefix only. Token output transfer intercepted; no settlement or historical prestate parity claim.')
 Path('reports/amm/delegated-single-curve-probe.json').write_text(json.dumps(report,indent=2)+'\n')
 print(expected)
if __name__=='__main__':main()
