"""Full saved-corpus audit for the newly decoded batch family, no RPC.
Logs only compare recorded pool identities, never determine swap quantities.
"""
import json
from collections import Counter
from pathlib import Path
from initialize_batch_bridge import validate_router_pins
from delegated_batch_route import inspect,router_payload
from delegated_batch_envelope import inspect as envelope
from delegated_holder_plan import inspect as holder
from v4_pool_state import load
from amm_feed_state import SWAP
from delegated_settler_v3 import intent as v3_intent
from variant_external_route import inspect as external_route
from variant_batch_route import inspect as funded_route
MANAGER='0x8366a39cc670b4001a1121b8f6a443a643e40951'
def classify(tx,logs,seed,pools,upstream_pools=()):
 if not tx.get('data','').startswith('0xc3c16ee4'):return None
 observed=sorted({l['address'].lower() for l in logs if l.get('topics',[None])[0]==SWAP and l['address'].lower() in pools})
 try:
  validate_router_pins(seed,tx.get('to'))
  plan=inspect(tx['data'],list(pools.values()))
 except (ValueError,KeyError) as exc:
  candidate=None
  try:
   batch=envelope(tx['data']);nested=router_payload(batch['calls'][1]['data']);parsed=holder(nested['payload'])
   downstream=[]
   for action in parsed['actions']:
    if action['selector']=='0x8d68a156':
     try:
      route=v3_intent(action['data'],2,list(pools.values()));route.pop('amount');route['amount_source']='upstream output plus carried inventory minus one';downstream.append(route)
     except ValueError:pass
   candidate=dict(action_selectors=[a['selector'] for a in parsed['actions']],downstream_recorded_routes=downstream,entry_code_verified=False,execution_verified=False)
   candidate['whole_route']=None
   for decoder in (external_route,funded_route):
    try:
     decoded=decoder(tx['data'],list(pools.values())+list(upstream_pools))
     candidate['whole_route']=dict(pools=decoded['pools'],recorded_pools=[p for p in decoded['pools'] if p in pools],scope_verified=False,execution_verified=False)
     break
    except ValueError:pass
  except (ValueError,KeyError,IndexError):pass
  return dict(status='batch_unresolved',reason=str(exc),observed_pools=observed,structural_candidate=candidate,safe_to_skip=False)
 a=plan['v4'];key=dict(currency0=a['currency0'],currency1=a['currency1'],fee=a['fee'],tick_spacing=a['spacing'],hooks=a['hook'])
 numeric_error=None
 try:
  curve=load(seed['accounts'][MANAGER]['storage'],key);curve.swap(a['zero'],a['amount'],a['limit'])
 except ValueError as exc:numeric_error=str(exc)
 decoded=[plan['v3']['pool']];missing=sorted(set(observed)-set(decoded))
 return dict(status='batch_recorded_route_identified',observed_pools=observed,decoded_recorded_pools=decoded,observed_pools_not_explained=missing,
  upstream_key=key,upstream_curve_checkpoint_error=numeric_error,continuous_state_verified=False,safe_to_skip=False,
  remaining=['hook branch/accounting and shared dependencies must stay current','inventory and source continuity','top-level authorization/token execution not complete'])
def main():
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());quotes=json.loads(Path('captures/startup-v9-quotes.json').read_text())
 if seed['anchor']['hash']!=quotes['anchor']['hash']:raise ValueError('anchor mismatch')
 pools={p['pool']:p for p in quotes['pools']};rows=[];total=0;seen=set()
 imm=json.loads(Path('reports/amm/variant-v3-immutables.json').read_text())
 upstream=[dict(pool='0xf55045c021949b202a5d10451b2ffa01561c5f55',tokens=['0x'+imm[k]['output'][-40:] for k in ('token0()','token1()')],fee=int(imm['fee()']['output'],16),spacing=int(imm['tickSpacing()']['output'],16))]
 for entry in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()):
  tx=entry['tx'];total+=1
  if tx['tx'] in seen:raise ValueError('duplicate corpus transaction')
  seen.add(tx['tx']);result=classify(tx,entry['logs'],seed,pools,upstream)
  if result is not None:rows.append(dict(tx=tx['tx'],**result))
 report=dict(anchor=seed['anchor']['hash'],corpus_transactions=total,counts=dict(Counter(r['status'] for r in rows)),transactions=rows,
  caveats=['Filtered historical corpus, not all chain activity','Research identification does not alter production decoder coverage','Missing old state is not filled using the newer checkpoint','No log amounts or prices used','Additional upstream immutable metadata comes from independent new-checkpoint code execution; structural candidate only, not old-checkpoint state coverage'])
 Path('reports/amm/batch-coverage-audit.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(total=total,counts=report['counts'],routes=[dict(tx=r['tx'],missing=r.get('observed_pools_not_explained'),curve_error=r.get('upstream_curve_checkpoint_error')) for r in rows])))
if __name__=='__main__':main()
