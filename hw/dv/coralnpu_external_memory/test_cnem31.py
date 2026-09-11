"""Spec-derived v0.4 terminal boundary controls; synthetic public traffic only."""
import copy,unittest
from checker import BASE,RECORD
from test_exploratory import complete_negative,config,memory
from exploratory_checker import TrapChecker
from test_checker import addr,frame,S
HALT=dict(halted=1,fault=0,wfi=0)

def terminal(edge=None):
    c,n=complete_negative();t=n+1 if edge is None else edge
    c.process(t,frame(),HALT);c.observe_responder(t,c.mem,12)
    return c,t

def window(c,t,n=32):
    for edge in range(t+1,t+n+1):
        c.process(edge,frame(),HALT);c.observe_responder(edge,c.mem,12)

class TerminalControls(unittest.TestCase):
    def test_byte_and_halfword_return_evidence_uses_all_successful_Bs(self):
        for size in (0,1):
            c,n=complete_negative(ret_size=size);c.accept()
            self.assertEqual(c.return_bytes,set(range(4)))
            self.assertEqual(len(c.ret_write_events),8 if size==0 else 4)
    def test_sentinel_cannot_reappear_after_return_and_partial_return_cannot_precede_it(self):
        c,n=complete_negative();a=addr(c.config['ret'],0,2)
        with self.assertRaisesRegex(AssertionError,'return store after final magic'):
            c.process(n+1,frame(aw=a,w=dict(data=0x0badd00d,strb=15,last=1)),S)
        c=TrapChecker(memory(),config());c.process(1,frame(aw=addr(c.config['ret'],0,0),w=dict(data=1,strb=1,last=1)),S)
        with self.assertRaisesRegex(AssertionError,'return byte before sentinel'):c.process(2,frame(b=dict(id=0,resp=0)),S)
    def test_magic_precedes_return_full_trace_rejected_for_each_width(self):
        # Capture the valid public stimulus, then only swap final return and magic.
        from unittest.mock import patch
        from exploratory_responder import FaultResponder
        for size in (0,1,2):
            trace=[];original=TrapChecker.process
            def capture(check,cycle,snapshot,status):
                trace.append(copy.deepcopy(snapshot));return original(check,cycle,snapshot,status)
            with patch.object(TrapChecker,'process',capture):complete_negative(ret_size=size)
            count=2*(4//(1<<size));invalid=trace[:-count-2]+trace[-2:]+trace[-count-2:-2]
            c=TrapChecker(memory(),config());r=FaultResponder(memory(),config());c.release=0
            with self.assertRaisesRegex(AssertionError,'magic before completed handler return'):
                for edge,snapshot in enumerate(invalid,1):
                    c.process(edge,snapshot,S);r.advance(edge,snapshot)
                    c.observe_responder(edge,r.memory,len(r.write_commits))
    def test_no_return_byte_store_after_final_magic(self):
        for size in (0,1,2):
            c,n=complete_negative(ret_size=size);at=c.config['ret']
            with self.assertRaisesRegex(AssertionError,'return store after final magic'):
                c.process(n+1,frame(aw=addr(at,0,size),w=dict(data=1,strb=(1<<(1<<size))-1,last=1)),S)
    def test_final_magic_B_on_terminal_edge_counts(self):
        c,n=complete_negative(final_b=False);c.process(n+1,frame(),HALT);self.assertIsNone(c.halt)
        c.process(n+2,frame(b=dict(id=0,resp=0)),HALT);self.assertEqual(c.halt,n+2)
    def test_last_legal_edge_and_additional_window(self):
        c,t=terminal(1000000);window(c,t);c.finish()
        self.assertEqual(c.post_halt_observations[-1]['cycle'],1000032)
    def test_late_terminal_and_release_offset(self):
        c,_=complete_negative()
        with self.assertRaisesRegex(AssertionError,'late terminal'):c.process(1000001,frame(),HALT)
        c,_=complete_negative();c.release=57;c.process(1000057,frame(),HALT);self.assertEqual(c.halt,1000057)
    def test_each_window_edge_and_exact_count(self):
        for count in (0,1,31):
            c,t=terminal();window(c,t,count)
            with self.assertRaisesRegex(AssertionError,'incomplete'):c.finish()
        c,t=terminal();window(c,t);c.finish()
        with self.assertRaisesRegex(AssertionError,'exactly 32'):c.process(t+33,frame(),HALT)
    def test_no_skipped_observation_edge(self):
        c,t=terminal()
        with self.assertRaisesRegex(AssertionError,'consecutive'):c.process(t+2,frame(),HALT)
    def test_first_and_last_window_status_changes_fail(self):
        for offset in (1,32):
            for field,value in (('halted',0),('fault',1),('wfi',1)):
                c,t=terminal();window(c,t,offset-1)
                with self.assertRaisesRegex(AssertionError,'unstable'):c.process(t+offset,frame(),{**HALT,field:value})
                self.assertEqual(c.halt,t) # no later terminal may replace T
    def test_first_and_last_window_write_halves_fail_even_zero_strobe(self):
        for offset in (1,32):
            for kwargs in ({'aw':addr(BASE+0x20000,0,2)},{'w':dict(data=0,strb=0,last=1)}):
                c,t=terminal();window(c,t,offset-1)
                with self.assertRaisesRegex(AssertionError,'write handshake'):c.process(t+offset,frame(**kwargs),HALT)
    def test_entire_aperture_mutation_and_commit_without_changed_byte_fail(self):
        for offset in (1,32):
            c,t=terminal();window(c,t,offset-1);c.mem[-1]^=1
            with self.assertRaisesRegex(AssertionError,'aperture changed'):c.process(t+offset,frame(),HALT)
            c,t=terminal();window(c,t,offset-1);c.process(t+offset,frame(),HALT)
            with self.assertRaisesRegex(AssertionError,'write commit'):c.observe_responder(t+offset,c.mem,13)
            c,t=terminal();window(c,t,offset-1);c.process(t+offset,frame(),HALT);m=bytearray(c.mem);m[-1]^=1
            with self.assertRaisesRegex(AssertionError,'aperture equality'):c.observe_responder(t+offset,m,12)
    def test_instruction_prefetch_pending_at_T_and_during_window(self):
        c,n=complete_negative();p=addr(BASE,1,4);c.process(n+1,frame(ar=p),S)
        t=n+2;c.process(t,frame(),HALT);c.observe_responder(t,c.mem,12)
        c.process(t+1,frame(r=dict(id=1,data=0,resp=0,last=1)),HALT);c.observe_responder(t+1,c.mem,12)
        c.process(t+2,frame(ar=p),HALT);c.observe_responder(t+2,c.mem,12)
        for edge in range(t+3,t+33):c.process(edge,frame(),HALT);c.observe_responder(edge,c.mem,12)
        c.finish();self.assertIn(1,c.reads) # instruction drain is not an extra prerequisite
    def test_instruction_deadline_remains_active_in_window(self):
        c,n=complete_negative();c.process(n+1,frame(ar=addr(BASE,1,4)),S)
        t=n+255;c.process(t,frame(),HALT);c.observe_responder(t,c.mem,12)
        c.process(t+1,frame(),HALT)
        with self.assertRaisesRegex(AssertionError,'R deadline'):c.process(t+2,frame(),HALT)
    def test_pending_data_delays_terminal_until_last_handshake(self):
        for kind in ('read','aw','w','write'):
            c,n=complete_negative();a=addr(BASE+0x20010,0,2);w=dict(data=0,strb=0,last=1)
            req={'read':dict(ar=a),'aw':dict(aw=a),'w':dict(w=w),'write':dict(aw=a,w=w)}[kind]
            c.process(n+1,frame(**req),HALT);self.assertIsNone(c.halt)
            if kind=='read':last=frame(r=dict(id=0,data=0,resp=0,last=1))
            else:
                if kind in ('aw','w'):
                    c.process(n+2,frame(**({'w':w} if kind=='aw' else {'aw':a})),HALT);self.assertIsNone(c.halt);n+=1
                last=frame(b=dict(id=0,resp=0))
            c.process(n+2,last,HALT);self.assertEqual(c.halt,n+2)
    def test_missing_terminal_record_B_and_return_B_are_not_evidence(self):
        c,n=complete_negative();c.written.remove(RECORD)
        c.process(n+1,frame(),HALT);self.assertIsNone(c.halt)
        c,n=complete_negative();c.return_bytes.clear()
        c.process(n+1,frame(),HALT);self.assertIsNone(c.halt)
    def test_reversed_sentinel_and_same_edge_B_first_half_rejected(self):
        c,n=complete_negative();c.sentinel_b=None
        with self.assertRaisesRegex(AssertionError,'completed sentinel/return'):c.accept()
        for first in ('aw','w','both'):
            c=TrapChecker(memory(),config());ret=c.config['ret'];a=addr(ret,0,2)
            c.process(1,frame(aw=a,w=dict(data=0x0badd00d,strb=15,last=1)),S)
            req={'b':dict(id=0,resp=0)}
            if first in ('aw','both'):req['aw']=a
            if first in ('w','both'):req['w']=dict(data=1,strb=15,last=1)
            if first=='both':
                with self.assertRaisesRegex(AssertionError,'precede first return half'):c.process(2,frame(**req),S)
            else:
                c.process(2,frame(**req),S)
                rest={'w':dict(data=1,strb=15,last=1)} if first=='aw' else {'aw':a}
                with self.assertRaisesRegex(AssertionError,'precede first return half'):c.process(3,frame(**rest),S)

if __name__=='__main__':unittest.main()
