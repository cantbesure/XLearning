import numpy as np
import logging

# Here we import LogWriter so that we can write log data while MXNet is training
from visualdl import LogWriter

import mxnet as mx

import os
import gzip, struct

# load mnist data
def read_data(label_url, image_url):
    with gzip.open(os.path.join('data',label_url)) as flbl:
        struct.unpack(">II", flbl.read(8))
        label = np.fromstring(flbl.read(), dtype=np.int8)
    with gzip.open(os.path.join('data',image_url), 'rb') as fimg:
        _, _, rows, cols = struct.unpack(">IIII", fimg.read(16))
        image = np.fromstring(fimg.read(), dtype=np.uint8).reshape(len(label), rows, cols)
        image = image.reshape(image.shape[0], 1, 28, 28).astype(np.float32)/255
    return (label, image)

(train_lbl, train_img) = read_data(
        'train-labels-idx1-ubyte.gz', 'train-images-idx3-ubyte.gz')
(test_lbl, test_img) = read_data(
        't10k-labels-idx1-ubyte.gz', 't10k-images-idx3-ubyte.gz')

mnist = {'train_data':train_img, 'train_label':train_lbl,
            'test_data':test_img, 'test_label':test_lbl}


batch_size = 100


# Provide a folder to store data for log, model, image, etc. VisualDL's visualization will be
# based on this folder.
logdir = "./log"

# Initialize a logger instance. Parameter 'sync_cycle' means write a log every 10 operations on
# memory.
logger = LogWriter(logdir, sync_cycle=10)

# mark the components with 'train' label.
with logger.mode("train"):
    # scalar0 is used to record scalar metrics while MXNet is training. We will record accuracy.
    # In the visualization, we can see the accuracy is increasing as more training steps happen.
    scalar0 = logger.scalar("scalars/scalar0")
    image0 = logger.image("images/image0", 1)
    histogram0 = logger.histogram("histogram/histogram0", num_buckets=100)

# Record training steps
cnt_step = 0


# MXNet provides many callback interface. Here we define our own callback method and it is called
# after every batch.
# https://mxnet.incubator.apache.org/api/python/callback/callback.html
def add_scalar():
    def _callback(param):
        with logger.mode("train"):
            global cnt_step
            # Here the value is the accuracy we want to record
            # https://mxnet.incubator.apache.org/_modules/mxnet/callback.html
            name_value = param.eval_metric.get_name_value()
            for name, value in name_value:
                scalar0.add_record(cnt_step, value)
                cnt_step += 1
    return _callback

def add_image_histogram():
    def _callback(iter_no, sym, arg, aux):
        image0.start_sampling()
        weight = arg['fullyconnected1_weight'].asnumpy()
        shape = [100, 50]
        data = weight.flatten()

        image0.add_sample(shape, list(data))
        histogram0.add_record(iter_no, list(data))

        image0.finish_sampling()
    return _callback


# Start to build CNN in MXNet, train MNIST dataset. For more info, check MXNet's official website:
# https://mxnet.incubator.apache.org/tutorials/python/mnist.html

logging.getLogger().setLevel(logging.DEBUG)  # logging to stdout

train_iter = mx.io.NDArrayIter(mnist['train_data'], mnist['train_label'], batch_size, shuffle=True)
val_iter = mx.io.NDArrayIter(mnist['test_data'], mnist['test_label'], batch_size)

data = mx.sym.var('data')
# first conv layer
conv1 = mx.sym.Convolution(data=data, kernel=(5, 5), num_filter=20)
tanh1 = mx.sym.Activation(data=conv1, act_type="tanh")
pool1 = mx.sym.Pooling(data=tanh1, pool_type="max", kernel=(2, 2), stride=(2, 2))
# second conv layer
conv2 = mx.sym.Convolution(data=pool1, kernel=(5, 5), num_filter=50)
tanh2 = mx.sym.Activation(data=conv2, act_type="tanh")
pool2 = mx.sym.Pooling(data=tanh2, pool_type="max", kernel=(2, 2), stride=(2, 2))
# first fullc layer
flatten = mx.sym.flatten(data=pool2)
fc1 = mx.symbol.FullyConnected(data=flatten, num_hidden=500)
tanh3 = mx.sym.Activation(data=fc1, act_type="tanh")
# second fullc
fc2 = mx.sym.FullyConnected(data=tanh3, num_hidden=10)
# softmax loss
lenet = mx.sym.SoftmaxOutput(data=fc2, name='softmax')

# create a trainable module on CPU
lenet_model = mx.mod.Module(symbol=lenet, context=mx.cpu())

model_prefix = 'output/mx_mlp'
checkpoint = mx.callback.do_checkpoint(model_prefix)

# train with the same
lenet_model.fit(train_iter,
                eval_data=val_iter,
                optimizer='sgd',
                optimizer_params={'learning_rate': 0.1},
                eval_metric='acc',
                # integrate our customized callback method
                batch_end_callback=[add_scalar()],
                epoch_end_callback=[add_image_histogram(), checkpoint],
                num_epoch=2)

test_iter = mx.io.NDArrayIter(mnist['test_data'], None, batch_size)
prob = lenet_model.predict(test_iter)
test_iter = mx.io.NDArrayIter(mnist['test_data'], mnist['test_label'], batch_size)

# predict accuracy for lenet
acc = mx.metric.Accuracy()
lenet_model.score(test_iter, acc)
print(acc)
