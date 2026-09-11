"""Independent public subordinate/reset observer; CNEM-03/04/09/10."""
from checker import require
class HostChecker:
    def __init__(self,entry):
        self.entry=entry;self.low_edges=0;self.first_high=None;self.prev={};self.pending=None;self.aw=None;self.w=None;self.index=0;self.release=None;self.reset1=None
        self.expected=[('r',0x200000,3),('r',0x200004,entry),('w',0x200004,entry),('r',0x200004,entry),('w',0x200000,1),('w',0x200000,0)]
    def reset_transition(self,cycle,phase):
        require(phase=='falling' and self.low_edges>=10,'CNEM-09 reset release phase/length')
    def process(self,cycle,reset,boot,snapshot,locked):
        require(boot==self.entry,'CNEM-09 boot address changed')
        if not reset:
            require(self.first_high is None,'unexpected reset in positive profile');self.low_edges+=1
            require(not any(s['valid'] for s in snapshot.values()),'CNEM-09 traffic during reset');return
        if self.first_high is None:
            require(self.low_edges>=10,'CNEM-09 short reset');self.first_high=cycle
        for ch,s in snapshot.items():
            old=self.prev.get(ch)
            if old and old['valid'] and not old['ready']:require(s['valid'] and s['p']==old['p'],'host '+ch+' unstable while stalled')
            self.prev[ch]=s
        hs={k:s['p'] for k,s in snapshot.items() if s['valid'] and s['ready']}
        if any(snapshot[k]['valid'] for k in ('ar','aw','w')):
            require(cycle-self.first_high>=10,'CNEM-09 early CSR');require(self.release is None,'CNEM-10 host traffic after release')
        for k in ('ar','aw'):
            if snapshot[k]['valid']:
                p=snapshot[k]['p'];require(all(p[f]==v for f,v in dict(id=0,len=0,size=2,burst=1,prot=0,lock=0,cache=0,qos=0,region=0).items()),'CNEM-10 host address attributes')
        # Response requires a prior request/pair; same-edge response is excluded.
        for k in ('r','b'):
            if snapshot[k]['valid']:
                q=self.pending;require(q is not None and cycle>q['cycle'],'host unsolicited/early response')
                require(k==('r' if q['kind']=='r' else 'b'),'host response kind')
                p=snapshot[k]['p'];require(p['id']==0 and p['resp']==0,'CNEM-10 host response ID/status')
                if k=='r':require(p['last']==1 and ((p['data']>>(8*(q['addr']&15)))&0xffffffff)==q['value'],'CNEM-10 CSR readback')
        if 'r' in hs or 'b' in hs:
            q=self.pending
            if self.index==4:self.reset1=cycle
            if self.index==5:self.release=cycle
            self.pending=None;self.index+=1
        for k in ('ar','aw'):
            if k in hs:
                require(self.pending is None and self.aw is None,'CNEM-10 host outstanding bound')
                p=hs[k];kind,address,value=self.expected[self.index]
                require(kind==('r' if k=='ar' else 'w') and p['addr']==address,'CNEM-10 CSR order/address')
                if self.index>=4:require(locked,'CNEM-08 loading not locked before release')
                if self.index==5:require(cycle-self.reset1>=10,'CNEM-10 reset hold interval')
                q=dict(kind=kind,addr=address,value=value,cycle=cycle)
                if k=='ar':self.pending=q
                else:self.aw=q
        if 'w' in hs:
            require(self.w is None and self.pending is None,'host W outstanding');self.w={**hs['w'],'cycle':cycle}
        if self.aw is not None and self.w is not None:
            q,w=self.aw,self.w;lane=q['addr']&15
            require(w['last']==1 and w['strb']==15<<lane and w['data']==q['value']<<(8*lane),'CNEM-10 CSR W lane/strobe/value')
            q['cycle']=max(q['cycle'],w['cycle']);self.pending=q;self.aw=self.w=None
    def finish(self):require(self.index==6 and self.release is not None,'CNEM-10 incomplete boot sequence')
