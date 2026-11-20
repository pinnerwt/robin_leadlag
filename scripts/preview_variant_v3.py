"""Offline actual-pool settlement probe and independent integer curve comparison."""
import json
from pathlib import Path
from bootstrap_state import mapping
from probe_delegated_kind8 import run
from v3_state import State

def main():
 r=json.loads(Path('reports/amm/variant-v3-prefix.json').read_text());s=r['seed'];tx=r['tx'];s['accounts'][tx['from']]['code']='0x00'
 r['synthetic'].append(dict(kind='callback_code_placeholder',address=tx['from'],code='0x00'))
 x=run(s,tx);r['stages'].append(x)
 if len(x['calls'])!=1 or not x['calls'][0]['data'].startswith('0xfa461e33'):raise ValueError('unexpected callback prefix')
 c=x['calls'][0];s['getters'].setdefault(c['to'],{})[c['data']]='0x';r['synthetic'].append(dict(kind='callback_success',call=c));x=run(s,tx);r['stages'].append(x);r['result']=x
 Path('reports/amm/variant-v3-settled.json').write_text(json.dumps(r,indent=2)+'\n')
 if not x['execution_success']:raise ValueError('isolated pool execution failed')
 storage={int(k,16):int(v,16) for k,v in s['accounts'][tx['to']]['storage'].items()};slot0=storage[0];tick=(slot0>>160)&((1<<24)-1);tick=tick-(1<<24) if tick&(1<<23) else tick
 bitmap={}
 for i in range(-18,18):
  key=int(mapping(i,6),16)
  if key in storage:bitmap[i]=storage[key]
 state=State(slot0&((1<<160)-1),tick,storage[4],10000,200,bitmap,{})
 d=bytes.fromhex(tx['data'][10:]);amount=int.from_bytes(d[64:96],'big',signed=True);limit=int.from_bytes(d[96:128],'big');zero=bool(int.from_bytes(d[32:64],'big'))
 fill=state.swap(zero,amount,limit)
 output=bytes.fromhex(x['output'][2:]);actual=[int.from_bytes(output[i:i+32],'big',signed=True) for i in (0,32)]
 writes={int(w['slot'],16):int(w['value'],16) for w in x['storage_writes']};after=writes[0];aftertick=(after>>160)&((1<<24)-1);aftertick=aftertick-(1<<24) if aftertick&(1<<23) else aftertick
 checks=dict(amounts=actual==[fill['amount0'],fill['amount1']],sqrt=after&((1<<160)-1)==fill['sqrt'],tick=aftertick==fill['tick'],full_fill=fill['unfilled']==0)
 report=dict(anchor=s['anchor']['hash'],pool=tx['to'],fill=fill,checks=checks,available_bitmap=sorted(bitmap),complete_tick_coverage=False,caveat='Original calldata size at new checkpoint, explicit settlement mocks. No historical parity or cross-anchor downstream composition.')
 Path('reports/amm/variant-v3-curve-parity.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
 if not all(checks.values()):raise ValueError('curve parity failed')
if __name__=='__main__':main()
