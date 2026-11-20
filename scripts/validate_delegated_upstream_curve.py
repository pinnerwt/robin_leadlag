"""Compare upstream curve with bytecode under explicitly synthetic fee/hooks."""
import argparse,json
from pathlib import Path
from index4_pool_state import load

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--leg',type=int,choices=(1,2),default=1);ap.add_argument('--synthetic-observation',action='store_true');args=ap.parse_args();prefix='leg2-' if args.leg==2 else ''
 s=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
 e=json.loads(Path('reports/amm/delegated-upstream-cache-'+prefix+'discount-0-no-rewards-skip-post-hook'+('-synthetic-observation' if args.synthetic_observation else '')+'.json').read_text())
 tx=e['tx'];pool=tx['to'];storage=s['accounts'][pool]['storage'];raw={int(k,16):int(v,16) for k,v in storage.items()}
 tick=raw[6]>>160&0xffffff;tick=tick-(1<<24) if tick&(1<<23) else tick;spacing=raw[12]>>176&0xffffff;center=(tick//spacing)>>8
 d=bytes.fromhex(tx['data'][10:]);zero=bool(int.from_bytes(d[32:64],'big'));amount=int.from_bytes(d[64:96],'big',signed=True);limit=int.from_bytes(d[96:128],'big');cases=[]
 for case in e['cases']:
  actual=case['result'];assert not actual['error'] and len(actual['calls'])==1
  fees=[r for r in actual['execution_returns'] if r['selector']=='0xd3e6bf58' and r['result']=='Return'];assert len(fees)==1
  fee=int(fees[0]['output'],16);state=load(storage,effective_fee=fee,bitmap_words=range(center-2,center+3));expected=state.swap(zero,amount,limit,True)
  transfer=actual['calls'][0];assert transfer['data'].startswith('0xa9059cbb')
  assert int(transfer['data'][-64:],16)==-expected['amount0' if not zero else 'amount1']
  writes=[w for w in actual['storage_writes'] if w['address']==pool and int(w['slot'],16)==6]
  assert int(writes[-1]['value'],16)&((1<<160)-1)==expected['sqrt']
  cases.append(dict(synthetic_cache=case['synthetic_fee_cache'],charged_fee=fee,expected=expected))
 Path('reports/amm/delegated-upstream-'+prefix+'curve-validation.json').write_text(json.dumps(dict(synthetic_observation=args.synthetic_observation,anchor=s['anchor']['hash'],pool=pool,cases=cases,caveat='Curve prefix parity with synthetic cache, zero discount/reward lookup and no-op post hook. Not historical fee/output or settled execution.'),indent=2)+'\n')
 print(cases)
if __name__=='__main__':main()
