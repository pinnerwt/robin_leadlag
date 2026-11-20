"""Research-only V4 exact-input intent; custom hook pricing is unresolved."""
from v3_calldata import word,blob,array,address
from v3_state import MIN_SQRT,MAX_SQRT
MANAGER='0x8366a39cc670b4001a1121b8f6a443a643e40951'

def inspect(payload):
    commands=blob(payload,word(payload,0));args=array(payload,word(payload,1))
    if commands not in (b'\x06\x0c\x0e',b'\x06\x0b\x0f') or len(args)!=3:
        raise ValueError('unverified V4 action sequence')
    b=args[0]
    if len(b)!=384 or word(b,0)!=32 or word(b,10)!=320 or blob(b,352):
        raise ValueError('unverified V4 swap layout')
    a,c=address(word(b,1)),address(word(b,2));fee=word(b,3);spacing=word(b,4);hook=address(word(b,5))
    zero=word(b,6);amount=word(b,7)
    if int(a,16)>=int(c,16) or fee>=1<<24 or not 0<spacing<1<<23 or zero not in (0,1):raise ValueError('V4 pool key')
    if not 0<amount<1<<128 or word(b,8)>=1<<128 or word(b,9)!=0:raise ValueError('V4 amount or extra mode')
    return dict(manager=MANAGER,currency0=a,currency1=c,fee=fee,tick_spacing=spacing,hooks=hook,
                zero=bool(zero),amount=-amount,limit=MIN_SQRT+1 if zero else MAX_SQRT-1,
                minimum_output=word(b,8),state_complete=False)
