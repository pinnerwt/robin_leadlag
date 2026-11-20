"""Initialize ticks named by a known bitmap word at the checkpoint anchor."""
import argparse,json
from pathlib import Path
from bootstrap_state import Bootstrap,mapping
from bootstrap_storage import read_slots
from bootstrap_index4_observations import POOL
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('checkpoint');a=ap.parse_args();p=Path(a.checkpoint);s=json.loads(p.read_text());raw={int(k,16):int(v,16) for k,v in s['accounts'][POOL]['storage'].items()}
tick=raw[6]>>160&((1<<24)-1);tick=tick-(1<<24) if tick&(1<<23) else tick
spacing=raw[12]>>176&((1<<24)-1);index=(tick//spacing)>>8
bitmap=raw[int(mapping(index,15),16)];ticks=[(index*256+bit)*spacing for bit in range(256) if bitmap>>bit&1]
keys=[int(mapping(t,14),16)+offset for t in ticks for offset in range(8)]
b=Bootstrap('https://rpc.mainnet.chain.robinhood.com',interval=.1);block=s['anchor']['number']
if b.rpc('eth_getBlockByNumber',[block,False])['hash']!=s['anchor']['hash']:raise ValueError('anchor')
values=read_slots(b.rpc,block,{POOL:keys})[POOL]
if b.rpc('eth_getBlockByNumber',[block,False])['hash']!=s['anchor']['hash']:raise ValueError('anchor changed')
for k,v in values.items():
 if int(k,16) in raw and raw[int(k,16)]!=int(v,16):raise ValueError('storage mismatch')
s['accounts'][POOL]['storage'].update(values);s['rpc_calls']+=b.calls;s['tick_initialization']=dict(bitmap_word=index,ticks=ticks,slots_per_tick=8,rpc_calls=b.calls)
p.write_text(json.dumps(s,indent=2)+'\n');print('ticks',len(ticks),'slots',len(values),'calls',b.calls)
