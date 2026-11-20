"""Offline fee callback cache interventions and same-block committed sequence."""
import copy,json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import mapping
POOL='0x7615926023bb149f36095645c2a81dc367d39750';FEE='0xc0ed888afe87ed1acf01d9f19bb850159e3ce434'
s=json.load(open('reports/amm/routera3d-index4-ticks-dependencies.json'));source=json.load(open('reports/amm/routera3d-index4-crossing-probe.json'));assert s['anchor']['hash']==source['anchor']['hash']
reference=source['cases'][0];r=reference['stages'][-1]
s.update(trace_execution=True,trace_hashes=True,math_targets=[FEE],control_targets=[FEE])
s['execute_targets']=sorted({c['code'] for c in r['execution_calls'] if c['scheme'] in ('Call','StaticCall') and int(c['code'],16)>0xffff and c['code'] not in ('0x0bd7d308f8e1639fab988df18a8011f41eacad73','0x5fc5360d0400a0fd4f2af552add042d716f1d168')})
s['delegate_targets']=sorted({c['code'] for c in r['execution_calls'] if c['scheme']=='DelegateCall'})
base=copy.deepcopy(s);slot=mapping(int(s['anchor']['number'],16),int(mapping(int(POOL,16),4),16));cases=[]
def run(seed,tx):
 with tempfile.NamedTemporaryFile(suffix='.json') as f:
  Path(f.name).write_text(json.dumps(seed));return json.loads(subprocess.check_output(['target/release/examples/router_prefix',f.name],input=json.dumps(tx)+'\n',text=True))
for side in (0,1):
 source_case=source['cases'][side];tx=source_case['transaction']
 for cached in (None,1,17,263,1000,'committed_previous_swap'):
  state=copy.deepcopy(base)
  if cached=='committed_previous_swap':
   prior=source_case['stages'][-1]
   assert prior['execution_success'] and not prior['calls'] and not prior['error']
   for w in prior['storage_writes']:state['accounts'][w['address']].setdefault('storage',{})[hex(int(w['slot'],16))]=w['value']
  elif cached is not None:state['accounts'][FEE]['storage'][slot]=hex(cached)
  result=run(state,tx)
  assert not result['error'],result['error']
  returns=[x for x in result['execution_returns'] if x['to']==FEE and x['selector']=='0xd3e6bf58']
  assert len(returns)==1 and returns[0]['result']=='Return'
  fee=int(returns[0]['output'],16)
  assert fee==(source_case['fee'] if cached is None or isinstance(cached,str) else cached)
  assert all(c['to'] in ('0x0bd7d308f8e1639fab988df18a8011f41eacad73','0x5fc5360d0400a0fd4f2af552add042d716f1d168') and c['data'].startswith('0xa9059cbb') for c in result['calls'])
  observations=sum(c['data'].startswith('0x883bdbfd') for c in result['execution_calls'])
  if cached is not None:assert observations==0
  cases.append(dict(side=side,cached=cached,fee=fee,observation_calls=observations,result=result))
# Independent config interventions test the uncached observed branch.
config_slot=mapping(int(POOL,16),3)
for side in (0,1):
 tx=source['cases'][side]['transaction']
 for minimum,maximum,slope in [(79,7500,0),(79,7500,1000000),(79,100,8380000),(10,7500,8380000),(79,1000,100000000)]:
  state=copy.deepcopy(base);original=int(state['accounts'][FEE]['storage'][config_slot],16)
  state['accounts'][FEE]['storage'][config_slot]=hex((original>>112<<112)|minimum|(maximum<<24)|(slope<<48))
  result=run(state,tx);assert not result['error'],result['error']
  returns=[x for x in result['execution_returns'] if x['to']==FEE and x['selector']=='0xd3e6bf58']
  assert len(returns)==1 and returns[0]['result']=='Return'
  observed=next(x['output'] for x in result['execution_returns'] if x['selector']=='0x883bdbfd')
  raw=bytes.fromhex(observed[2:]);cumulatives=[int.from_bytes(raw[i:i+32],'big',signed=True) for i in (96,128)]
  tick=int(base['accounts'][POOL]['storage']['0x6'],16)>>160&((1<<24)-1)
  if tick&(1<<23):tick-=1<<24
  delta=abs(tick-(cumulatives[1]-cumulatives[0])//600)
  fee=int(returns[0]['output'],16);expected=min(maximum,minimum+slope*delta//1000000)
  assert fee==expected,(minimum,maximum,slope,delta,fee,expected)
  cases.append(dict(side=side,cached='config_intervention',config=dict(minimum=minimum,maximum=maximum,slope=slope),tick_delta=delta,tick=tick,cumulatives=cumulatives,window_seconds=600,fee=fee,result=result))
# Tick-only counterfactuals isolate the fee branch; curve consistency/root
# success is deliberately not claimed for these synthetic states.
for side in (0,1):
 tx=source['cases'][side]['transaction']
 for shift in (-200,-50,-23,-22,-21,0,21,50,200):
  state=copy.deepcopy(base);packed=int(state['accounts'][POOL]['storage']['0x6'],16)
  tick=packed>>160&((1<<24)-1);tick=tick-(1<<24) if tick&(1<<23) else tick
  tick+=shift;state['accounts'][POOL]['storage']['0x6']=hex((packed&~(((1<<24)-1)<<160))|((tick&((1<<24)-1))<<160))
  result=run(state,tx)
  returns=[x for x in result['execution_returns'] if x['to']==FEE and x['selector']=='0xd3e6bf58']
  assert len(returns)==1 and returns[0]['result']=='Return', (shift,result['error'])
  observed=next(x['output'] for x in result['execution_returns'] if x['selector']=='0x883bdbfd')
  raw=bytes.fromhex(observed[2:]);cumulatives=[int.from_bytes(raw[i:i+32],'big',signed=True) for i in (96,128)]
  mean=(cumulatives[1]-cumulatives[0])//600;delta=tick-mean
  fee=int(returns[0]['output'],16);expected=min(7500,79+8380000*abs(delta)//1000000)
  assert fee==expected,(shift,tick,mean,fee,expected)
  cases.append(dict(side=side,cached='tick_intervention',shift=shift,tick=tick,mean_tick=mean,cumulatives=cumulatives,signed_tick_delta=delta,window_seconds=600,fee=fee,result=result))
report=dict(anchor_hash=s['anchor']['hash'],slot=slot,cases=cases,caveat='Original transaction origin/caller retained. Pool runs until output transfer, so current root not committed. Committed prior state comes only from a successful synthetic-funded pool case. Synthetic cache interventions are separate; new-block formula and caller discounts unmodeled.')
Path('reports/amm/routera3d-index4-fee-cache-probe.json').write_text(json.dumps(report,indent=2)+'\n')
for c in cases:print(c['side'],c['cached'],c['fee'],'calls',len(c['result']['execution_calls']),'writes',len(c['result']['storage_writes']))
