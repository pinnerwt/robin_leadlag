"""Pure index4 fee arithmetic for the verified zero-flags config branch.

Inputs must come from local pool observations/configuration. This does not update
an observation ring or infer absent cache storage. Caller profiles are explicit.
"""
from v3_state import MIN_TICK,MAX_TICK

def integer(value,lower,upper,name):
    if type(value) is not int or not lower<=value<=upper:
        raise ValueError('invalid '+name)
    return value

def cached_fee(value):
    """Explicit stored word only: zero means compute, never means free swap."""
    integer(value,0,999999,'fee cache')
    return value or None

def undiscounted_fee(config,tick,cumulative_old,cumulative_now,window_seconds):
    integer(config,0,(1<<256)-1,'fee config')
    if config>>112:raise ValueError('unverified fee config flags')
    minimum=config&((1<<24)-1);maximum=config>>24&((1<<24)-1)
    slope=config>>48&((1<<64)-1)
    if not 0<=minimum<=maximum<1000000:raise ValueError('invalid fee range')
    integer(tick,MIN_TICK,MAX_TICK,'tick')
    integer(window_seconds,1,(1<<32)-1,'observation window')
    for value in (cumulative_old,cumulative_now):integer(value,-(1<<55),(1<<55)-1,'tick cumulative')
    difference=cumulative_now-cumulative_old
    if not -(1<<55)<=difference<(1<<55):raise ValueError('unverified cumulative wrap')
    mean=difference//window_seconds # floor, including negative nonintegral mean
    if not MIN_TICK<=mean<=MAX_TICK:raise ValueError('invalid mean tick')
    deviation=abs(tick-mean)
    return min(maximum,minimum+slope*deviation//1000000)

def profile_discount(word,pool_word=None):
    """Resolve one address's packed mapping2 profile for a specified pool."""
    integer(word,0,(1<<256)-1,'caller profile')
    enabled=word&255;global_rate=word>>8&((1<<24)-1)
    if enabled not in (0,1):raise ValueError('unverified caller profile flag')
    integer(global_rate,0,1000000,'global discount')
    if enabled:
        integer(pool_word,0,(1<<256)-1,'pool discount storage')
        rate=pool_word&((1<<24)-1);integer(rate,0,1000000,'pool discount')
        if rate:return rate
    return global_rate

def caller_discount(caller_word,origin_word,*,caller_pool_word=None,origin_pool_word=None,same_origin=False):
    """Caller nonzero profile wins; otherwise use origin. Inputs are known state."""
    if type(same_origin) is not bool:raise ValueError('origin equality')
    if not same_origin:
        rate=profile_discount(caller_word,caller_pool_word)
        if rate:return rate
    return profile_discount(origin_word,origin_pool_word)

def discounted_fee(base_fee,discount_ppm):
    integer(base_fee,0,999999,'base fee');integer(discount_ppm,0,1000000,'caller discount')
    return (base_fee*(1000000-discount_ppm)+999999)//1000000
