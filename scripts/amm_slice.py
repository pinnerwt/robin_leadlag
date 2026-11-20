"""Offline tape window beginning just before the AMM bootstrap anchor."""
import argparse,json
from tape import records
p=argparse.ArgumentParser(description=__doc__);p.add_argument('checkpoint');p.add_argument('tape');a=p.parse_args();seed=json.load(open(a.checkpoint));start=(int(seed['anchor']['timestamp'],16)-5)*10**9
for row in records([a.tape]):
 if row.get('recv_ns',0)>=start and row['kind'] in ('nitro_push','chain_log','head','gap'):
  print(json.dumps(row,separators=(',',':')))
