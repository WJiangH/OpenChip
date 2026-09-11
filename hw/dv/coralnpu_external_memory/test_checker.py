"""Synthetic negative and boundary controls; no DUT dependency."""
import copy,struct,tempfile,unittest
from pathlib import Path
from checker import *
from responder import Responder
S={'halted':0,'fault':0,'wfi':0}
CONFIG={'salt':0,'run_id':1,'entry':BASE,'kernel':BASE+16,'ret':BASE+0x20000,'schedule':'P0'}
def addr(address=BASE,ident=1,size=4):return dict(addr=address,id=ident,size=size,len=0,burst=1,prot=2,lock=0,cache=0,qos=0,region=0)
def frame(**changes):
    s={k:dict(valid=0,ready=1,p={f:0 for f in fields}) for k,fields in FIELDS.items()}
    for k,p in changes.items():s[k]=dict(valid=1,ready=1,p=p)
    return s
def chk():return Checker(bytearray(END-BASE),CONFIG)
def wr(c,cycle=1,strobe=15,address=BASE+0x20000):c.process(cycle,frame(aw=addr(address,0,2),w=dict(data=0x11223344,strb=strobe,last=1)),S)
class Controls(unittest.TestCase):
    def test_r_lanes(self):
        c=chk();c.mem[5]=123;c.process(1,frame(ar=addr(BASE+5,0,0)),S);c.process(2,frame(r=dict(id=0,data=123<<40,resp=0,last=1)),S);self.assertIn(BASE+5,c.read_bytes)
    def test_wrong_id_data_unsolicited(self):
        for bad in (dict(id=0,data=0,resp=0,last=1),dict(id=1,data=1,resp=0,last=1)):
            c=chk();c.process(1,frame(ar=addr()),S)
            with self.assertRaises(AssertionError):c.process(2,frame(r=bad),S)
        with self.assertRaises(AssertionError):chk().process(1,frame(b=dict(id=0,resp=0)),S)
    def test_early_presented_response(self):
        c=chk();c.process(1,frame(ar=addr()),S);s=frame(r=dict(id=1,data=0,resp=0,last=1));s['r']['ready']=0
        with self.assertRaises(AssertionError):c.process(1,s,S)
    def test_stalled_stability(self):
        c=chk();s=frame(ar=addr());s['ar']['ready']=0;c.process(1,s,S);s=copy.deepcopy(s);s['ar']['p']['addr']+=16
        with self.assertRaises(AssertionError):c.process(2,s,S)
    def test_aw_w_order(self):
        for order in ('aw','w','same'):
            c=chk();a=addr(BASE+0x20000,0,2);w=dict(data=0x11223344,strb=15,last=1)
            if order=='same':c.process(1,frame(aw=a,w=w),S)
            else:
                c.process(1,frame(**{order:a if order=='aw' else w}),S)
                c.process(2,frame(**({'w':w} if order=='aw' else {'aw':a})),S)
            c.process(3,frame(b=dict(id=0,resp=0)),S);self.assertEqual(c.mem[0x20000:0x20004],bytes.fromhex('44332211'))
    def test_zero_mask_and_illegal_write(self):
        c=chk();wr(c,strobe=0);self.assertEqual(c.mem,bytearray(END-BASE))
        for address,mask in ((PROBE+1,3),(GUARDS[0],1),(BASE,1)):
            with self.assertRaises(AssertionError):chk().process(1,frame(aw=addr(address,0,0),w=dict(data=0,strb=mask,last=1)),S)
    def test_outstanding_bound(self):
        c=chk();c.process(1,frame(ar=addr(BASE,0)),S)
        with self.assertRaises(AssertionError):c.process(2,frame(aw=addr(BASE+0x20000,0)),S)
    def test_read_deadline(self):
        for age in (255,256):
            c=chk();c.process(1,frame(ar=addr()),S);c.process(1+age,frame(r=dict(id=1,data=0,resp=0,last=1)),S)
        for age in (256,257):
            c=chk();c.process(1,frame(ar=addr()),S)
            with self.assertRaises(AssertionError):c.process(1+age,frame(),S)
    def test_write_deadline(self):
        for age in (255,256):
            c=chk();wr(c);c.process(1+age,frame(b=dict(id=0,resp=0)),S)
        c=chk();wr(c)
        with self.assertRaises(AssertionError):c.process(257,frame(),S)
    def test_half_deadline(self):
        for age in (63,64):
            c=chk();c.process(1,frame(aw=addr(BASE+0x20000,0,2)),S);c.process(1+age,frame(w=dict(data=0,strb=0,last=1)),S)
        for age in (64,65):
            c=chk();c.process(1,frame(aw=addr(BASE+0x20000,0,2)),S)
            with self.assertRaises(AssertionError):c.process(1+age,frame(),S)
    def test_fault_halted_only_terminal_deadline(self):
        with self.assertRaises(AssertionError):chk().process(1,frame(),{**S,'fault':1})
        c=chk();c.release=1
        with self.assertRaises(AssertionError):c.process(2,frame(),{**S,'halted':1})
        c=chk();c.release=1;c.process(1000000,frame(),S)
        with self.assertRaises(AssertionError):c.process(1000001,frame(),S)
    def test_early_magic(self):
        with self.assertRaises(AssertionError):wr(chk(),address=RECORD)
    def test_host_lock(self):
        r=Responder(bytearray(END-BASE),'P0',42);r.locked=True
        with self.assertRaises(AssertionError):r.host_write(BASE,b'x')
    def test_response_timing_and_hold(self):
        mem=bytearray(END-BASE);mem[7]=91;r=Responder(mem,'P0',42);r.advance(10,frame(ar=addr(BASE+7,0,0)))
        self.assertEqual(r.outputs(10)['r']['valid'],0);response=r.outputs(11)['r'];self.assertEqual(response['p']['data'],91<<56);self.assertEqual(response,r.outputs(20)['r'])
    def test_p1_bounds_and_replay(self):
        r=Responder(bytearray(END-BASE),'P1',42);r2=Responder(bytearray(END-BASE),'P1',42);waits=dict(ar=0,aw=0,w=0)
        for cycle in range(1000):
            a=r.outputs(cycle);self.assertEqual(a,r2.outputs(cycle))
            for k in waits:
                waits[k]=0 if a[k]['ready'] else waits[k]+1;self.assertLessEqual(waits[k],7)
            r.advance(cycle,frame());r2.advance(cycle,frame())
        for k in ('r','b'):
            values=[r.delay(k) for _ in range(200)];self.assertEqual((min(values),max(values)),(1,15))
    def test_unmapped_read(self):
        c=chk();c.process(1,frame(ar=addr(0x21000000,0,2)),S);c.process(2,frame(r=dict(id=0,data=0,resp=3,last=1)),S)
    def test_elf_shape_bss_and_invalid_extents(self):
        h=struct.pack('<16sHHIIIIIHHHHHH',b'\x7fELF\x01\x01\x01'+bytes(9),2,243,1,BASE,52,0,0,52,32,1,0,0,0);p=struct.pack('<8I',1,84,BASE,BASE,4,8,5,4)
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'x.elf';f.write_bytes(h+p+b'CODE');mem,_=load_elf(f);self.assertEqual(mem[:8],b'CODE\0\0\0\0')
            for field,value in ((3,BASE+4),(4,9),(5,0x10001),(2,BASE+0x10000)):
                bad=list(struct.unpack('<8I',p));bad[field]=value;f.write_bytes(h+struct.pack('<8I',*bad)+b'CODE')
                with self.assertRaises(AssertionError):load_elf(f)

from host_checker import HostChecker

def completed_trace():
    image=bytearray(END-BASE)
    for case,(aa,ba) in enumerate(((0x20010000,0x20011000),(0x20014000,0x20015000))):
        a,b=oracle.inputs(case,0)
        for address,values in ((aa,a),(ba,[v for row in b for v in row])):image[address-BASE:address-BASE+len(values)]=bytes(v&255 for v in values)
    for a,n in (*CS,*[(g,16) for g in GUARDS],(PROBE,32)):image[a-BASE:a-BASE+n]=b'\xa5'*n
    struct.pack_into('<II',image,0x18000,0,1)
    c=Checker(image,dict(CONFIG));cycle=0
    def step(s):
        nonlocal cycle
        cycle+=1;c.process(cycle,s,S)
    def read(address,size=4,ident=0):
        p=addr(address,ident,size);value,resp=snapshot_read(c.mem,p);step(frame(ar=p));step(frame(r=dict(id=ident,data=value,resp=resp,last=1)))
    def write(address,value,size=2):
        step(frame(aw=addr(address,0,size),w=dict(data=value<<(8*(address&15)),strb=((1<<(1<<size))-1)<<(address&15),last=1)));step(frame(b=dict(id=0,resp=0)))
    write(CONFIG['ret'],0x0badd00d)
    for address in (BASE,BASE+16):read(address,ident=1)
    for address,size in AB:
        for offset in range(0,size,16):read(address+offset)
    read(BASE+0x18000)
    sig=[]
    for case,(address,size) in enumerate(CS):
        values=oracle.gemv(*oracle.inputs(case,0));sig.append(oracle.signature(values))
        for i,v in enumerate(values):write(address+i*4,v&0xffffffff)
    for address,value,size in ((PROBE+1,0x5a,0),(PROBE+6,0x1234,1),(PROBE+12,0x89abcdef,2)):
        write(address,value,size);read(address,size)
    record=[0x434e454d,1,1,0,*sig,2,0,0,0,0,0,0,0,0,0]
    for i in (1,2,3,4,5,6,11):write(RECORD+i*4,record[i])
    write(RECORD,record[0]);write(CONFIG['ret'],0)
    c.release=0
    return c,cycle
class TerminalControls(unittest.TestCase):
    def test_complete_trace_and_32_clocks(self):
        c,cycle=completed_trace()
        for i in range(1,34):c.process(cycle+i,frame(),dict(halted=1,fault=0,wfi=0))
        self.assertEqual(c.summary()['output_bytes'],388);self.assertEqual(c.summary()['input_bytes'],4330)
    def test_complete_deadline_edge(self):
        c,_=completed_trace();c.process(1000000,frame(),dict(halted=1,fault=0,wfi=0));self.assertEqual(c.halt,1000000)
    def test_corrupted_outputs_record_probe_guard_return(self):
        c,_=completed_trace()
        for address in (CS[0][0],CS[1][0],RECORD+8,PROBE+2,GUARDS[-1],CONFIG['ret']):
            bad=copy.deepcopy(c);bad.mem[address-BASE]^=1
            with self.assertRaises(AssertionError,msg=hex(address)):bad.accept()
    def test_missing_observed_bytes_and_response(self):
        c,_=completed_trace()
        for byte in (CS[0][0],RECORD+4,PROBE+1):
            bad=copy.deepcopy(c);bad.written.remove(byte)
            with self.assertRaises(AssertionError):bad.accept()
        c.write=dict(cycle=0,resp=0,bytes=set())
        with self.assertRaises(AssertionError):c.accept()
    def test_wrong_ret_sequence_and_late_write(self):
        c,cycle=completed_trace();c.ret_values=[0]
        with self.assertRaises(AssertionError):c.accept()
        c,cycle=completed_trace();c.process(cycle+1,frame(),dict(halted=1,fault=0,wfi=0))
        with self.assertRaises(AssertionError):wr(c,cycle+2)
    def test_post_magic_output_store(self):
        c,cycle=completed_trace()
        with self.assertRaises(AssertionError):wr(c,cycle+1,address=CS[0][0])

class HostControls(unittest.TestCase):
    def boot(self,mutation=None):
        h=HostChecker(BASE)
        for cycle in range(1,11):h.process(cycle,0,BASE,frame(),False)
        h.reset_transition(10,'falling')
        for cycle in range(11,21):h.process(cycle,1,BASE,frame(),False)
        cycle=20
        for index,(kind,address,value) in enumerate(h.expected):
            if index==5:
                for _ in range(10):cycle+=1;h.process(cycle,1,BASE,frame(),True)
            p=addr(address,0,2);p['prot']=0
            f=frame(ar=p) if kind=='r' else frame(aw=p,w=dict(data=value<<(8*(address&15)),strb=15<<(address&15),last=1))
            if mutation:mutation(index,f)
            cycle+=1;h.process(cycle,1,BASE,f,index>=4)
            r=frame(r=dict(id=0,data=value<<(8*(address&15)),resp=0,last=1)) if kind=='r' else frame(b=dict(id=0,resp=0))
            cycle+=1;h.process(cycle,1,BASE,r,index>=4)
        h.finish();return h,cycle
    def test_complete_host_sequence(self):self.boot()
    def test_short_reset_bad_phase_moving_boot(self):
        for n,phase in ((9,'falling'),(10,'rising')):
            h=HostChecker(BASE)
            for cycle in range(n):h.process(cycle,0,BASE,frame(),False)
            with self.assertRaises(AssertionError):h.reset_transition(n,phase)
        with self.assertRaises(AssertionError):HostChecker(BASE).process(1,0,BASE+4,frame(),False)
    def test_wrong_strobe_address_value(self):
        for field,value in (('strb',15),('data',1)):
            def bad(index,s):
                if index==2:s['w']['p'][field]=value
            with self.assertRaises(AssertionError):self.boot(bad)
        def bad(index,s):
            if index==0:s['ar']['p']['addr']=0
        with self.assertRaises(AssertionError):self.boot(bad)
    def test_postrelease_host_access(self):
        h,cycle=self.boot();p=addr(0x200000,0,2);p['prot']=0
        with self.assertRaises(AssertionError):h.process(cycle+1,1,BASE,frame(ar=p),True)

class ProbeReadbackControls(unittest.TestCase):
    def test_prewrite_read_has_no_readback_credit(self):
        c=chk();c.mem[PROBE+1-BASE]=0xa5
        c.process(1,frame(ar=addr(PROBE+1,0,0)),S)
        c.process(2,frame(r=dict(id=0,data=0xa5<<8,resp=0,last=1)),S)
        self.assertFalse(c.probe_reads)
        c.process(3,frame(aw=addr(PROBE+1,0,0),w=dict(data=0x5a<<8,strb=2,last=1)),S)
        c.process(4,frame(b=dict(id=0,resp=0)),S)
        self.assertFalse(c.probe_reads)
        c.process(5,frame(ar=addr(PROBE+1,0,0)),S)
        c.process(6,frame(r=dict(id=0,data=0x5a<<8,resp=0,last=1)),S)
        self.assertEqual(c.probe_reads,{(PROBE+1,0)})
    def test_correct_width_but_wrong_stored_value_no_credit(self):
        c=chk();c.process(1,frame(aw=addr(PROBE+1,0,0),w=dict(data=0x33<<8,strb=2,last=1)),S)
        c.process(2,frame(b=dict(id=0,resp=0)),S);c.process(3,frame(ar=addr(PROBE+1,0,0)),S)
        c.process(4,frame(r=dict(id=0,data=0x33<<8,resp=0,last=1)),S);self.assertFalse(c.probe_reads)
if __name__=='__main__':unittest.main()
