import time
from random import *
from theano import config
from theano.tensor.shared_randomstreams import RandomStreams
import theano
from theano import tensor
import theano.tensor as T
import scipy.stats as meas
import numpy as np

from alternative_trains.SiameseLSTM import *
from util_files.general_utils import init_tparams, numpy_floatX
from util_files.data_utils import prepare_sent_pairs_data, embed_sentence
from util_files.positive_expansion import expand_positive_examples
from util_files.nn_utils import getpl2, adadelta
from util_files.Constants import data_folder, models_folder


def chkterr2(mydata):
    count=[]
    num=len(mydata)
    px=[]
    yx=[]
    use_noise.set_value(0.)
    for i in range(0,num,256):
        q=[]
        x=i+256
        if x>num:
            x=num
        for j in range(i,x):
            q.append(mydata[j])
        x1,mas1,x2,mas2,y2=prepare_sent_pairs_data(q)
        ls=[]
        ls2=[]
        for j in range(0,len(q)):
            ls.append(embed_sentence(x1[j]))
            ls2.append(embed_sentence(x2[j]))
        trconv=np.dstack(ls)
        trconv2=np.dstack(ls2)
        emb2=np.swapaxes(trconv2,1,2)
        emb1=np.swapaxes(trconv,1,2)
        pred=(f2sim(emb1,mas1,emb2,mas2))*4.0+1.0
        #dm1=np.ones(mas1.shape,dtype=np.float32)
        #dm2=np.ones(mas2.shape,dtype=np.float32)
        #corr=f_cost(emb1,mas1,emb2,mas2,y2)
        for z in range(0,len(q)):
            yx.append(y2[z])
            px.append(pred[z])
    #count.append(corr)
    px=np.array(px)
    yx=np.array(yx)
    #print "average error= "+str(np.mean(acc))
    return np.mean(np.square(px-yx)),meas.pearsonr(px,yx)[0],meas.spearmanr(yx,px)[0]


def train_lstm(train,max_epochs):
    print "Training"
    crer=[]
    cr=1.6
    freq=0
    batchsize=32
    dfreq=40#display frequency
    valfreq=800# Validation frequency
    lrate=0.0001
    precision=2
    for eidx in xrange(0,max_epochs):
        sta=time.time()
        num=len(train)
        nd=eidx
        sta=time.time()
        print 'Epoch',eidx
        rnd=sample(xrange(len(train)),len(train))
        for i in range(0,num,batchsize):
            q=[]
            x=i+batchsize
            if x>num:
                x=num
            for z in range(i,x):
                q.append(train[rnd[z]])
            #q=train[i:i+32]
            #shuffle(q)
            x1,mas1,x2,mas2,y2=prepare_sent_pairs_data(q)
            
            ls=[]
            ls2=[]
            freq+=1
            use_noise.set_value(1.)
            for j in range(0,len(x1)):
                ls.append(embed_sentence(x1[j]))
                ls2.append(embed_sentence(x2[j]))
            trconv=np.dstack(ls)
            trconv2=np.dstack(ls2)
            emb2=np.swapaxes(trconv2,1,2)
            emb1=np.swapaxes(trconv,1,2)
            cst=f_grad_shared(emb2, mas2, emb1,mas1,y2)
            s=f_update(lrate)
            ls=[]
            ls2=[]
            freq+=1
            use_noise.set_value(1.)
            
            #s=f_update(lrate)
            if np.mod(freq,dfreq)==0:
                print 'Epoch ', eidx, 'Update ', freq, 'Cost ', cst
        sto=time.time()
        print "epoch took:",sto-sta


training = True  # Set to false to load weights
Syn_aug = True  # it False faster but does slightly worse on Test dataset


print training
newp=creatrnnx()
for i in newp.keys():
    if i[0]=='1':
        newp['2'+i[1:]]=newp[i]
y = tensor.vector('y', dtype=config.floatX)
mask11 = tensor.matrix('mask11', dtype=config.floatX)
mask21 = tensor.matrix('mask21', dtype=config.floatX)
emb11=theano.tensor.ftensor3('emb11')
emb21=theano.tensor.ftensor3('emb21')
if not training:
    newp=pickle.load(open(models_folder + "bestsem.p",'rb'))
tnewp=init_tparams(newp)
trng = RandomStreams(1234)
use_noise = theano.shared(numpy_floatX(0.))

rate=0.5
rrng=trng.binomial(emb11.shape,p=1-rate, n=1,dtype=emb11.dtype)

proj11=getpl2(emb11,'1lstm1',mask11,False,rrng,50,tnewp)[-1]
proj21=getpl2(emb21,'2lstm1',mask21,False,rrng,50,tnewp)[-1]
dif=(proj21-proj11).norm(L=1,axis=1)
s2=T.exp(-dif)
sim=T.clip(s2,1e-7,1.0-1e-7)
lr = tensor.scalar(name='lr')
ys=T.clip((y-1.0)/4.0,1e-7,1.0-1e-7)
cost=T.mean((sim - ys) ** 2)
ns=emb11.shape[1]
f2sim=theano.function([emb11,mask11,emb21,mask21],sim,allow_input_downcast=True)
f_cost=theano.function([emb11,mask11,emb21,mask21,y],cost,allow_input_downcast=True)
if training:
    
    gradi = tensor.grad(cost, wrt=tnewp.values())#/bts
    grads=[]
    l=len(gradi)
    for i in range(0,l/2):
        gravg=(gradi[i]+gradi[i+l/2])/(2.0)
        #print i,i+9
        grads.append(gravg)
    for i in range(0,len(tnewp.keys())/2):
        grads.append(grads[i])
    
    f_grad_shared, f_update = adadelta(lr, tnewp, grads,emb11,mask11,emb21,mask21,y, cost)


train=pickle.load(open(data_folder + "stsallrmf.p","rb"))#[:-8]
if training:
    print "Pre-training"
    train_lstm(train,66)
    print "Pre-training done"
    train=pickle.load(open(data_folder + "semtrain.p",'rb'))
    if Syn_aug:
        train=expand_positive_examples(train, ignore_flag=False)
        train_lstm(train,375)
    else:
        train_lstm(train,330)

test=pickle.load(open(data_folder + "semtest.p",'rb'))
print chkterr2(test)

#Example
q=[["A truly wise man","He is smart",0]]

x1,mas1,x2,mas2,y2=prepare_sent_pairs_data(q)
ls=[]
ls2=[]
for j in range(0,len(q)):
    ls.append(embed_sentence(x1[j]))
    ls2.append(embed_sentence(x2[j]))
trconv=np.dstack(ls)
trconv2=np.dstack(ls2)
emb2=np.swapaxes(trconv2,1,2)
emb1=np.swapaxes(trconv,1,2)
pred=(f2sim(emb1,mas1,emb2,mas2))*4.0+1.0
print "Similarity of "
print q[0][0],q[0][1]
print "on a scale of 1-5" +str(pred[0])

