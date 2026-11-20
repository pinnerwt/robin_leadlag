"""Structural c3c16ee4 batch extraction. No authorization/execution claim.

Offsets below describe the observed ABI layout only. Remaining header words,
inner tail, and outer authorization bytes stay opaque; never infer safe pool
scope from this envelope alone.
"""
from pathlib import Path
import json

def inspect(calldata):
 raw=bytes.fromhex(calldata.removeprefix('0x'))
 if raw[:4].hex()!='c3c16ee4':raise ValueError('batch selector')
 d=raw[4:]
 def word(offset):
  if offset<0 or offset+32>len(d):raise ValueError('truncated batch word')
  return int.from_bytes(d[offset:offset+32],'big')
 def blob(offset,end):
  n=word(offset);stop=offset+32+n;padded=offset+32+((n+31)//32)*32
  if padded>end or any(d[stop:padded]):raise ValueError('batch bytes bounds/padding')
  return d[offset+32:stop],padded
 if word(0)!=64:raise ValueError('batch tuple offset')
 auth=word(32)
 if auth%32 or auth<224 or auth>len(d):raise ValueError('batch authorization offset')
 if word(64)!=160:raise ValueError('batch body offset')
 body=224
 if word(body)!=64:raise ValueError('batch call array offset')
 array=body+64;n=word(array);base=array+32
 if not 0<n<=64:raise ValueError('batch call count')
 cursor=base+n*32;calls=[]
 for i in range(n):
  start=base+word(base+i*32)
  if start!=cursor:raise ValueError('noncanonical batch call offset')
  target=word(start)
  if target>=1<<160 or word(start+64)!=96:raise ValueError('batch call tuple')
  data,cursor=blob(start+96,auth)
  calls.append(dict(target='0x'+target.to_bytes(20,'big').hex(),value=word(start+32),data='0x'+data.hex()))
 authorization,end=blob(auth,len(d))
 if end!=len(d):raise ValueError('batch trailing bytes')
 return dict(header_words=[word(64+i*32) for i in range(1,5)],batch_field=word(body+32),calls=calls,
  opaque_inner_tail='0x'+d[cursor:auth].hex(),authorization='0x'+authorization.hex(),
  execution_verified=False,scope_verified=False)

def main():
 rows=[]
 for tx in map(json.loads,Path('reports/amm/delegated-router-txs.jsonl').read_text().splitlines()):
  if tx['data'].startswith('0xc3c16ee4'):rows.append(dict(tx=tx['tx'],plan=inspect(tx['data'])))
 Path('reports/amm/delegated-batch-envelope.json').write_text(json.dumps(dict(transactions=rows,caveat='Structural extraction only. Opaque authorization and nested router semantics remain unresolved.'),indent=2)+'\n')
 for row in rows:print(row['tx'],[(c['target'],c['data'][:10],len(c['data'])//2-1) for c in row['plan']['calls']])
if __name__=='__main__':main()
