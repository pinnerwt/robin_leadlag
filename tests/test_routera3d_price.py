import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from routera3d_price import price_word, reverse_v3_limit, first_reverse_discount, input_cap, route_fields, forward_v3_limit, forward_input_amount

class A3DPriceTest(unittest.TestCase):
    def test_research_bytecode_bounds(self):
        cases = json.loads(Path('tests/fixtures/routera3d_price.json').read_text())
        self.assertEqual(len(cases), 26)
        for c in cases:
            with self.subTest(tx=c['tx']):
                self.assertEqual(price_word(c['calldata']), c['price'])
                discount = first_reverse_discount(c['calldata'])
                self.assertEqual(discount, c['discount'])
                self.assertEqual(reverse_v3_limit(c['price'], discount, 100, 10), c['limit'])
    def test_unverified_inputs_reject(self):
        for data in ['0x', '0x'+'00'*20]:
            with self.assertRaises(ValueError): price_word(data)
        with self.assertRaises(ValueError): first_reverse_discount('0x'+'e1'+'00'*14)
        with self.assertRaises(ValueError): reverse_v3_limit(1, 100000, 100, 10)

    def test_normalized_cap_bytecode_cases(self):
        cases = json.loads(Path('tests/fixtures/routera3d_caps.json').read_text())
        self.assertEqual(len(cases), 15)
        for c in cases:
            with self.subTest(mantissa=c['mantissa'], exponent=c['exponent']):
                self.assertEqual(input_cap(c['calldata']), int(c['cap']))
                self.assertEqual(min(input_cap(c['calldata']), int(c['inventory'])), int(c['amount']))

    def test_cap_boundaries_fail_closed(self):
        reference = json.loads(Path('tests/fixtures/routera3d_caps.json').read_text())[0]
        for mantissa, exponent in [(0, 0), (65535, 0), (65536, 111)]:
            raw = bytearray.fromhex(reference['calldata'][2:])
            raw[6:9] = ((mantissa << 7) | exponent).to_bytes(3, 'big')
            with self.assertRaises(ValueError):
                input_cap('0x'+raw.hex())

    def test_route_framing_and_sell_arithmetic(self):
        fixture = json.loads(Path('tests/fixtures/routera3d_sides.json').read_text())
        self.assertEqual(len(fixture['headers']), 85)
        self.assertEqual(len(fixture['sells']), 24)
        for case in fixture['headers']:
            self.assertEqual(route_fields(case['calldata']), case['expected'])
        for case in fixture['sells']:
            fields = route_fields(case['calldata'])
            self.assertEqual(fields['routes'][0]['side'], 2)
            self.assertEqual(forward_input_amount(case['calldata'], 10**18), int(case['amount']))
            self.assertEqual(forward_v3_limit(fields['price'], -fields['routes'][0]['adjustment'], 100, 10), int(case['limit']))

    def test_route_mask_and_length_reject(self):
        sample = json.loads(Path('tests/fixtures/routera3d_sides.json').read_text())['sells'][0]['calldata']
        for data in [sample+'00', sample[:-2], sample[:-4]+'0000', sample[:-4]+'0003', sample[:-4]+'0006']:
            with self.assertRaises(ValueError):
                route_fields(data)
        with self.assertRaises(ValueError):
            forward_input_amount(sample, -1)

class BlockWindowTest(unittest.TestCase):
    def test_bytecode_boundaries(self):
        from routera3d_price import block_window
        cases=json.loads(Path('reports/amm/routera3d-expiry-validation.json').read_text())['cases']
        self.assertEqual(len(cases),120)
        for case in cases:
            result=block_window(case['calldata'],case['block'],int(case['slot9'],16))
            self.assertEqual(result['target_block'],case['expiry'])
            self.assertEqual(result['max_future_blocks'],case['max_future_blocks'])
            self.assertEqual(result['valid'],not case['invalid'])

class Mode40FramingTest(unittest.TestCase):
    def test_actual_router_no_special_route_framing(self):
        cases={c['label']:c for c in json.loads(Path('reports/amm/routera3d-mode40-probe.json').read_text())['cases']}
        base=cases['e1_baseline'];plain=cases['41_no_extra']
        self.assertEqual(base['result']['calls'],plain['result']['calls'])
        p=route_fields(plain['transaction']['data']);self.assertEqual(p['extra'],'')
        self.assertEqual(p['routes'],route_fields(base['transaction']['data'])['routes'])
        extra=cases['41_extra'];self.assertEqual(extra['result']['output'],'0xce09c715')
        with self.assertRaises(ValueError):route_fields(extra['transaction']['data'])
        for label in ('42_two_special_short','42_two_special_long'):
            with self.assertRaisesRegex(ValueError,'special-route framing'):route_fields(cases[label]['transaction']['data'])

class Mode40FeeHintTest(unittest.TestCase):
    def test_five_actual_swap_bounds_and_zero_fallback(self):
        from routera3d_price import mode40_limit_fee_hint
        cases=json.loads(Path('reports/amm/routera3d-index4-anchor-probe.json').read_text())['cases']
        self.assertEqual(len(cases),6)
        for c in cases:
            hint=mode40_limit_fee_hint(c['transaction']['data'])
            self.assertEqual(hint['limit_fee_hint_ppm'],c['tail'])
            self.assertEqual(hint['fallback_required'],c['tail']==0)
            if c['tail']:
                self.assertIsNotNone(c['limit'])
                self.assertEqual(reverse_v3_limit(1900000000,10,hint['limit_fee_hint_ppm'],10),c['limit'])
            else:
                self.assertIsNone(c['limit'])
                self.assertIn('unknown slot',c['result']['error'])
