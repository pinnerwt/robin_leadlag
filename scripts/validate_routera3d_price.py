"""Compare local price decoder against research bytecode call arguments."""
import json
from pathlib import Path
from routera3d_price import price_word, reverse_v3_limit, first_reverse_discount
from v3_calldata import word, signed


def main():
    txs = {r['tx']['tx']: r['tx'] for r in map(json.loads, open('reports/amm/optimistic-target-corpus.jsonl'))}
    cases = []; price_matches = 0
    for row in map(json.loads, open('reports/amm/routera3d-math-prefix.jsonl')):
        decoded_price = price_word(txs[row['tx']]['data'])
        assert any(op['pc'] == 13773 and int(op['a']) == decoded_price for op in row['math_ops'])
        price_matches += 1
        for call in row['calls']:
            if not call['data'].startswith('0x128acb08'):
                continue
            d = bytes.fromhex(call['data'][10:]); tx = txs[row['tx']]
            assert call['to'] == '0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca'
            assert word(d, 1) == 0
            price = price_word(tx['data'])
            discount = first_reverse_discount(tx['data'])
            bound = reverse_v3_limit(price, discount, 100, 10)
            assert bound == word(d, 3), (row['tx'], bound, word(d, 3))
            assert any(op['pc'] == 13773 and int(op['a']) == price for op in row['math_ops'])
            cases.append(dict(tx=row['tx'], calldata=tx['data'], price=price, discount=discount, limit=bound,
                              amount=signed(word(d, 2))))
    assert len(cases) == 26 and price_matches == 85
    report = dict(cases=cases, matches=len(cases), price_word_matches=price_matches, caveats=[
        'Current child bytecode/config with archived pool state',
        'Synthetic router USDG inventory 1000000000000 and WETH inventory zero',
        'Only decoded price and reverse V3 limit verified; amount is inventory-dependent',
        'No full route, execution success or historical swap parity claim'])
    Path('reports/amm/routera3d-price-validation.json').write_text(json.dumps(report, indent=2)+'\n')
    Path('tests/fixtures/routera3d_price.json').write_text(json.dumps(cases, indent=2)+'\n')
    print('85 price words and 26 V3 limits match research bytecode')

if __name__ == '__main__':
    main()
