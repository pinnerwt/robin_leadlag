"""Research hub storage layout. Key derivation is for initialization, not hot path.

b00bbd10 withdrawal and 47d72768 deposit arithmetic are implemented;
full settlement and flag lifecycle are not yet covered. No RPC and no inferred defaults for missing storage.
"""
from bootstrap_state import hashhex,word as encode_word
from v3_calldata import word,blob,address
HUB='0x1111113ccf1426a8e30e2bff5e005d929bf6a90a'
AGGREGATOR='0x111111338c5091e8440b67b168bae16a668ac0de'
MASK248=(1<<248)-1

def storage_key(maker,caller,program_hash,token,hash_fn=hashhex):
    """Four nested mappings; caller is the aggregator, not the EOA sender."""
    key=hash_fn(encode_word(int(maker,16))+encode_word(0))
    for value in [int(caller,16),int(program_hash,16),int(token,16)]:
        key=hash_fn(encode_word(value)+bytes.fromhex(key[2:]))
    return key

def primary_keys(calldata,hash_fn=hashhex):
    raw=bytes.fromhex(calldata.removeprefix('0x'))
    if raw[:4].hex()!='f4d2d412':raise ValueError('unsupported hub caller')
    data=raw[4:]
    if word(data,0)!=160:raise ValueError('descriptor offset')
    desc=data[160:]
    if word(desc,2)!=96:raise ValueError('program offset')
    program=blob(desc,96)
    end=128+((len(program)+31)//32)*32
    if word(data,4)!=160+end:raise ValueError('descriptor boundary')
    maker=address(word(desc,0))
    program_hash=hash_fn(encode_word(32)+desc[:end])
    tokens=[address(word(data,i)) for i in (1,2)]
    return dict(maker=maker,caller=AGGREGATOR,program_hash=program_hash,
                token_slots={t:storage_key(maker,AGGREGATOR,program_hash,t,hash_fn) for t in tokens})

def unpack(value):
    if not 0<=value<(1<<256):raise ValueError('uint256 state bounds')
    return value>>248,value&MASK248

def withdraw(value,amount):
    flags,balance=unpack(value)
    if not 0<=amount<=MASK248 or amount>balance:raise ValueError('withdrawal overflow/underflow')
    return (flags<<248)|(balance-amount)


def deposit(value,amount):
    flags,balance=unpack(value)
    if flags in (0,255):raise ValueError('inactive deposit entry')
    if not 0<=amount<=MASK248 or balance+amount>MASK248:
        raise ValueError('deposit overflow')
    return (flags<<248)|(balance+amount)


def deposit_fields(calldata):
    """Decode push identity and amount without hashing, I/O, or subprocesses."""
    raw=bytes.fromhex(calldata.removeprefix('0x'))
    if len(raw)!=164 or raw[:4].hex()!='47d72768':
        raise ValueError('deposit ABI not verified')
    data=raw[4:]
    maker,caller,token=(address(word(data,i)) for i in (0,1,3))
    program_hash='0x'+format(word(data,2),'064x')
    amount=word(data,4)
    if amount>MASK248:raise ValueError('deposit amount width')
    return dict(maker=maker,caller=caller,program_hash=program_hash,token=token,amount=amount)


def deposit_call(calldata,hash_fn=hashhex):
    op=deposit_fields(calldata)
    return dict(op,slot=storage_key(op['maker'],op['caller'],op['program_hash'],op['token'],hash_fn))


def withdrawal_fields(calldata,caller):
    """The app namespace is the immediate hub caller, never an inferred EOA."""
    raw=bytes.fromhex(calldata.removeprefix('0x'))
    if len(raw)!=164 or raw[:4].hex()!='b00bbd10':raise ValueError('withdrawal ABI not verified')
    data=raw[4:]
    amount=word(data,3)
    if amount>MASK248:raise ValueError('withdrawal amount width')
    return dict(maker=address(word(data,0)),caller=address(int(caller,16)),
                program_hash='0x'+format(word(data,1),'064x'),token=address(word(data,2)),
                amount=amount,recipient=address(word(data,4)))
