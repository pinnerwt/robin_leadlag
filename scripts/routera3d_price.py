"""Research decoder for A3D's observed price, route mask and V3 bounds.
Not a complete route/amount decoder. Configuration is explicit; no RPC or logs.
"""
from math import isqrt

PRICE_XOR = 0x8bb8f78e21

def price_word(calldata):
    raw = bytes.fromhex(calldata.removeprefix('0x'))
    if len(raw) < 13:
        raise ValueError('truncated A3D price header')
    if raw[0] & 0xf0 not in (0x40, 0xe0):
        raise ValueError('unverified A3D mode')
    value = int.from_bytes(raw[1:6], 'big')
    reverse = 0
    for _ in range(40):
        reverse = (reverse << 1) | (value & 1)
        value >>= 1
    return reverse ^ PRICE_XOR


def reverse_v3_limit(price, price_discount, pool_fee, limit_padding):
    """Observed USDG-input/WETH-output bound, two floor square roots.

    price is decoded integer; discount units 1e-5; fee/padding units 1e-6.
    Other directions, route modes and inventory sizing remain unimplemented.
    """
    if not 0 < price < 1 << 40:
        raise ValueError('price bounds')
    if not 0 <= price_discount < 100000 or not 0 <= pool_fee < 1000000 or not 0 <= limit_padding < 1000000:
        raise ValueError('fee/discount bounds')
    adjusted = price * (100000 - price_discount) // 100000
    target = isqrt((adjusted << 192) // 10**18)
    multiplier = isqrt(((1000000 - pool_fee) << 192) // (1000000 + limit_padding))
    return target * multiplier >> 96


def first_reverse_discount(calldata):
    raw = bytes.fromhex(calldata.removeprefix('0x'))
    if len(raw) < 15 or raw[13] != 0x09 or not 128 <= raw[14] <= 255:
        raise ValueError('unverified first reverse route descriptor')
    return 256 - raw[14]


def input_cap(calldata):
    """Observed normalized 17-bit mantissa / 7-bit exponent USDG budget cap."""
    raw = bytes.fromhex(calldata.removeprefix('0x'))
    # Keep this helper within the observed header modes as price_word does.
    price_word(calldata)
    packed = int.from_bytes(raw[6:9], 'big')
    mantissa, exponent = packed >> 7, packed & 127
    if not 65536 <= mantissa <= 131071 or exponent > 110:
        raise ValueError('unverified or non-normalized input cap')
    return mantissa << exponent


def route_fields(calldata):
    """Decode observed framing and two-bit side mask, not a full route plan."""
    raw = bytes.fromhex(calldata.removeprefix('0x'))
    price = price_word(calldata)
    mode, count = raw[0] & 0xf0, raw[0] & 15
    if not 1 <= count <= 8:
        raise ValueError('route count')
    offset = 13 + count * 2
    extra_size=0
    if mode==0x40:
        if len(raw)<offset:raise ValueError('truncated route descriptors')
        special=[raw[13+2*i]>>4 for i in range(count) if raw[13+2*i]>>4 in (4,7)]
        if special not in ([],[4]):raise ValueError('unverified mode40 special-route framing')
        extra_size=2 if special else 0
    expected = offset + 2 + extra_size
    if len(raw) != expected:
        raise ValueError('route envelope length')
    mask = int.from_bytes(raw[offset:offset+2], 'big')
    if mask >> (2 * count):
        raise ValueError('unused direction bits')
    routes = []
    for i in range(count):
        descriptor, adjustment = raw[13+2*i:15+2*i]
        side = (mask >> (2*i)) & 3
        if side not in (1, 2):
            raise ValueError('unverified side mask')
        routes.append(dict(index=descriptor >> 4, flags=descriptor & 15,
                           adjustment=adjustment if adjustment < 128 else adjustment-256,
                           side=side))
    return dict(price=price, cap=input_cap(calldata), mode=mode, routes=routes,
                extra=raw[offset+2:].hex(), state_complete=False)


def forward_v3_limit(price, price_discount, pool_fee, limit_padding):
    """Observed WETH-input/USDG-output bound: ceil sqrt followed by ceil div."""
    # Apply the same supported parameter domain as the reverse helper.
    reverse_v3_limit(price, price_discount, pool_fee, limit_padding)
    adjusted = price * (100000 - price_discount) // 100000
    squared = (adjusted << 192) // 10**18
    target = isqrt(squared)
    target += int(target * target < squared)
    multiplier = isqrt(((1000000 - pool_fee) << 192) // (1000000 + limit_padding))
    return ((target << 96) + multiplier - 1) // multiplier


def forward_input_amount(calldata, weth_inventory):
    """Tested first-route WETH sell budget under the research configuration.

    The serialized budget is in raw USDG units, not raw WETH. Other config
    caps, transaction gating and settlement are outside this arithmetic helper.
    """
    fields = route_fields(calldata)
    first = fields['routes'][0]
    if first['index'] != 0 or first['flags'] != 9 or first['side'] != 2 or first['adjustment'] >= 0:
        raise ValueError('unverified first sell route')
    if type(weth_inventory) is not int or not 0 <= weth_inventory < 1 << 256:
        raise ValueError('inventory bounds')
    adjusted = fields['price'] * (100000 + first['adjustment']) // 100000
    if adjusted == 0:
        raise ValueError('zero adjusted price')
    return min(weth_inventory, fields['cap'] * 10**18 // adjusted)


def block_window(calldata,block,slot9):
    """Observed compressed header target block and configured lookahead gate."""
    route_fields(calldata) # require a supported, complete envelope
    if type(block) is not int or not 0<=block<1<<256:raise ValueError('block bounds')
    if type(slot9) is not int or not 0<=slot9<1<<256:raise ValueError('router setting word')
    raw=bytes.fromhex(calldata.removeprefix('0x'))
    target=int.from_bytes(raw[9:13],'big');future=(slot9>>144)&0xffff
    return dict(target_block=target,max_future_blocks=future,
                valid=block<=target and target-block<=future)


def mode40_limit_fee_hint(calldata):
    """Observed one-index4 tail: router limit fee hint, not actual pool fee.

    Zero means the router takes its getter-based fallback; caller must resolve
    that dependency locally instead of treating zero as a free swap.
    """
    plan=route_fields(calldata)
    if plan['mode']!=0x40 or len(plan['extra'])!=4 or sum(r['index']==4 for r in plan['routes'])!=1:
        raise ValueError('unverified mode40 fee hint')
    value=int(plan['extra'],16)
    return dict(limit_fee_hint_ppm=value,fallback_required=value==0)
