import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from delegated_compressed import inspect
from delegated_unlock_plan import inspect as expanded
class CompressedTest(unittest.TestCase):
 def test_original_and_controlled_bytecode_expansion(self):
  txs={t['tx']:t for t in map(json.loads,Path('reports/amm/delegated-router-txs.jsonl').read_text().splitlines())}
  original=json.loads(Path('reports/amm/delegated-router-callback-probe.json').read_text())['cases']
  for c in original:
   actual=inspect(txs[c['tx']]['data']);expected=expanded(c['callback'])
   self.assertEqual([g['expanded'] for g in actual['condition_groups']],expected['condition_groups']);self.assertEqual(actual['strategies'],expected['strategies']);self.assertFalse(actual['execution_complete'])
   self.assertTrue(actual['compressed_conditions'])
  mutations=json.loads(Path('reports/amm/delegated-encoding-probe.json').read_text())['cases']
  for c in mutations:
   a=inspect(c['tx']['data']);b=expanded(c['result']['calls'][0]['data'])
   self.assertEqual(a['strategies'],b['strategies'])
   self.assertEqual([g['expanded'] for g in a['condition_groups']],b['condition_groups'])
 def test_malformed_inputs(self):
  tx=json.loads(Path('reports/amm/delegated-router-funded-balance-0.json').read_text())['tx'];raw=bytes.fromhex(tx['data'][2:])
  for end in (0,4,5,25,180,200,250,303,len(raw)-1):
   with self.assertRaises(ValueError):inspect('0x'+raw[:end].hex())
  for offset,value in [(4,0),(166,33),(209,8),(210,255),(250,1)]:
   b=bytearray(raw);b[offset]=value
   with self.assertRaises(ValueError):inspect('0x'+b.hex())
