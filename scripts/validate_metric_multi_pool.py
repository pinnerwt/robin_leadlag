"""Offline multi-pool quote smoke; never starts capture or uses RPC."""
import json
from pathlib import Path
from metric_worker import MetricWorker
from tape import MAGIC,write_record

def main():
 rows=[]
 with MetricWorker('captures/checkpoint.json') as worker:
  for pool,p in worker.pools.items():
   if p.get('curator')!='Carcosa':continue
   for size in ('0.02','0.1'):rows.append(worker.quote(pool,size))
 result=dict(anchor=worker.anchor['hash'],quotes=rows,priced=sum(r['status']=='priced' for r in rows),unavailable=sum(r['status']!='priced' for r in rows),caveat='Archived initial-state quote check only; not continuous capture or current market quotes.')
 Path('reports/metric-multi-pool-smoke.json').write_text(json.dumps(result,indent=2)+'\n')
 with open('reports/metric-multi-pool-smoke.bin','wb') as f:
  f.write(MAGIC)
  for row in rows:write_record(f,row)
 print(json.dumps({k:v for k,v in result.items() if k!='quotes'}))
if __name__=='__main__':main()
