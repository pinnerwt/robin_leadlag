"""Actual saved kind-8 metadata getter and router prefix; no network."""
import copy,json,subprocess,tempfile
from pathlib import Path
from probe_delegated_callback import callback_code

def run(seed,tx):
 with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
  Path(tmp.name).write_text(json.dumps(seed))
  return json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
def main():
 prior=json.loads(Path('reports/amm/delegated-single-prefix-probe.json').read_text())['cases'][0]
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());seed['trace_execution']=True
 call=prior['result']['calls'][0]
 getter=run(seed,dict(prior['tx'],to=call['to'],data=call['data'],**{'from':prior['tx']['to']}))
 s=copy.deepcopy(seed);s['getters']=prior['synthetic_getters'];s['execute_calls']=[call['to']+':'+call['data']]
 prefix=run(s,prior['tx'])
 unlock=prefix['calls'][0];manager=unlock['to'];root=prior['tx']['to'].lower()
 cb=bytes.fromhex('91dd7346'+unlock['data'][10:])
 s['accounts'][manager]=dict(code='0x'+callback_code(cb,root).hex(),balance='0x0',nonce='0x0',storage={})
 s['execute_calls'].append(manager+':'+unlock['data']);s['execute_targets']=[root]
 callback=run(s,prior['tx'])
 report=dict(callback=callback,tx=prior['tx'],getter=getter,prefix=prefix,caveat='Saved actual metadata getter and root prefix, synthetic V3 token metadata inherited. No settlement/state-completeness claim.')
 Path('reports/amm/delegated-kind8-probe.json').write_text(json.dumps(report,indent=2)+'\n')
 print('getter',getter.get('error'),getter.get('execution_success'),getter.get('output'))
 print('callback',callback.get('error'),[(c['to'],c['data'][:10]) for c in callback['calls']])
 print('prefix',prefix.get('error'),[(c['to'],c['data'][:10]) for c in prefix['calls']])
if __name__=='__main__':main()
