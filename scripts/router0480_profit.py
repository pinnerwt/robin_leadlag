"""Observed terminal a3 start/end inventory increment condition."""
from router0480_guards import inspect

def condition(calldata):
 raw=bytes.fromhex(calldata.removeprefix('0x'));p=inspect(calldata);offset=p['offsets'][-1];c=raw[offset:]
 if len(c)!=5 or c[0]!=0xa3:raise ValueError('unverified terminal condition')
 tokenoff=int.from_bytes(c[1:3],'big');minimumoff=int.from_bytes(c[3:5],'big');end=2+2*raw[0]
 if not end<=tokenoff<=p['offsets'][0]-20 or not end<=minimumoff<=p['offsets'][0]-16:raise ValueError('terminal operand bounds')
 return dict(token='0x'+raw[tokenoff:tokenoff+20].hex(),minimum=int.from_bytes(raw[minimumoff:minimumoff+16],'big'))
def evaluate(calldata,start,end):
 c=condition(calldata)
 if any(type(x) is not int or not 0<=x<1<<256 for x in (start,end)):raise ValueError('inventory bounds')
 required=start+c['minimum']
 return dict(**c,required=required,passes=required<1<<256 and end>=required)
