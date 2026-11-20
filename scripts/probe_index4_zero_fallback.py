"""Explicit synthetic factory fee interventions for zero callback return."""
import copy,json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import mapping
from index4_pool_state import load
POOL='0x7615926023bb149f36095645c2a81dc367d39750';FEE='0xc0ed888afe87ed1acf01d9f19bb850159e3ce434';HELPER='0xaa48aaef655fb7cd7acc04717f66022a4771a345';CALLER='0xe3c90972c6462bb4a4c75cf49dcf4189c5b42880';FACTORY='0xc63d7338c178e805c544b8f897066bd3bbcbe136'
seed=json.load(open('reports/amm/routera3d-index4-ticks-dependencies.json'));source=json.load(open('reports/amm/routera3d-index4-crossing-probe.json'));r=source['cases'][0]['stages'][-1]
seed.update(trace_execution=True,trace_hashes=True)
seed['execute_targets']=sorted({c['code'] for c in r['execution_calls'] if c['scheme'] in ('Call','StaticCall') and int(c['code'],16)>65535 and c['code'] not in ('0x0bd7d308f8e1639fab988df18a8011f41eacad73','0x5fc5360d0400a0fd4f2af552add042d716f1d168')})
seed['delegate_targets']=sorted({c['code'] for c in r['execution_calls'] if c['scheme']=='DelegateCall'})
profile=mapping(int(CALLER,16),2);cache=mapping(int(seed['anchor']['number'],16),int(mapping(int(POOL,16),4),16));fallback_slot=mapping(50,15);cases=[]
for side in (0,1):
 reference=source['cases'][side];tx=reference['transaction'];limit=int.from_bytes(bytes.fromhex(tx['data'][10:])[96:128],'big')
 for stored in (0,263):
  for fallback in (0,1,100,500,1000):
   s=copy.deepcopy(seed);s['accounts'][HELPER]['storage'][profile]=hex(1000000<<8);s['accounts'][FEE]['storage'][cache]=hex(stored);s['accounts'][FACTORY]['storage'][fallback_slot]=hex(fallback)
   with tempfile.NamedTemporaryFile(suffix='.json') as f:
    Path(f.name).write_text(json.dumps(s));result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',f.name],input=json.dumps(tx)+'\n',text=True))
   assert not result['error'],result['error']
   returns=[x for x in result['execution_returns'] if x['to']==FACTORY and x['selector']=='0x380dc1c2'];assert len(returns)==1 and int(returns[0]['output'],16)==fallback
   callbacks=[x for x in result['execution_returns'] if x['to']==FEE and x['selector']=='0xd3e6bf58'];assert len(callbacks)==1 and int(callbacks[0]['output'],16)==0
   curve=load(s['accounts'][POOL]['storage'],effective_fee=fallback,bitmap_words=[seed['tick_initialization']['bitmap_word']]);expected=curve.swap(reference['zero'],reference['amount'],limit,True)
   transfers=[x for x in result['calls'] if x['data'].startswith('0xa9059cbb')];assert len(transfers)==len(result['calls'])==1
   assert int(transfers[0]['data'][-64:],16)==-expected['amount1' if reference['zero'] else 'amount0']
   writes=[w for w in result['storage_writes'] if w['address']==POOL and int(w['slot'],16)==6];assert int(writes[-1]['value'],16)&((1<<160)-1)==expected['sqrt']
   cases.append(dict(side=side,stored=stored,fallback=fallback,expected=expected,result=result))
Path('reports/amm/routera3d-index4-zero-fallback-probe.json').write_text(json.dumps(dict(anchor_hash=seed['anchor']['hash'],factory_slot=fallback_slot,cases=cases,caveat='Synthetic factory/caller settings, actual pool bytecode until token transfer. No claim about current factory value or root success.'),indent=2)+'\n')
print('matched cases',len(cases))
