"""Synthetic V3 research runtime: fixed slot0, real router callback, fixed deltas.
Never a production pool implementation or numerical swap simulator.
"""

def runtime(callback_target, slot0, amount0, amount1):
    word = lambda n: (n % (1 << 256)).to_bytes(32, 'big')
    payload = bytes.fromhex('fa461e33') + word(amount0) + word(amount1) + word(96) + word(0)
    values = {'slot0_data': bytes.fromhex(slot0.removeprefix('0x')),
              'callback_data': payload, 'deltas': word(amount0)+word(amount1)}
    code = bytearray(); labels = {}; fixups = []
    def op(*values): code.extend(values)
    def push(n, size=None):
        size = size or max(1, (n.bit_length()+7)//8)
        op(0x5f+size); code.extend(n.to_bytes(size, 'big'))
    def ref(name):
        op(0x61); fixups.append((len(code), name)); code.extend(bytes(2))
    def label(name): labels[name] = len(code); op(0x5b)
    def copy(name):
        push(len(values[name])); ref(name); push(0); op(0x39)
    def ret(name):
        copy(name); push(len(values[name])); push(0); op(0xf3)
    push(0); op(0x35); push(224); op(0x1c); push(0x128acb08, 4); op(0x14); ref('swap'); op(0x57)
    push(0); op(0x35); push(224); op(0x1c); push(0x3850c7bd, 4); op(0x14); ref('slot0'); op(0x57)
    push(0); push(0); op(0xfd)
    label('slot0'); ret('slot0_data')
    label('swap'); copy('callback_data')
    push(0); push(0); push(len(payload)); push(0); push(0); push(int(callback_target, 16), 20); op(0x5a, 0xf1, 0x15)
    ref('fail'); op(0x57)
    ret('deltas')
    label('fail'); op(0x3d); push(0); push(0); op(0x3e, 0x3d); push(0); op(0xfd)
    for name, data in values.items():
        labels[name] = len(code); code.extend(data)
    for offset, name in fixups:
        code[offset:offset+2] = labels[name].to_bytes(2, 'big')
    return '0x'+code.hex()
