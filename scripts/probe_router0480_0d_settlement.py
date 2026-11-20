"""Actual manager lock/root callback with explicitly synthetic swap return."""
import argparse,json
from pathlib import Path
from probe_delegated_kind8 import run
from router0480_0d import intent

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=int,default=1000000);ap.add_argument('--advance',action='store_true');ap.add_argument('--pay',action='store_true');ap.add_argument('--settle',action='store_true');ap.add_argument('--credit',type=int);a=ap.parse_args()
 if not 0<a.output<1<<127:raise ValueError('invalid synthetic native output')
 row=next(r for r in json.loads(Path('reports/amm/router0480-other-swaps.json').read_text())['cases'] if r['opcode']==13);tx=row['tx'];p=intent(row['original_tx']['data'],row['offset'],row['stop']);old=json.loads(Path('reports/amm/router0480-0d-manager.json').read_text());s=json.loads(Path('captures/startup-v9-dependencies.json').read_text());keep={tx['from'].lower(),tx['to'].lower(),'0x'+'00'*20};s['accounts']={k:v for k,v in s['accounts'].items() if k in keep or k[2:] in tx['data'].lower()};s.update(trace_execution=True,control_targets=[tx['to'].lower()],getters={},execute_calls=[])
 for c in row['synthetic_zero_inventory']:s['getters'].setdefault(c['to'],{})[c['data']]='0x'+bytes(32).hex()
 for c in (row['result']['calls'][0],old['stages'][0]['calls'][0]):s['execute_calls'].append(c['to']+':'+c['data'])
 c=old['result']['calls'][0];packed=(((-a.output)%(1<<128))<<128)|p['amount'];s['getters'].setdefault(c['to'],{})[c['data']]='0x'+(packed.to_bytes(32,'big')+bytes(32)).hex();r=run(s,tx);stages=[r];mocks=[]
 if a.advance and not r['error'] and len(r['calls'])==1 and r['calls'][0]['data'].startswith('0x3ccfd60b'):
  c=r['calls'][0];s['getters'].setdefault(c['to'],{})[c['data']]='0x';mocks.append(dict(call=c,response='0x'));r=run(s,tx);stages.append(r)
 if a.advance and not r['error'] and len(r['calls'])==1 and r['calls'][0]['data'].startswith('0xf9b6a796'):
  c=r['calls'][0];s['execute_calls'].append(c['to']+':'+c['data']);r=run(s,tx);stages.append(r)
 if a.pay:
  if not a.advance:raise ValueError('--pay requires --advance')
  for c in r['calls']:
   if c['data'].startswith('0x70a08231'):response='0x'+bytes(32).hex()
   elif c['data'].startswith('0xa9059cbb'):response='0x'+(1).to_bytes(32,'big').hex()
   else:raise ValueError('unexpected payment stage')
   s['getters'].setdefault(c['to'],{})[c['data']]=response;mocks.append(dict(call=c,response=response))
  r=run(s,tx);stages.append(r)
 if a.settle:
  if not a.pay or r['error'] or len(r['calls'])!=1:raise ValueError('settlement stage unavailable')
  c=r['calls'][0]
  if not c['data'].startswith('0x12e103f1'):raise ValueError('unexpected settlement call')
  s['execute_calls'].append(c['to']+':'+c['data']);balance='0x70a08231'+int(p['manager'],16).to_bytes(32,'big').hex();values=['0x'+bytes(32).hex(),'0x'+(p['amount'] if a.credit is None else a.credit).to_bytes(32,'big').hex()];s['getters'][p['currency1']][balance]=values;mocks.append(dict(token=p['currency1'],data=balance,response_sequence=values));r=run(s,tx);stages.append(r)
 Path('reports/amm/router0480-0d-settlement-'+str(a.output)+('-advance' if a.advance else '')+('-paid' if a.pay else '')+('-settled' if a.settle else '')+('' if a.credit is None else '-credit-'+str(a.credit))+'.json').write_text(json.dumps(dict(stages=stages,synthetic_settlement=mocks,tx=tx,synthetic_native_output=a.output,synthetic_swap_return=hex(packed),result=r,caveat='Synthetic packed swap delta and zero inventory, isolated command table. Actual manager lock and router callback; no manager swap or full transaction success claim.'),indent=2)+'\n');print(json.dumps(dict(error=r['error'],success=r['execution_success'],calls=r['calls'],returns=r['execution_returns'][-4:])))
if __name__=='__main__':main()
