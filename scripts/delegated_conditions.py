"""Local operation3 condition arithmetic. No I/O; other operation types reject."""
Q32=1<<32

def score(record,return_data):
 h=bytes.fromhex(record['header']);extra=bytes.fromhex(record['extra'])
 if len(h)!=6 or h[2]!=1 or h[5]!=3 or len(extra)!=8:raise ValueError('unverified condition operation')
 raw=bytes.fromhex(return_data.removeprefix('0x')) if isinstance(return_data,str) else return_data
 offset=h[1]*32
 if len(raw)<offset+32:raise ValueError('short condition return')
 observed=int.from_bytes(raw[offset:offset+32],'big')>>h[4]
 reference=record['value']
 if type(reference) is not int or not 0<=reference<1<<256:raise ValueError('condition reference bounds')
 if h[3]:
  mask=(1<<h[3])-1
  if reference&~mask:raise ValueError('reference exceeds extraction mask')
  observed&=mask
 # The deployed code rescales both operands once before subtraction/division.
 if (observed|reference)>>192:observed>>=64;reference>>=64
 magnitude=min((abs(observed-reference)<<32)//reference if reference else 1<<62,1<<62)
 ratio=-magnitude if observed<reference else magnitude
 weight=int.from_bytes(extra,'big',signed=True)
 return (weight*ratio)>>32

def evaluate(group,returns):
 if not group['flag']&128 or len(bytes.fromhex(group['prefix']))!=8:raise ValueError('unverified unweighted condition group')
 threshold=int.from_bytes(bytes.fromhex(group['prefix']),'big',signed=True)
 values=[score(r,returns[(r['target'],r['calldata'])]) for r in group['records']]
 total=sum(values)
 return dict(score=total,threshold=threshold,passes=total<=threshold,record_scores=values)
