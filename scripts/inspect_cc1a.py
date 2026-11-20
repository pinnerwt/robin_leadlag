"""Research framing only: not an executable route/state decoder.

Table and compressed values from bytecode PCs 0x6bd7 and 0x7d1f.
No log-derived amounts, RPC, or inferred intermediate swap amounts.
"""
import argparse
import json
from pathlib import Path

LENGTH_TABLE = int('081c1807161703060f061717020216021e1e1716161702160208191c16021600', 16)
ADDRESS = '0xcc1ae96cd8479f896a8dba85eab09a694b929b6c'


def inspect(data):
    raw = bytes.fromhex(data.removeprefix('0x'))
    if len(raw) < 27 or raw[:4] != bytes.fromhex('00000001'):
        raise ValueError('unsupported header')
    count = raw[11] & 15
    if count < 2:
        raise ValueError('token count not verified')
    cursor = 27 + 20 * count
    if cursor > len(raw):
        raise ValueError('truncated tokens')
    tokens = ['0x' + raw[i:i+20].hex() for i in range(27, cursor, 20)]
    records = []
    for index in range(count):
        if cursor >= len(raw):
            raise ValueError('truncated route')
        opcode = raw[cursor]
        body_size = ((LENGTH_TABLE >> (8 * opcode)) & 255) - 1
        if body_size < 1:
            raise ValueError('unknown route opcode')
        end = cursor + body_size + 6
        if end > len(raw):
            raise ValueError('truncated route value')
        exponent = raw[cursor + body_size]
        mantissa = int.from_bytes(raw[cursor+body_size+1:end], 'big')
        # EVM SHL discards overflow; this field is NOT necessarily swap input.
        value = (mantissa << exponent) & ((1 << 256) - 1)
        records.append(dict(index=index, offset=cursor, opcode=opcode,
                            body=raw[cursor:cursor+body_size].hex(),
                            exponent=exponent, mantissa=mantissa, value=value))
        cursor = end
    if len(raw) - cursor != 6 * count - 3:
        raise ValueError('unverified footer layout')
    return dict(tokens=tokens, initial_amount=int.from_bytes(raw[12:21], 'big'),
                flags=raw[10], records=records, footer_offset=cursor,
                footer=raw[cursor:].hex(), executable=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--corpus', default='reports/amm/optimistic-target-corpus.jsonl')
    ap.add_argument('--output', default='reports/amm/routercc1-framing.json')
    args = ap.parse_args()
    rows = []
    for line in Path(args.corpus).read_text().splitlines():
        tx = json.loads(line)['tx']
        if (tx['to'] or '').lower() == ADDRESS:
            rows.append(dict(tx=tx['tx'], **inspect(tx['data'])))
    Path(args.output).write_text(json.dumps(dict(status='research framing, not swap decoder', rows=rows), indent=2)+'\n')
    print(f'{len(rows)} transactions framed; no production coverage change')


if __name__ == '__main__':
    main()
