"""Verified arithmetic branch of index-6 hook; not a complete hook reducer."""
Q48=1<<48
Q96=1<<96


def same_block_reverse_fee(reference_sqrt,current_sqrt,base_fee,coefficient,increment_cap):
    """Reverse swap, unchanged reference block, false reference direction flag.

    Caller must establish these branch predicates from hook state. Crossing a
    block or moving below the reference requires a different branch.
    """
    if any(type(x) is not int for x in (reference_sqrt,current_sqrt,base_fee,coefficient,increment_cap)):
        raise ValueError('integer hook inputs required')
    if not 0<reference_sqrt<=current_sqrt<1<<160:
        raise ValueError('unverified price direction')
    if any(not 0<=x<1<<24 for x in (base_fee,coefficient,increment_cap)):
        raise ValueError('hook config width')
    ratio=reference_sqrt*Q48//current_sqrt
    squared=ratio*ratio
    if not squared:raise ValueError('unverified extreme price move')
    numerator=(Q96-squared)*coefficient
    increment=(numerator+squared-1)//squared
    fee=base_fee+min(increment,increment_cap)
    if fee>=1000000:raise ValueError('unverified total fee')
    return fee


def small_upward_block_transition(state_word,current_sqrt,current_block):
    """Verified default-profile transition from base fee 40 with zero carry.

    Requires the pinned default config externally. Larger moves populate an
    additional carry field; reject them until that branch is reconstructed.
    """
    if type(state_word) is not int or not 0<=state_word<1<<256:
        raise ValueError('hook state word')
    block=state_word&((1<<40)-1);reference=(state_word>>40)&((1<<160)-1)
    base=(state_word>>200)&0xffffff;carry=(state_word>>224)&0xffffff;flag=(state_word>>248)&255
    if base!=40 or carry or flag or state_word>>256:
        raise ValueError('unverified initial hook profile')
    if type(current_block) is not int or not block<current_block<1<<40:
        raise ValueError('new block required')
    fee=same_block_reverse_fee(reference,current_sqrt,base,1000000,0xffffff)
    if fee>80:raise ValueError('large move carry branch unresolved')
    after=current_block|(current_sqrt<<40)|(fee<<200)|(int(current_sqrt>reference)<<248)
    return dict(fee=fee,after=after)


def default_upward_block_transition(state_word,current_sqrt,current_block):
    """Default-config upward transition from base40/carry0/direction=false.

    Explicitly limited initial domain; not a general sequential hook reducer.
    """
    if type(state_word) is not int or not 0<=state_word<1<<256:
        raise ValueError('hook state word')
    block=state_word&((1<<40)-1);reference=(state_word>>40)&((1<<160)-1)
    if state_word>>200 !=40:
        raise ValueError('unverified initial hook profile')
    if type(current_block) is not int or not block<current_block<1<<40:
        raise ValueError('new block required')
    raw_fee=same_block_reverse_fee(reference,current_sqrt,40,1000000,0xffffff)
    fee=40+min(raw_fee-40,40)
    ratio=reference*Q48//current_sqrt;squared=ratio*ratio;difference=Q96-squared
    carry=0
    if difference*1000000>=100*squared:
        carry=(fee-40)+(difference*500000+squared-1)//squared
    if current_block-block>2:carry=0
    if carry>=1<<24:raise ValueError('carry width')
    after=current_block|(current_sqrt<<40)|(fee<<200)|(carry<<224)|(int(current_sqrt>reference)<<248)
    return dict(fee=fee,carry=carry,after=after)


def default_block_transition(state_word,current_sqrt,current_block):
    """Default-config cross-block reference update; reverse swap fee only.

    Research branch: caller must pin the default ten-field hook config.
    """
    if type(state_word) is not int or not 0<=state_word<1<<256:
        raise ValueError('hook state word')
    block=state_word&((1<<40)-1);reference=(state_word>>40)&((1<<160)-1)
    base=(state_word>>200)&0xffffff;flag=(state_word>>248)&255
    if not 40<=base<=160 or flag not in (0,1):raise ValueError('unverified hook profile')
    if type(current_block) is not int or not block<current_block<1<<40:
        raise ValueError('new block required')
    if type(current_sqrt) is not int or not 0<current_sqrt<1<<160 or not reference:
        raise ValueError('sqrt bounds')
    up=current_sqrt>reference
    ratio=min(reference,current_sqrt)*Q48//max(reference,current_sqrt)
    squared=ratio*ratio
    if not squared:raise ValueError('extreme price movement')
    difference=Q96-squared
    denominator=squared if up else Q96
    increment=min((difference*1000000+denominator-1)//denominator,40)
    next_base=min(160,base+increment) if up else max(40,base-increment)
    carry=0
    if difference*1000000>=100*denominator:
        carry=abs(next_base-base)+(difference*500000+denominator-1)//denominator
    if current_block-block>2:carry=0
    if carry>=1<<24:raise ValueError('carry width')
    fee=next_base if up else next_base+carry
    if fee>=1000000:raise ValueError('unverified fee range')
    after=current_block|(current_sqrt<<40)|(next_base<<200)|(carry<<224)|(int(up)<<248)
    return dict(fee=fee,base_fee=next_base,carry=carry,after=after)

DEFAULT_CONFIG=int('640f42400000640000a00000280f42400000323d090007a1200000c8',16)


def reverse_update(state_word,config_word,current_sqrt,current_block):
    """Research default-config reverse beforeSwap fee and reference transition."""
    if type(config_word) is not int or config_word!=DEFAULT_CONFIG:
        raise ValueError('unverified hook config')
    if type(state_word) is not int or not 0<=state_word<1<<256:
        raise ValueError('hook state word')
    block=state_word&((1<<40)-1);reference=(state_word>>40)&((1<<160)-1)
    base=(state_word>>200)&0xffffff;carry=(state_word>>224)&0xffffff;flag=state_word>>248
    if not 40<=base<=160 or flag not in (0,1):raise ValueError('unverified hook profile')
    if type(current_block) is not int or not block<=current_block<1<<40:
        raise ValueError('hook block order')
    if type(current_sqrt) is not int or not 0<current_sqrt<1<<160 or not reference:
        raise ValueError('sqrt bounds')
    if current_block>block:
        result=default_block_transition(state_word,current_sqrt,current_block)
        return dict(result,write_required=True)
    fee=base+(carry if not flag else 0)
    if current_sqrt>=reference:
        fee=same_block_reverse_fee(reference,current_sqrt,fee,4000000,50)
    else:
        ratio=current_sqrt*Q48//reference;squared=ratio*ratio
        fee+=((Q96-squared)*500000+Q96-1)//Q96
    if fee>=1000000:raise ValueError('unverified fee range')
    return dict(fee=fee,base_fee=base,carry=carry,after=state_word,write_required=False)


def forward_same_block_fee(state_word,config_word,current_sqrt,current_block):
    """Default-config forward fee branch; reference state remains unchanged."""
    # Reuse domain checks; discard the reverse quote.
    reverse_update(state_word,config_word,current_sqrt,current_block)
    block=state_word&((1<<40)-1)
    if current_block!=block:raise ValueError('forward cross-block branch unverified')
    reference=(state_word>>40)&((1<<160)-1);base=(state_word>>200)&0xffffff
    carry=(state_word>>224)&0xffffff;flag=state_word>>248
    fee=200-base+(carry if flag else 0)
    if current_sqrt>=reference:
        ratio=reference*Q48//current_sqrt;squared=ratio*ratio
        if not squared:raise ValueError('extreme price movement')
        fee+=((Q96-squared)*500000+squared-1)//squared
    else:
        ratio=current_sqrt*Q48//reference;squared=ratio*ratio
        fee+=min(((Q96-squared)*4000000+Q96-1)//Q96,50)
    if fee>=1000000:raise ValueError('unverified fee range')
    return dict(fee=fee,after=state_word,write_required=False)


def forward_update(state_word,config_word,current_sqrt,current_block):
    """Research default-config forward beforeSwap quote/reference update."""
    transition=reverse_update(state_word,config_word,current_sqrt,current_block)
    result=forward_same_block_fee(transition['after'],config_word,current_sqrt,current_block)
    return dict(result,write_required=transition['write_required'])


def directional_fees(state_word,config_word,current_sqrt,current_block):
    """Independent counterfactual bid/ask fees from one immutable snapshot.

    Quoting both sides must not apply one hypothetical trade to the other.
    """
    reverse=reverse_update(state_word,config_word,current_sqrt,current_block)
    forward=forward_update(state_word,config_word,current_sqrt,current_block)
    if reverse['after']!=forward['after']:raise ValueError('direction-dependent reference update')
    return dict(buy_fee_ppm=reverse['fee'],sell_fee_ppm=forward['fee'],
                reference_after=reverse['after'],write_required=reverse['write_required'])
