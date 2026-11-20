import json,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from bootstrap_state import mapping
class PrefixDiscoveryTest(unittest.TestCase):
 def test_nine_current_code_prefixes(self):
  rows=json.loads(Path('reports/amm/router7627-prefix.json').read_text())['cases'];self.assertEqual(len(rows),9)
  for row in rows:
   self.assertIn('unknown account',row['baseline']['error']);self.assertIsNone(row['result']['error']);c=row['result']['calls'][0];self.assertEqual(c['to'],'0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca');self.assertEqual(c['data'],'0x3850c7bd');self.assertFalse(row['result']['execution_success'])
 def test_second_price_and_additional_dependencies(self):
  rows=json.loads(Path('reports/amm/router7627-prices.json').read_text())['cases']
  for row in rows:
   c=row['result']['calls'][0];self.assertEqual(c['to'],'0x8366a39cc670b4001a1121b8f6a443a643e40951');self.assertEqual(c['data'],'0x1e2eaeafa652248898f7392773fb86e84bf1ef4cf17b449600f2d309595c039285782ad8')
  rows=json.loads(Path('reports/amm/router7627-prices-v4-3400000000000000000000000.json').read_text())['cases']
  for row in rows:
   calls=row['result']['calls'];self.assertEqual(len(calls),2);self.assertEqual(calls[0]['data'],'0xddca3f43');self.assertEqual(calls[1]['data'],'0x1e2eaeafa652248898f7392773fb86e84bf1ef4cf17b449600f2d309595c039285782adb');self.assertFalse(row['result']['execution_success'])

 def test_liquidity_intervention_reaches_bitmap(self):
  report=json.loads(Path('reports/amm/router7627-prices-v4-3400000000000000000000000-liq-1000000000000000000.json').read_text());base=int('a652248898f7392773fb86e84bf1ef4cf17b449600f2d309595c039285782ad8',16);slot=mapping(0,base+5)
  self.assertEqual(len(report['cases']),9)
  for row in report['cases']:
   r=row['result'];self.assertIsNone(r['error']);self.assertFalse(r['execution_success']);self.assertEqual(r['calls'][0]['data'],'0x1e2eaeaf'+slot[2:]);self.assertEqual(r['calls'][0]['to'],'0x8366a39cc670b4001a1121b8f6a443a643e40951')

 def test_actual_unlock_callback_swap_intents(self):
  expected=None
  for inventory in (10**18,2*10**18):
   report=json.loads(Path(f'reports/amm/router7627-local-getters-shift-50-inventory-{inventory}-unlock.json').read_text());self.assertEqual(len(report['cases']),3)
   for row in report['cases']:
    r=row['result'];self.assertIsNone(r['error']);self.assertFalse(r['execution_success']);c=r['calls'][0];self.assertEqual(c['data'][:10],'0xf3cd914c');b=bytes.fromhex(c['data'][10:]);self.assertEqual(int.from_bytes(b[160:192],'big'),1);self.assertEqual(int.from_bytes(b[192:224],'big',signed=True),-10**19);self.assertEqual(int.from_bytes(b[224:256],'big'),3389941616529640613032821)
    if expected is None:expected=c['data']
    self.assertEqual(c['data'],expected);self.assertTrue(any(x['data'].startswith('0x91dd7346') for x in r['execution_calls']));self.assertIsNotNone(row['price_intervention'])

 def test_amount_cap_and_price_dependent_limit(self):
  code=bytes.fromhex(json.loads(Path('reports/amm/router7627-code.json').read_text())['code'][2:]);self.assertEqual(code[12060],0x7f);self.assertEqual(int.from_bytes(code[12061:12093],'big'),10**19)
  limits=[]
  for shift,inventory in [(50,0),(50,10**15),(100,10**18)]:
   report=json.loads(Path(f'reports/amm/router7627-local-getters-shift-{shift}-inventory-{inventory}-unlock.json').read_text())
   for row in report['cases']:
    r=row['result'];self.assertIsNone(r['error']);c=r['calls'][0];self.assertEqual(c['data'][:10],'0xf3cd914c');b=bytes.fromhex(c['data'][10:]);self.assertEqual(int.from_bytes(b[192:224],'big',signed=True),-10**19);limits.append((shift,int.from_bytes(b[224:256],'big')))
  a={limit for shift,limit in limits if shift==50};b={limit for shift,limit in limits if shift==100};self.assertEqual(len(a),1);self.assertEqual(len(b),1);self.assertNotEqual(a,b)
