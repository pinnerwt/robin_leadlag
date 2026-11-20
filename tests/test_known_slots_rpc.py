import io,json,sys,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bootstrap_known_slots import BatchRpc

class BatchTests(unittest.TestCase):
 def response(self,rows):return io.BytesIO(json.dumps(rows).encode())
 def test_response_order_is_by_id(self):
  with patch('bootstrap_known_slots.urllib.request.urlopen',return_value=self.response([dict(id=1,result='b'),dict(id=0,result='a')])):
   self.assertEqual(BatchRpc('https://unused').many([('m',[]),('m',[])]),['a','b'])
 def test_duplicate_id_rejected(self):
  with patch('bootstrap_known_slots.urllib.request.urlopen',return_value=self.response([dict(id=0,result='a'),dict(id=0,result='a')])):
   with self.assertRaises(ValueError):BatchRpc('https://unused').many([('m',[]),('m',[])])
 def test_rate_limit_retries_same_batch(self):
  err=urllib.error.HTTPError('https://unused',429,'rate limit',{},None)
  with patch('bootstrap_known_slots.urllib.request.urlopen',side_effect=[err,self.response([dict(id=0,result='a')])])as call,patch('bootstrap_known_slots.time.sleep'):
   self.assertEqual(BatchRpc('https://unused').one('m',[]),'a');self.assertEqual(call.call_count,2)
 def test_error_does_not_become_storage_value(self):
  with patch('bootstrap_known_slots.urllib.request.urlopen',return_value=self.response([dict(id=0,error={'code':-1})])):
   with self.assertRaises(RuntimeError):BatchRpc('https://unused').one('m',[])
if __name__=='__main__':unittest.main()
