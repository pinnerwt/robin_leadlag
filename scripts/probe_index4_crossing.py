"""Offline crossing/partial-fill parity with explicitly synthetic settlement."""
import argparse,copy,json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import word,unpack
from bootstrap_index4_observations import POOL
from index4_pool_state import load
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');ap.add_argument('observations');ap.add_argument('--sequence',action='store_true');ap.add_argument('--cross-block',action='store_true');a=ap.parse_args()
if a.cross_block and not a.sequence:raise ValueError('cross-block requires sequence')
seed=json.load(open(a.seed));obs=json.load(open(a.observations));assert seed['anchor']['hash']==obs['anchor']['hash']
seed.update(trace_execution=True,trace_hashes=True)
seed['execute_targets']=['0x0575b823c22585f1828bbc133d5e522a8499165c','0xe033f4bd3d7ccf537a2f954ecdc8eb1218e3b7a6',POOL,'0x27d5eb73e7406675f6b0cbd037490ec3dba935a4','0xcc421483cd131a8fd6b68c37e46f244dbec4f797','0xf437f62053acb121665b8fdbfea8f214fb8e589d','0x382409fad8503fbcdbb27a4211551fa03e884078','0xdd1705e23762f4d6e44d8c31bd8ea80c54612239','0xc0ed888afe87ed1acf01d9f19bb850159e3ce434','0xc63d7338c178e805c544b8f897066bd3bbcbe136','0xaa48aaef655fb7cd7acc04717f66022a4771a345']
seed['delegate_targets']=['0xc7e262e848fca78c3c66ee3c9835e4e65e3e0398','0x89e91a960154b1ed6c093039a8f0725ab67d14e0','0x1642634c8cb1c9f1b84c9a1a08534f8c3f4e89f8','0x1ad7a8703ebff81c0d753190938f228672ec7e42']
caller='0xe3c90972c6462bb4a4c75cf49dcf4189c5b42880';tokens=['0x0bd7d308f8e1639fab988df18a8011f41eacad73','0x5fc5360d0400a0fd4f2af552add042d716f1d168'];h=seed['anchor'];sqrt=unpack(obs['slot0'])[0]
def run(s,tx):
 with tempfile.NamedTemporaryFile(suffix='.json') as f:
  Path(f.name).write_text(json.dumps(s));return json.loads(subprocess.check_output(['target/release/examples/router_prefix',f.name],input=json.dumps(tx)+'\n',text=True))
cases=[]
for zero,amount in [(False,10**9),(True,10**18),(False,10**12),(True,10**21)]:
 limit=sqrt*(99 if zero else 101)//100
 data='0x128acb08'+b''.join(word(v) for v in [int(caller,16),int(zero),amount,limit,160,0]).hex()
 tx=dict(tx=f'cross-{zero}-{amount}',to=POOL,data=data,sequence=int(h['number'],16)+(len(cases) if a.cross_block else 0),timestamp=int(h['timestamp'],16)+(len(cases) if a.cross_block else 0),l1_block=int(h.get('l1BlockNumber','0x1'),16),**{'from':caller})
 s=copy.deepcopy(seed);s['getters']={};stages=[run(s,tx)];case=dict(transaction=tx,zero=zero,amount=amount,stages=stages,matched=False)
 transfers=[c for c in stages[-1]['calls'] if c['to']==tokens[1 if zero else 0] and c['data'].startswith('0xa9059cbb')]
 if not stages[-1]['error'] and len(transfers)==1 and len(stages[-1]['calls'])==1:
  c=transfers[0];s['getters'][c['to']]={c['data']:'0x'+word(1).hex()}
  token=tokens[0 if zero else 1];balance='0x70a08231'+word(int(POOL,16)).hex();s['getters'].setdefault(token,{})[balance]=['0x'+word(0).hex()]
  stages.append(run(s,tx));callbacks=[c for c in stages[-1]['calls'] if c['to']==caller and c['data'].startswith('0xfa461e33')]
  if not stages[-1]['error'] and len(callbacks)==1 and len(stages[-1]['calls'])==1:
   callback=callbacks[0]['data'];raw=bytes.fromhex(callback[10:]);deltas=[int.from_bytes(raw[i:i+32],'big',signed=True) for i in (0,32)]
   spent=deltas[0 if zero else 1];assert 0<spent<=amount
   s['getters'].setdefault(caller,{})[callback]='0x';s['getters'][token][balance]=['0x'+word(0).hex(),'0x'+word(spent).hex()]
   stages.append(run(s,tx));r=stages[-1]
   if r['execution_success'] and not r['calls'] and not r['error']:
    fees=[int(x['output'],16) for x in r['execution_returns'] if x['selector']=='0xd3e6bf58'];assert len(fees)==1
    state=load(seed['accounts'][POOL]['storage'],effective_fee=fees[0],bitmap_words=[seed['tick_initialization']['bitmap_word']])
    expected=state.swap(zero,amount,limit,True)
    out=bytes.fromhex(r['output'][2:]);actual=[int.from_bytes(out[i:i+32],'big',signed=True) for i in (0,32)]
    writes={int(w['slot'],16):int(w['value'],16) for w in r['storage_writes'] if w['address']==POOL}
    final_slot=writes[6];final_tick=final_slot>>160&((1<<24)-1);final_tick=final_tick-(1<<24) if final_tick&(1<<23) else final_tick
    final_liq=writes.get(13,int(seed['accounts'][POOL]['storage']['0xd'],16))&((1<<128)-1)
    assert actual==[expected['amount0'],expected['amount1']],(actual,expected)
    assert (final_slot&((1<<160)-1),final_tick,final_liq)==(expected['sqrt'],expected['tick'],expected['liquidity'])
    case.update(matched=True,fee=fees[0],expected=expected,actual_deltas=actual)
 cases.append(case)
 if a.sequence:
  if not case['matched']:break
  for w in stages[-1]['storage_writes']:seed['accounts'][w['address']].setdefault('storage',{})[hex(int(w['slot'],16))]=w['value']
report=dict(anchor=h,sequence=a.sequence,cross_block=a.cross_block,cases=cases,results=[c['stages'][-1] for c in cases],caveat='Actual pool/helper code with synthetic token transfer/payment/callback. No historical/full-router or dynamic-fee reducer parity claim.')
Path('reports/amm/routera3d-index4-'+('cross-block' if a.cross_block else 'sequence' if a.sequence else 'crossing')+'-probe.json').write_text(json.dumps(report,indent=2)+'\n')
for c in cases:
 r=c['stages'][-1];print(c['transaction']['tx'],'matched',c['matched'],'error',r['error'],'calls',[(x['to'],x['data'][:10]) for x in r['calls']], 'curve',c.get('expected'))
