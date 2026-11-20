"""Recompute arbitrary V3 sizes from optimistic journals, preserving checkpoint order.
Recomputed quotes are retrospective; use recorded quotes for as-seen latency studies.
"""
import argparse
from optimistic_pool import Follower
from tape import MAGIC, records, write_record


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input',nargs='+');ap.add_argument('--sizes',required=True)
    ap.add_argument('--output',required=True)
    args=ap.parse_args()
    with open(args.output,'xb') as output:
        output.write(MAGIC)
        def emit(row):
            if row['kind']=='amm_state_quote':
                row['phase']='offline_reconstruction'
                row['timing']='reconstructed_not_observed_latency'
                row['available_mono_ns']=None
                row['available_ns']=None
                write_record(output,row)
        follower=None
        for row in records(args.input):
            if row['kind']=='optimistic_checkpoint':
                if row.get('initial'):
                    follower=Follower(row['seed'],args.sizes.split(','),emit,max_blocks=row.get('max_blocks',20000),registry=row.get('registry'))
                else:
                    follower.install(row['seed'],row.get('registry'))
            elif row['kind']=='optimistic_input':
                if follower is None:raise ValueError('input before checkpoint')
                follower.event(row['event'])

if __name__=='__main__':main()
