import sys,unittest,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from iex_pool_hy import load_iex
class IexTests(unittest.TestCase):
 def q(self,recv,stamp,bid=100,ask=101):return dict(kind='iex_bbo',symbol='AAPL',recv_ns=recv,exchange_ns=stamp,bid=bid,ask=ask)
 def test_duplicate_late_invalid_and_gap(self):
  s,b,q=load_iex([dict(kind='iex_session',config={'symbols':['AAPL']},recv_ns=1),self.q(10,9),self.q(11,9),self.q(12,8),self.q(13,12,102,101),dict(kind='iex_gap',recv_ns=14),self.q(15,14,101,102)])
  self.assertEqual(len(b['AAPL']),2);self.assertEqual(q['duplicate_AAPL'],1);self.assertEqual(q['late_AAPL'],1);self.assertEqual(q['invalid_AAPL'],1);self.assertTrue(math.isnan(s['AAPL'][1][1]));self.assertTrue(math.isnan(s['AAPL'][2][1]));self.assertEqual(s['AAPL'][-1],[15,101.,102.])
if __name__=='__main__':unittest.main()
