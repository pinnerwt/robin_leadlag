"""Pure packed-slot updates for four observed A3D child config setters.
Caller authorization is assumed. Validate the pinned child target/code outside
this decoder. Parent forwarding/upgrades and arbitrary writers remain uncovered.
"""
CHILD='0xe3c90972c6462bb4a4c75cf49dcf4189c5b42880'


def update(calldata, storage):
    raw=bytes.fromhex(calldata.removeprefix('0x')); selector=raw[:4].hex()
    shapes={'da0dfdc3':[88,88], '7098d028':[8,1,96,96,32],
            '875260d6':[40,40,64,16], '17a41e5a':[16,16,88,88]}
    widths=shapes.get(selector)
    if widths is None or len(raw)!=4+32*len(widths):
        raise ValueError('unknown setter or invalid ABI length')
    values=[int.from_bytes(raw[4+32*i:36+32*i],'big') for i in range(len(widths))]
    if any(v>=1<<w for v,w in zip(values,widths)):
        raise ValueError('setter ABI width')
    if selector=='7098d028':
        index,enabled,cap0,cap1,gas=values
        if index>8 or not cap0 or not cap1 or not 50000<=gas<=2000000:
            raise ValueError('unsupported pool config range')
        slot=hex(index); fields=[(0,8,enabled),(8,96,cap0),(104,96,cap1),(200,32,gas)]
    elif selector=='875260d6':
        low,high,gas,parameter=values
        if not 0<low<=high or not gas or not 1<=parameter<=100:
            raise ValueError('unsupported global config range')
        slot='0x9'; fields=list(zip([0,40,80,144],widths,values))
    elif selector=='17a41e5a':
        first,second,_,_=values
        if not 1<=first<=6500 or not 1<=second<=7500:
            raise ValueError('unsupported slot10 config range')
        slot='0xa'; fields=list(zip([0,16,32,120],widths,values))
    else:
        slot='0xa'; fields=list(zip([32,120],widths,values))
    if slot not in storage:raise ValueError('missing initial setting slot')
    old=storage[slot]; old=int(old,16) if isinstance(old,str) else old
    if type(old) is not int or not 0<=old<1<<256:raise ValueError('invalid setting word')
    if selector=='da0dfdc3' and any(v>((old>>offset)&((1<<width)-1)) for offset,width,v in fields):
        raise ValueError('limited setter may only reduce current caps')
    value=old
    for offset,width,field in fields:
        mask=((1<<width)-1)<<offset
        value=(value&~mask)|(field<<offset)
    return dict(slot=slot,before=old,after=value,selector='0x'+selector,authorization_assumed=True)

PARENT='0x000000000000a3d2e62895f55d5a4304d2f3c998'


def transaction_update(to, calldata, storage, parent_state=None):
    """Direct child setter or canonical zero-value parent execute wrapper."""
    target=(to or '').lower()
    if target==CHILD:
        return dict(update(calldata,storage),path=[CHILD])
    if target!=PARENT:raise ValueError('unknown settings transaction target')
    raw=bytes.fromhex(calldata.removeprefix('0x'))
    if raw[:4].hex()!='b61d27f6' or len(raw)<132:
        raise ValueError('unknown parent settings wrapper')
    words=[int.from_bytes(raw[4+32*i:36+32*i],'big') for i in range(4)]
    child,value,offset,size=words
    if child!=int(CHILD,16) or value or offset!=96:
        raise ValueError('unverified execute target/value/offset')
    padded=(size+31)//32*32
    if size<4 or len(raw)!=132+padded or any(raw[132+size:]):
        raise ValueError('invalid execute payload framing')
    if parent_state is None:
        raise ValueError('parent postlude balance state required')
    postlude=parent_postlude(**parent_state)
    return dict(update('0x'+raw[132:132+size].hex(),storage),path=[PARENT,CHILD],parent_postlude=postlude)


def parent_postlude(slot0, tier2_balance, tier1_balance):
    """Observed post-execute token-balance tier update; preserves other slot bits."""
    slot0=int(slot0,16) if isinstance(slot0,str) else slot0
    if any(type(v) is not int or not 0<=v<1<<256 for v in (slot0,tier2_balance,tier1_balance)):
        raise ValueError('parent postlude state bounds')
    tier=2 if tier2_balance else 1 if tier1_balance else 0
    after=(slot0&~(255<<168))|(tier<<168)
    return dict(slot='0x0',before=slot0,after=after,tier=tier,write_required=slot0!=after)


def executor_update(calldata, slot0, known_child_code_hash=None):
    """Decode 63f8683b executor replacement; flag unsafe reuse of current decoder.

    The hash in calldata is an expected code hash, not proof of downloaded code.
    New addresses require initialization even if their bytecode hash is identical.
    """
    raw=bytes.fromhex(calldata.removeprefix('0x'))
    if len(raw)!=68 or raw[:4].hex()!='63f8683b':
        raise ValueError('unsupported executor setter framing')
    address=int.from_bytes(raw[4:36],'big'); expected_hash='0x'+raw[36:68].hex()
    if address>=1<<160 or address==int(PARENT,16):raise ValueError('invalid executor address')
    slot0=int(slot0,16) if isinstance(slot0,str) else slot0
    if type(slot0) is not int or not 0<=slot0<1<<256:raise ValueError('invalid parent slot0')
    paused=bool((slot0>>160)&255) or address==0
    after=(slot0&~((1<<168)-1))|address|(int(paused)<<160)
    target='0x'+address.to_bytes(20,'big').hex()
    compatible=(not paused and target==CHILD and known_child_code_hash is not None
                and expected_hash==known_child_code_hash.lower())
    return dict(slot='0x0',before=slot0,after=after,executor=target,paused=paused,
                expected_code_hash=expected_hash,requires_reinitialization=not compatible,
                authorization_and_success_assumed=True)
