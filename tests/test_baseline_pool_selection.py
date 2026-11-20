import sys,unittest
from pathlib import Path
from decimal import Decimal as D
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from baseline_policy import sizes,best_pool
from metric_strategy import Policy,Inventory
class SelectionTests(unittest.TestCase):
 def setUp(self):self.policy=Policy(D(500),D(10));self.bbo={'bid':'100','ask':'100','available_ns':1}
 def quote(self,pool,side,q,amount):return {'pool':pool,'side':side,'quantity':str(q),'quote':dict(status='priced',state_valid=True,size_tokens=str(q),available_ns=1,bid_usdg=str(amount),ask_usdg=str(amount))}
 def test_shared_cap_not_per_pool(self):
  inv=Inventory(D(5),D(1000));rows=[self.quote('a','buy',D(5),D(499)),self.quote('b','buy',D(5),D(498))]
  r=best_pool(self.policy,inv,D(5),self.bbo,1,rows,D(10),D(-5));self.assertEqual(r['pool'],'b')
  inv=Inventory(D(10),D(502));self.assertIsNone(best_pool(self.policy,inv,D(5),self.bbo,1,rows,D(10),D(-5)))
 def test_close_can_use_different_pool_without_crossing_baseline(self):
  inv=Inventory(D(3),D(700));self.assertEqual(sizes(self.policy,inv,D(5),D(100)),dict(buy=D(2),sell=D(0)))
  rows=[self.quote('b','buy',D(2),D('200.05')),self.quote('a','buy',D(3),D(299))]
  r=best_pool(self.policy,inv,D(5),self.bbo,1,rows,D(10),D(-5));self.assertEqual((r['pool'],r['phase']),('b','close'))
 def test_initial_long_room_is_additional_and_no_borrowed_shares(self):
  self.assertEqual(sizes(self.policy,Inventory(D(5),D(500)),D(5),D(100)),dict(buy=D(5),sell=D(5)))
  rows=[self.quote('a','sell',D(1),D(101))];self.assertIsNone(best_pool(self.policy,Inventory(D(0),D(1000)),D(5),self.bbo,1,rows,D(10),D(-5)))
if __name__=='__main__':unittest.main()
