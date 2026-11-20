import copy
import io
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from optimistic_pool import Follower
from tape import MAGIC, write_record, read
from v3_state import State, Q96, MIN_SQRT

A = '0x' + '11' * 20
B = '0x' + '22' * 20

def seed():
    state = State(Q96, 0, 0, 500, 1, {w: 0 for w in range(-4, 4)}, {})
    state.modify(-100, 100, 10**18)
    return dict(complete=True, anchor=dict(hash='h1'), pools=[dict(
        pool=A, tokens=[A, B], base_token=A, quote_token=B, base_index=0,
        decimals=[18,18], fee=500, spacing=1, sqrt=str(state.sqrt),
        tick=0, liquidity=str(state.liquidity), bitmap=state.bitmap, ticks=state.ticks)])

def marker(n, count=0):
    return dict(kind='feed_block', sequence=n, block_hash='h'+str(n), transaction_count=count)

def tx(n, identity='t'):
    words = [0,1,10**12,MIN_SQRT+1,160,0]
    return dict(kind='feed_tx', tx=identity, to=A, data='0x128acb08'+''.join(
        v.to_bytes(32,'big').hex() for v in words), block_hash='h'+str(n), mono_ns=1, recv_ns=2)

class OptimisticTests(unittest.TestCase):
    def follower(self, **kwargs):
        rows=[]
        f=Follower(seed(), ['0.000001'], rows.append, **kwargs)
        f.event(marker(1))
        return f,rows

    def test_unknown_sender_does_not_block_and_duplicate_does_not_apply(self):
        f,rows=self.follower()
        f.event(marker(2,1)); f.event(tx(2))
        state=copy.deepcopy(f.book.states[A]); self.assertLess(state.sqrt,Q96)
        f.event(tx(2)); self.assertEqual(state,f.book.states[A])
        self.assertTrue(any(r['kind']=='amm_state_quote' and 'bid' in r for r in rows))

    def test_background_install_replays_only_after_anchor_and_preserves_history(self):
        f,rows=self.follower()
        f.event(marker(2,1)); f.event(tx(2))
        before=copy.deepcopy(rows)
        f.event(marker(3,1)); f.event(tx(3,'t3'))
        want=copy.deepcopy(f.book.states[A])
        f.install(seed())
        self.assertEqual(want,f.book.states[A]); self.assertEqual(rows[:len(before)],before)
        self.assertEqual(f.generation,1)
        self.assertEqual(rows[-1]['cause'],'reconciliation')

    def test_gap_rejects_old_snapshot_and_new_anchor_recovers(self):
        f,rows=self.follower()
        f.event(dict(kind='gap',stream='nitro'))
        with self.assertRaises(ValueError):f.install(seed())
        f.event(marker(5)); snapshot=seed();snapshot['anchor']['hash']='h5'
        f.install(snapshot); self.assertFalse(f.needs_sync)
        f.event(marker(6,1));f.event(tx(6));self.assertLess(f.book.states[A].sqrt,Q96)

    def test_partial_anchor_and_missing_transaction_rejected(self):
        f,_=self.follower();f.event(marker(2,1))
        snapshot=seed();snapshot['anchor']['hash']='h2'
        with self.assertRaises(ValueError):f.install(snapshot)
        f.event(marker(3));self.assertTrue(f.needs_sync)
        with self.assertRaises(ValueError):f.install(snapshot)

    def test_unknown_router_is_coverage_record_not_global_invalidation(self):
        f,rows=self.follower();f.event(marker(2,2))
        unknown=tx(2,'unknown');unknown['to']=B;f.event(unknown);f.event(tx(2))
        self.assertFalse(f.book.invalid)
        self.assertTrue(any(r['kind']=='calldata_coverage_gap' for r in rows))
        self.assertLess(f.book.states[A].sqrt,Q96)

    def test_snapshot_at_later_block_does_not_double_apply_anchor(self):
        f,_=self.follower();f.event(marker(2,1));f.event(tx(2))
        snapshot=seed();snapshot['anchor']['hash']='h2'
        state=f.book.states[A]
        snapshot['pools'][0].update(sqrt=str(state.sqrt),tick=state.tick,
                                    liquidity=str(state.liquidity))
        f.event(marker(3,1));f.event(tx(3,'next'))
        want=copy.deepcopy(f.book.states[A]);f.install(snapshot)
        self.assertEqual(want,f.book.states[A])

    def test_success_assumption_skips_router_guard(self):
        from unittest.mock import patch
        from amm_feed_state import Book
        op=dict(kind='swap',pool=A,zero=True,amount=10**12,limit=MIN_SQRT+1,
                constraint=dict(kind='min_out',amount=10**30))
        with patch('amm_feed_state.decode',return_value=[op]):
            strict=Book(seed());optimistic=Book(seed(),assume_success=True)
            self.assertEqual(strict.proposal(tx(2)),[])
            self.assertEqual(optimistic.proposal(tx(2)),[A])

    def test_reconnect_anchor_does_not_reenable_old_mutated_book(self):
        f,_=self.follower();f.event(marker(2,1));f.event(tx(2))
        before=copy.deepcopy(f.book.states[A])
        f.event(dict(kind='gap',stream='nitro'));f.event(marker(1))
        f.event(marker(2,1));f.event(tx(2))
        self.assertFalse(f.started);self.assertTrue(f.needs_sync)
        self.assertEqual(before,f.book.states[A])
        f.install(seed());self.assertEqual(before,f.book.states[A])

    def test_impossible_math_publishes_pool_unavailable(self):
        f,rows=self.follower();f.event(marker(2,1))
        bad=tx(2);bad['data']='0xa34123a7'+''.join(
            (v % (1<<256)).to_bytes(32,'big').hex() for v in [-100,100,10**19])
        f.event(bad)
        self.assertIn(A,f.book.invalid)
        self.assertEqual(rows[-1]['kind'],'amm_state_quote')
        self.assertIn('reason',rows[-1]);self.assertNotIn('bid',rows[-1])

    def test_binary_roundtrip(self):
        f,rows=self.follower();f.event(marker(2,1));f.event(tx(2))
        out=io.BytesIO();out.write(MAGIC)
        for row in rows:write_record(out,row)
        out.seek(0);decoded=list(read(out))
        self.assertEqual(decoded[-1],rows[-1])
        self.assertEqual(State.load(decoded[0]['seed']['pools'][0]),State.load(seed()['pools'][0]))

if __name__=='__main__':unittest.main()
