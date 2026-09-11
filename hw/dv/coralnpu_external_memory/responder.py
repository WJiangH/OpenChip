"""Independent CNEM-13--18 simulation environment; no DUT implementation imports."""
import random
from collections import Counter
from checker import BASE,END,require
class Responder:
    def __init__(self,image,schedule,seed):
        self.memory=bytearray(image); self.locked=False; self.schedule=schedule
        self.rng={k:random.Random(seed+off) for k,off in [('ar',101),('aw',211),('w',307),('r',401),('b',503)]}
        self.cool={k:0 for k in ('ar','aw','w')}; self.ar=[]; self.aw=[]; self.w=[]; self.b=[]
        self.active_r=None; self.active_b=None; self.events=[]; self.counts=Counter()
    def host_write(self,address,data):
        require(not self.locked,'CNEM-08 host write after initialization lock')
        self.memory[address-BASE:address-BASE+len(data)]=data
    def delay(self,k):
        value=1 if self.schedule=='P0' else self.rng[k].randint(1,15)
        self.counts[k+'_delay_'+str(value)]+=1
        return value
    def outputs(self,cycle):
        if self.active_r is None:
            eligible=[q for q in self.ar if q['due']<=cycle]
            if eligible:
                self.active_r=min(eligible,key=lambda q:(q['due'],q['id']))
                self.ar.remove(self.active_r)
        if self.active_b is None and self.b and self.b[0]['due']<=cycle: self.active_b=self.b.pop(0)
        out={k:{'ready':int(self.cool[k]==0)} for k in self.cool}
        out['r']={'valid':int(self.active_r is not None),'p':self.active_r['p'] if self.active_r else {'data':0,'id':0,'resp':0,'last':0}}
        out['b']={'valid':int(self.active_b is not None),'p':self.active_b['p'] if self.active_b else {'id':0,'resp':0}}
        return out
    def advance(self,cycle,snapshot):
        for k in self.cool:
            if self.cool[k]: self.cool[k]-=1
            else: self.cool[k]=0 if self.schedule=='P0' else self.rng[k].randint(0,7)
        hs={k:s['p'] for k,s in snapshot.items() if s['valid'] and s['ready']}
        if 'r' in hs: self.active_r=None
        if 'b' in hs: self.active_b=None
        if 'ar' in hs:
            p=hs['ar']; data=0; resp=0
            if not BASE<=p['addr']<END: resp=3
            else:
                lane=p['addr']%16
                chunk=self.memory[p['addr']-BASE:p['addr']-BASE+(1<<p['size'])]
                data=int.from_bytes(chunk,'little')<<(lane*8)
            self.ar.append({'id':p['id'],'due':cycle+self.delay('r'),'p':{'id':p['id'],'data':data,'resp':resp,'last':1}})
        if 'aw' in hs: self.aw.append(hs['aw'])
        if 'w' in hs: self.w.append(hs['w'])
        if self.aw and self.w:
            a=self.aw.pop(0); w=self.w.pop(0); resp=0
            if not BASE<=a['addr']<END: resp=3
            else:
                base=(a['addr']&~15)-BASE
                raw=w['data'].to_bytes(16,'little')
                for lane in range(16):
                    if w['strb']&(1<<lane): self.memory[base+lane]=raw[lane]
            self.b.append({'due':cycle+self.delay('b'),'p':{'id':a['id'],'resp':resp}})
