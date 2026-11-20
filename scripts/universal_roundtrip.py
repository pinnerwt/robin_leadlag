"""Verified structural plan for wrap/V3/V4/V3/unwrap; state needed for amounts."""
from v3_calldata import word,blob,array,path,address
from universal_v4_intent import inspect
from v4_v3_bridge import WETH

def plan(calldata):
 raw=bytes.fromhex(calldata.removeprefix('0x'))
 if raw[:4].hex()!='3593564c':raise ValueError('Universal selector')
 d=raw[4:];commands=blob(d,word(d,0));inputs=array(d,word(d,1))
 if commands!=b'\x0b\x00\x10\x00\x0c' or len(inputs)!=5:raise ValueError('roundtrip sequence')
 wrap,first,v4,last,unwrap=inputs;op=inspect(v4)
 if len(wrap)!=64 or word(wrap,0)!=2 or not 0<word(wrap,1)<1<<255:raise ValueError('wrap mode')
 if len(unwrap)!=64 or word(unwrap,0)!=1 or word(unwrap,1)!=0:raise ValueError('unwrap mode')
 if blob(v4,word(v4,0))!=b'\x06\x0b\x0f' or op['zero']:raise ValueError('V4 branch')
 args=array(v4,word(v4,1));settle,take=args[1:]
 if len(settle)!=96 or address(word(settle,0))!=op['currency1'] or word(settle,1) or word(settle,2):raise ValueError('router-funded V4 settlement')
 if len(take)!=64 or address(word(take,0))!=op['currency0'] or word(take,1):raise ValueError('V4 take-all to user')
 hops=[]
 for b in (first,last):
  if len(b)!=256 or word(b,0)!=2 or word(b,1)!=1<<255 or word(b,3)!=160 or word(b,4)!=0:raise ValueError('V3 balance mode')
  h=path(blob(b,160))
  if len(h)!=1:raise ValueError('multihop V3')
  hops.append(h[0])
 if hops[0][:2]!=(WETH,op['currency1']) or hops[1][:2]!=(op['currency1'],WETH) or hops[0][2]!=hops[1][2]:raise ValueError('roundtrip token path')
 return dict(wrap_amount=word(wrap,1),v4=op,v3_fee=hops[0][2],
             final_input_source='router USDG after first V3 minus actual V4 input',
             v4_output_recipient='transaction sender',state_complete=False)
