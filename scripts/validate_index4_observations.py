"""Compare local ring reads with real observe bytecode, no RPC or logs."""
import copy,json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import word
from index4_observations import Ring
from index4_fee import undiscounted_fee
POOL='0x7615926023bb149f36095645c2a81dc367d39750'
s=json.load(open('reports/amm/routera3d-index4-ticks-dependencies.json'));ring=Ring.load(s['accounts'][POOL]['storage']);raw={int(k,16):int(v,16) for k,v in s['accounts'][POOL]['storage'].items()};packed=raw[6];tick=packed>>160&((1<<24)-1);tick=tick-(1<<24) if tick&(1<<23) else tick;liq=raw[13]&((1<<128)-1);now=int(s['anchor']['timestamp'],16)
s.update(delegate_targets=['0x1642634c8cb1c9f1b84c9a1a08534f8c3f4e89f8'])
cases=[]
for elapsed in (0,5,600):
 for shift in (-200,0,200):
  time=now+elapsed;t=tick+shift;state=copy.deepcopy(s);state['accounts'][POOL]['storage']['0x6']=hex((packed&~(((1<<24)-1)<<160))|((t&((1<<24)-1))<<160))
  age=time-ring.records[ring.index].timestamp;oldest=time-ring.times[0]
  lookbacks=sorted(set([0,1,2,59,599,600,601,age,max(0,age-1),age+1,oldest]))
  data='0x883bdbfd'+b''.join(word(v) for v in [32,len(lookbacks),*lookbacks]).hex()
  tx=dict(tx=f'observe-{elapsed}-{shift}',to=POOL,data=data,sequence=int(s['anchor']['number'],16),timestamp=time,**{'from':'0xe3c90972c6462bb4a4c75cf49dcf4189c5b42880'})
  with tempfile.NamedTemporaryFile(suffix='.json') as f:
   Path(f.name).write_text(json.dumps(state));r=json.loads(subprocess.check_output(['target/release/examples/router_prefix',f.name],input=json.dumps(tx)+'\n',text=True))
  assert r['execution_success'] and not r['calls'] and not r['error'],r['error']
  output=bytes.fromhex(r['output'][2:]);arrays=[]
  for i in (0,32):
   offset=int.from_bytes(output[i:i+32],'big');count=int.from_bytes(output[offset:offset+32],'big');assert count==len(lookbacks)
   arrays.append([int.from_bytes(output[offset+32+32*j:offset+64+32*j],'big',signed=i==0) for j in range(count)])
  expected=[ring.observe(time,ago,t,liq) for ago in lookbacks];assert expected==list(zip(*arrays))
  cases.append(dict(time=time,tick=t,liquidity=liq,lookbacks=lookbacks,values=expected,bytecode_output=r['output']))
# End-to-end local observations -> fee, independently compared to actual fee callback.
fee_report=json.load(open('reports/amm/routera3d-index4-fee-cache-probe.json'));fees=[]
config=79|(7500<<24)|(8380000<<48)
for c in fee_report['cases']:
 if c['cached']!='tick_intervention':continue
 old=ring.observe(now,600,c['tick'],liq)[0];current=ring.observe(now,0,c['tick'],liq)[0]
 actual=undiscounted_fee(config,c['tick'],old,current,600);assert actual==c['fee']
 fees.append(dict(tick=c['tick'],fee=actual,side=c['side']))
report=dict(anchor_hash=s['anchor']['hash'],cases=cases,fee_cases=fees,caveat='Counterfactual time/tick getter reads. Ring writes, wrap handling and caller discounts remain unmodeled.')
Path('reports/amm/routera3d-index4-observation-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print('observe cases',len(cases),'read pairs',sum(len(c['lookbacks']) for c in cases),'end-to-end fee cases',len(fees))
