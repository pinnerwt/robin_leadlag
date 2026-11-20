"""Offline frozen-price diagnostic: vary each oracle clock independently."""
import json,sys
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parent))
from causal_spcx_backtest import Worker
B=Path('reports/ohio-20ms-backtest');rows=[]
for symbol in ['ETHUSDT','NVDABUSDT']:
 seed=json.load(open(B/(symbol+'-seed.json')));pool=seed['pools'][0]
 w=Worker(str(B/(symbol+'-seed.json')),'provider-full')
 info=w.call(dict(kind='aux_info',feed=pool['aux_feed_id']));a='0x30a88bf894d1b806125a23ebf23d715496fd7102';b='0xe844701934d9c6085b292e428f41b911cc0b3872'
 storage=seed['accounts'][a]['storage'];auxword=next(int(v,16) for k,v in storage.items() if int(k,16)==int(info['slot'],16));sourceword=int(seed['accounts'][b]['storage'][pool['source_slot']],16)
 h=dict(seed['anchor']);sec=int(h['timestamp'],16)+30;h['timestamp']=hex(sec)
 for which in ['source','aux']:
  for age in [0,5,9,10,10.001,10.999,11,14,15,15.001,15.999,16,20]:
   sm=sec*1000-(int(age*1000) if which=='source' else 0);am=sec*1000-(int(age*1000) if which=='aux' else 0)
   sw=(sourceword&~(((1<<56)-1)<<8))|(sm<<8);aw=(auxword&~(((1<<56)-1)<<96))|(am<<96)
   w.change(dict(kind='patch',patch=[[b,pool['source_slot'],hex(sw)],[a,info['slot'],hex(aw)]]))
   try:out=w.call(dict(kind='quote',raw_base=str(10**17),header=h));error=None
   except ValueError as exc:out=None;error=str(exc)
   rows.append(dict(symbol=symbol,varied_oracle=which,age_seconds=age,other_oracle_age_seconds=0,priced=out is not None,error=error))
 w.close()
(B/'isolated-provider-expiry.json').write_text(json.dumps(rows,indent=2)+'\n')
for symbol in ['ETHUSDT','NVDABUSDT']:
 for which in ['source','aux']:
  rs=[r for r in rows if r['symbol']==symbol and r['varied_oracle']==which];print(symbol,which,[(r['age_seconds'],r['priced']) for r in rs])
