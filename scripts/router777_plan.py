"""Strict observed two-action 777 framing and exact Aqua primary-call rebuild.

No state/amount inference from logs; callback settlement remains separate work.
"""
from v3_calldata import word,blob,address
from aqua_program import parse
AQUA='0x111111338c5091e8440b67b168bae16a668ac0de'
def enc(n):return n.to_bytes(32,'big')
def dynamic(b):return enc(len(b))+b+bytes((-len(b))%32)

def plan(calldata):
 raw=bytes.fromhex(calldata.removeprefix('0x'))
 if raw[:4].hex()!='3fa72595':raise ValueError('777 selector')
 d=raw[4:]
 if word(d,0)!=32 or len(d)!=1632:raise ValueError('777 envelope')
 outer=blob(d,32)
 if len(outer)!=1568 or word(outer,0)!=32:raise ValueError('777 tuple envelope')
 t=outer[32:]
 if [word(t,i) for i in (0,1,3,4,5)]!=[2,192,1,0,1504] or word(t[1504:],0)!=0:
  raise ValueError('777 root mode')
 a=t[192:]
 if [word(a,i) for i in range(3)]!=[2,64,800]:raise ValueError('777 action table')
 first=a[96:];second=a[832:]
 if [word(first,i) for i in (0,1,5,6)]!=[0,0,0,224]:raise ValueError('777 primary action')
 tin,tout=address(word(first,2)),address(word(first,3));amount=word(first,4)
 if not 0<amount<1<<255 or word(t,2)!=word(first,2):raise ValueError('777 primary amount/token')
 extra=blob(first,224)
 if len(extra)!=480 or word(extra,0)!=32 or word(extra,1)!=160 or address(word(extra,2))!=AQUA:
  raise ValueError('777 primary descriptor')
 desc=extra[192:]
 if word(desc,1)!=1<<254 or word(desc,2)!=96:raise ValueError('777 maker traits')
 parse(blob(desc,96))
 if [word(second,i) for i in (0,1,4,5,6)]!=[1,1,0,amount,224] or word(second,2)!=word(first,3) or word(second,3)!=word(first,2):
  raise ValueError('777 reverse action')
 path=blob(second,224)
 if len(path)!=224 or [word(path,i) for i in (0,1,2,5)]!=[64,160,2,1] or word(path,3)!=word(first,3) or word(path,4)!=word(first,2):
  raise ValueError('777 reverse path')
 pool=address(word(path,6))
 # Verified fixed-size callback wrapper: three callback lengths, flags, then
 # ABI encoding of (action index 0, original route bytes).
 prefix=bytes.fromhex('06800680068000000000000000000000000000000005')
 tail=prefix+enc(0)+enc(64)+dynamic(outer)
 primary='0xf4d2d412'+(enc(160)+enc(int(tin,16))+enc(int(tout,16))+enc(amount)+enc(448)+desc+dynamic(tail)).hex()
 return dict(primary=primary,maker=address(word(desc,0)),token_in=tin,token_out=tout,amount=amount,
             pool=pool,reverse_minimum_output=amount,state_complete=False)


def bind_callback(route,aqua_received,pools):
 """Verified action 1 uses token balance delta, not entire router inventory."""
 if not 0<aqua_received<1<<255:raise ValueError('777 callback input bounds')
 pool=route['pool']
 if pool not in pools:raise ValueError('777 upstream Aqua remains relevant despite unrecorded callback')
 tokens=pools[pool]['tokens']
 if set(tokens)!={route['token_in'],route['token_out']}:raise ValueError('777 pool token mismatch')
 zero=tokens[0]==route['token_out']
 from v3_state import MIN_SQRT,MAX_SQRT
 return dict(kind='swap',pool=pool,zero=zero,amount=aqua_received,limit=MIN_SQRT+1 if zero else MAX_SQRT-1,
             constraint=dict(kind='min_out',amount=route['reverse_minimum_output']),
             coverage_note='balance-delta callback; full Aqua settlement not modeled')


def allocation_candidate(calldata,packed_in,packed_out,pools):
 """Use common full-input repayment arithmetic with balance-delta callback."""
 from aqua_program import transition_exact_input
 r=plan(calldata);data=bytes.fromhex(r['primary'][10:]);desc=data[word(data,0):]
 candidate=transition_exact_input(blob(desc,word(desc,2)),r['token_in'],r['token_out'],packed_in,packed_out,r['amount'])
 return dict(candidate,route=r,operation=bind_callback(r,candidate['quote']['amount_out'],pools),state_complete=False)
