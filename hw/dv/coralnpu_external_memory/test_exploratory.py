"""CPU-only adversarial controls from CNEM-21/23--27, no DUT or SW imports."""
import copy,struct,unittest
from checker import *
from exploratory_checker import TrapChecker,NEGATIVE_RECORD_BYTES
from exploratory_responder import FaultResponder,AbortResponder,abort_epoch
from test_checker import addr,frame,S,CONFIG

def config(kind='load',response=2):
    target=0x21000000 if kind=='unmapped' else 0x200ff000
    return {**CONFIG,'kind':'error','error_kind':kind,'error_response':response,'fault_address':target,
            'expected_mcause':{'fetch':1,'load':5,'store':7,'unmapped':5}[kind],
            'expected_mepc':target if kind=='fetch' else BASE+64,'expected_mtval':0 if kind=='fetch' else target,
            'schedule':'P0','seed':42,'run_id':99}
def memory():
    m=bytearray(END-BASE)
    for a in GUARDS:m[a-BASE:a-BASE+16]=b'\xa5'*16
    struct.pack_into('<II',m,0x18000,0,99)
    return m

def complete_negative(kind='load',response=2,sentinel=True,ret_size=2,final_b=True):
    cfg=config(kind,response);c=TrapChecker(memory(),cfg);cycle=0
    def step(s):
        nonlocal cycle
        cycle+=1;c.process(cycle,s,S)
    def read(address,size=2,ident=0,error=0):
        p=addr(address,ident,size);data,_=snapshot_read(c.mem,p);step(frame(ar=p));step(frame(r=dict(id=ident,data=0 if error else data,resp=error,last=1)))
    def write(address,value,error=0):
        if address==cfg['ret'] and ret_size<2:
            for offset in range(0,4,1<<ret_size):
                at=address+offset;mask=(1<<(8*(1<<ret_size)))-1
                step(frame(aw=addr(at,0,ret_size),w=dict(data=((value>>(offset*8))&mask)<<(8*(at&15)),strb=((1<<(1<<ret_size))-1)<<(at&15),last=1)))
                step(frame(b=dict(id=0,resp=error)))
        else:
            step(frame(aw=addr(address,0,2),w=dict(data=value<<(8*(address&15)),strb=15<<(address&15),last=1)))
            if address!=RECORD or final_b:step(frame(b=dict(id=0,resp=error)))
    if sentinel:write(cfg['ret'],0x0badd00d)
    read(BASE+0x18004)
    if kind=='store':write(cfg['fault_address'],0xdeadbeef,response)
    else:read(cfg['fault_address'],4 if kind=='fetch' else 2,1 if kind=='fetch' else 0,response)
    record=[0x434e454d,1,99,1,0,0,0,1,cfg['expected_mcause'],cfg['expected_mepc'],cfg['expected_mtval'],1,0,0,0,0]
    for i in (1,2,3,7,8,9,10,11):write(RECORD+4*i,record[i])
    write(cfg['ret'],1);write(RECORD,record[0]);c.release=0
    return c,cycle

class NegativeControls(unittest.TestCase):
    def test_seven_complete_explicit_trap_profiles(self):
        for kind in ('fetch','load','store','unmapped'):
            for response in ((3,) if kind=='unmapped' else (2,3)):
                with self.subTest(kind=kind,response=response):
                    c,cycle=complete_negative(kind,response);c.process(cycle+1,frame(),dict(halted=1,fault=0,wfi=0))
                    self.assertEqual(c.summary()['record_bytes'],36);self.assertEqual(len(c.error_handshakes),1)
                    c.observe_responder(cycle+1,c.mem,10)
                    for edge in range(cycle+2,cycle+34):
                        c.process(edge,frame(),dict(halted=1,fault=0,wfi=0));c.observe_responder(edge,c.mem,10)
                    c.finish()
    def test_wrong_cause_pc_value_and_record_bytes(self):
        c,_=complete_negative()
        for offset in (0,4,8,12,16,24,28,32,36,40,44,48,60):
            bad=copy.deepcopy(c);bad.mem[RECORD+offset-BASE]^=1
            with self.assertRaises(AssertionError,msg=str(offset)):bad.accept()
    def test_missing_mandatory_write_coverage(self):
        c,_=complete_negative()
        for address in NEGATIVE_RECORD_BYTES:
            bad=copy.deepcopy(c);bad.written.remove(address)
            with self.assertRaises(AssertionError):bad.accept()
    def test_missing_return_store_or_wrong_return(self):
        c,_=complete_negative();c.return_bytes.clear()
        with self.assertRaises(AssertionError):c.accept()
        c,_=complete_negative();c.mem[c.config['ret']-BASE]=0
        with self.assertRaises(AssertionError):c.accept()
    def test_missing_sentinel_rejected(self):
        with self.assertRaisesRegex(AssertionError,'sentinel'):complete_negative(sentinel=False)
    def test_fault_and_wfi_cannot_qualify_terminal(self):
        c,cycle=complete_negative()
        with self.assertRaisesRegex(AssertionError,'top fault'):c.process(cycle+1,frame(),dict(halted=1,fault=1,wfi=0))
        c,cycle=complete_negative();c.process(cycle+1,frame(),dict(halted=1,fault=0,wfi=1));self.assertIsNone(c.halt)
    def test_negative_deadline_edge(self):
        c,_=complete_negative();c.process(1000000,frame(),dict(halted=1,fault=0,wfi=0))
        c,_=complete_negative()
        with self.assertRaises(AssertionError):c.process(1000000,frame(),S)
    def test_wrong_error_response_or_nonzero_error_data(self):
        cfg=config()
        for response,data in ((3,0),(2,1),(0,0)):
            c=TrapChecker(memory(),cfg);c.process(1,frame(ar=addr(cfg['fault_address'],0,2)),S)
            with self.assertRaises(AssertionError):c.process(2,frame(r=dict(id=0,data=data,resp=response,last=1)),S)
    def test_injection_only_first_matching_response(self):
        cfg=config();c=TrapChecker(memory(),cfg)
        for cycle,response in ((1,2),(3,0)):
            c.process(cycle,frame(ar=addr(cfg['fault_address'],0,2)),S)
            c.process(cycle+1,frame(r=dict(id=0,data=0,resp=response,last=1)),S)
        self.assertEqual(c.substitutions,1)
    def test_unmapped_decode_is_not_counted_as_injection(self):
        c,_=complete_negative('unmapped',3);self.assertEqual(c.substitutions,0);self.assertEqual(c.target_operations,1)
    def test_responder_error_read_zero_and_matching_id(self):
        for kind in ('fetch','load'):
            cfg=config(kind);r=FaultResponder(memory(),cfg);ident=1 if kind=='fetch' else 0
            r.advance(1,frame(ar=addr(cfg['fault_address'],ident,4 if kind=='fetch' else 2)))
            self.assertEqual(r.outputs(2)['r']['p'],dict(id=ident,data=0,resp=2,last=1));self.assertEqual(len(r.injected),1)
    def test_responder_error_store_never_mutates(self):
        for order in ('aw','w','same'):
            cfg=config('store');m=memory();m[0xff000:0xff010]=b'\x83'*16;r=FaultResponder(m,cfg)
            a=addr(cfg['fault_address'],0,2);w=dict(data=0xdeadbeef,strb=15,last=1)
            if order=='same':r.advance(1,frame(aw=a,w=w))
            else:
                r.advance(1,frame(**{order:a if order=='aw' else w}));r.advance(2,frame(**({'w':w} if order=='aw' else {'aw':a})))
            self.assertEqual(r.memory,m);self.assertEqual(r.outputs(3)['b']['p'],dict(id=0,resp=2))
    def test_unmapped_responder(self):
        cfg=config('unmapped',3);r=FaultResponder(memory(),cfg);r.advance(1,frame(ar=addr(cfg['fault_address'],0,2)))
        self.assertEqual(r.outputs(2)['r']['p'],dict(id=0,data=0,resp=3,last=1));self.assertFalse(r.injected)

class ResetControls(unittest.TestCase):
    def test_pending_ar_is_withheld_and_purged(self):
        cfg={**CONFIG,'seed':42,'reset_kind':'ar'};c=Checker(memory(),cfg);r=AbortResponder(memory(),cfg);c.release=0
        req=frame(ar=addr(BASE,1,4));c.process(1,req,S);r.advance(1,req)
        self.assertEqual(r.outputs(2)['r']['valid'],0);c.process(2,frame(),S)
        witness=abort_epoch(c,r,'ar',BASE,cfg['ret']);self.assertEqual(witness['kind'],'AR_WITHOUT_R')
        self.assertFalse(c.reads);self.assertFalse(r.ar);self.assertIsNone(r.active_r)
        c.process(1000001,frame(),S) # old-epoch watchdogs were canceled
        self.assertEqual(r.outputs(1000002)['r']['valid'],0)
    def test_aw_only_discards_half_and_cancels_watchdog(self):
        cfg={**CONFIG,'seed':42,'reset_kind':'aw_only'};c=Checker(memory(),cfg);r=AbortResponder(memory(),cfg);c.release=0
        req=frame(aw=addr(cfg['ret'],0,2),w=dict(data=99,strb=15,last=1));req['w']['ready']=r.outputs(1)['w']['ready']
        self.assertEqual(req['w']['ready'],0);c.process(1,req,S);r.advance(1,req)
        before=bytes(r.memory);witness=abort_epoch(c,r,'aw_only',BASE,cfg['ret'])
        self.assertEqual(witness['kind'],'AW_WITHOUT_W');self.assertEqual(r.memory,before);self.assertFalse(r.aw);self.assertFalse(r.w);self.assertIsNone(c.aw)
        c.process(1000001,frame(),S)
    def test_invalid_abort_witness_rejected(self):
        cfg={**CONFIG,'seed':42,'reset_kind':'ar'};c=Checker(memory(),cfg);r=AbortResponder(memory(),cfg);c.release=0
        with self.assertRaises(AssertionError):abort_epoch(c,r,'ar',BASE,cfg['ret'])
        c.process(1,frame(aw=addr(cfg['ret'],0,2),w=dict(data=0,strb=0,last=1)),S)
        with self.assertRaises(AssertionError):abort_epoch(c,r,'aw_only',BASE,cfg['ret'])
    def test_prior_epoch_response_rejected_by_fresh_checker(self):
        for channel,payload in (('r',dict(id=1,data=0,resp=0,last=1)),('b',dict(id=0,resp=0))):
            c=Checker(memory(),CONFIG)
            with self.assertRaises(AssertionError):c.process(11,frame(**{channel:payload}),S)
    def test_memory_and_queues_are_separate_after_cold_reload(self):
        cfg={**CONFIG,'seed':42,'reset_kind':'ar'};old=AbortResponder(memory(),cfg);fresh=AbortResponder(memory(),cfg)
        old.memory[0]=123;old.ar.append(dict(id=1,due=1,p=dict(id=1,data=0,resp=0,last=1)));old.purge()
        self.assertEqual(fresh.memory[0],0);self.assertFalse(fresh.ar);self.assertIsNone(fresh.active_r)


class ColdReloadControls(unittest.TestCase):
    def test_salt17_runid_reload_ignores_prior_committed_memory(self):
        import tempfile
        from pathlib import Path
        header=struct.pack('<16sHHIIIIIHHHHHH',b'\x7fELF\x01\x01\x01'+bytes(9),2,243,1,BASE,52,0,0,52,32,1,0,0,0)
        ph=struct.pack('<8I',1,84,BASE,BASE,4,8,5,4)
        with tempfile.TemporaryDirectory() as td:
            elf=Path(td)/'fixture.elf';elf.write_bytes(header+ph+b'CODE')
            old,_=initial_image(elf,0,2100);old[RECORD-BASE:RECORD-BASE+64]=b'\x7a'*64;old[CS[0][0]-BASE]=12
            fresh,info=initial_image(elf,17,2101)
            self.assertEqual(struct.unpack_from('<II',fresh,0x18000),(17,2101));self.assertEqual(fresh[RECORD-BASE:RECORD-BASE+64],bytes(64))
            for a,n in CS:self.assertEqual(fresh[a-BASE:a-BASE+n],b'\xa5'*n)
            for a in GUARDS:self.assertEqual(fresh[a-BASE:a-BASE+16],b'\xa5'*16)
            self.assertEqual(fresh[4:8],bytes(4));self.assertNotEqual(old,fresh)
            for case,(aa,ba) in enumerate(((BASE+0x10000,BASE+0x11000),(BASE+0x14000,BASE+0x15000))):
                a,b=oracle.inputs(case,17);self.assertEqual(fresh[aa-BASE:aa-BASE+len(a)],bytes(v&255 for v in a));flat=[v for row in b for v in row];self.assertEqual(fresh[ba-BASE:ba-BASE+len(flat)],bytes(v&255 for v in flat))

if __name__=='__main__':unittest.main()
