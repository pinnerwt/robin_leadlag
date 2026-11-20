"""Original callback control flow under explicitly synthetic strategy outcomes."""
import json,subprocess,tempfile,copy,argparse
from pathlib import Path
from probe_delegated_callback import callback_code
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--fresh-price',action='store_true');args=ap.parse_args()
source=json.loads(Path('reports/amm/delegated-router-funded-balance-0.json').read_text())['tx'];root=source['to'].lower()
report=json.loads(Path('reports/amm/delegated-condition-score-probe.json').read_text());baseline=next(c for c in report['cases'] if c['shift_bps']==0)
call=next(c for c in baseline['result']['execution_calls'] if c['data'].startswith('0x48c89491'));manager=call['to'];cb='0x91dd7346'+call['data'][10:]
strategies=[c['data'] for c in baseline['result']['execution_calls'] if c['data'].startswith('0x273a5b72')];assert len(strategies)==2
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());seed['trace_execution']=True
seed['accounts'][manager]=dict(code='0x'+callback_code(bytes.fromhex(cb[2:]),root).hex(),balance='0x0',nonce='0x0',storage={})
seed['execute_calls']=[manager+':'+call['data'],root+':'+cb];seed['getters']={}
for g in report['plan']['condition_groups']:
 for r in g['records']:seed['getters'].setdefault(r['target'],{})[r['calldata']]='0x'+r['value'].to_bytes(32,'big').hex()
cases=[]
for outcomes,second_shift in ([((1,1),n) for n in (-1,1)] if args.fresh_price else [(x,None) for x in [(None,None),(0,None),(1,None),(10**18,None),(None,1),(1,1),(1,2)]]):
 s=copy.deepcopy(seed);s['getters'][root]={data:'0x'+value.to_bytes(32,'big').hex() for data,value in zip(strategies,outcomes) if value is not None}
 if second_shift is not None:
  shared=report['plan']['condition_groups'][0]['records'][-1];ref=shared['value']
  s['getters'][shared['target']][shared['calldata']]=['0x'+ref.to_bytes(32,'big').hex(),'0x'+(ref*(10000+second_shift)//10000).to_bytes(32,'big').hex()]
 with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
  Path(tmp.name).write_text(json.dumps(s));r=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(source)+'\n',text=True))
 attempted=[strategies.index(c['data']) for c in r['execution_calls'] if c['to']==root and c['data'] in strategies]
 returns=[x for x in r['execution_returns'] if x['selector']=='0x91dd7346']
 cases.append(dict(second_price_shift_bps=second_shift,outcomes=outcomes,attempted=attempted,callback_returns=returns,result=r))
 print(outcomes,attempted,[(x['result'],x['output'][:80]) for x in returns],r['error'],flush=True)
Path('reports/amm/delegated-continuation-'+('fresh-price' if args.fresh_price else 'probe')+'.json').write_text(json.dumps(dict(cases=cases,caveat='Only strategy result outcomes are mocked; original callback code and condition processing. No executed swap/settlement claim.'),indent=2)+'\n')
