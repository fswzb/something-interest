"""
use softmax regression and read data from mongodb
"""
import logging

import numpy as np
import tensorflow as tf

from v3.config.config import Option
from v3.db.db_service.read_mongodb import ReadDB
from v3.service.data_preprocess import DataPreprocess
from v3.service.load_all_code import load_all_code
from v3.service.mini_batch import batch

logging.basicConfig(level=logging.DEBUG,
                format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                datefmt='%b %d %Y %H:%M:%S',
                filename='/home/daiab/log/quantlog.log',
                filemode='w')
logger = logging.getLogger(__name__)


class LstmModel:
    def __init__(self, session):
        self._session = session
        self._option = Option()

        self.all_stock_code = load_all_code()
        self.read_db = ReadDB(data_preprocess=DataPreprocess(self._option.time_step))

    def update_data(self, code):
        self.read_db.read_one_stock_data(code)
        self.train_data = self.read_db.data_preprocess.train_data
        self.target = self.read_db.data_preprocess.target
        self.softmax = self.read_db.data_preprocess.softmax
        total_days = self.read_db.data_preprocess.date_time_range.shape[0]
        test_days = (int)(total_days / 50)

        date_time_range = self.read_db.data_preprocess.date_time_range
        np.random.shuffle(date_time_range)

        self.train_date_range = date_time_range[:(total_days - test_days)]
        self.test_date_range = date_time_range[(total_days - test_days):]

    def get_one_epoch_train_data(self, day):
        return self.train_data.loc[day].values

    def get_one_epoch_softmax(self, day):
        return self.softmax.loc[day].values

    def build_graph(self):
        option = self._option
        self.one_train_data = tf.placeholder(tf.float32, [None, option.time_step, 4])
        self.target_data = tf.placeholder(tf.float32, [None, 2])
        cell = tf.nn.rnn_cell.BasicLSTMCell(option.hidden_cell_num, forget_bias=option.forget_bias,
                                            input_size=[option.batch_size, option.time_step, option.hidden_cell_num])
        cell = tf.nn.rnn_cell.DropoutWrapper(cell, input_keep_prob=1.0, output_keep_prob=option.rnn_keep_prop)

        cell_2 = tf.nn.rnn_cell.MultiRNNCell([cell] * option.hidden_layer_num)
        val, self.states = tf.nn.dynamic_rnn(cell_2, self.one_train_data, dtype=tf.float32)

        # val = tf.transpose(val, [1, 0, 2])
        # self.val = tf.gather(val, val.get_shape()[0] - 1)
        dim = option.time_step * option.hidden_cell_num
        self.val = tf.reshape(val, [-1, dim])

        self.weight = tf.Variable(tf.truncated_normal([dim, option.output_cell_num], dtype=tf.float32), name='weight')
        self.bias = tf.Variable(tf.constant(0.0, dtype=tf.float32, shape=[1, option.output_cell_num]), name='bias')

        tmp_value = tf.nn.relu(tf.matmul(self.val, self.weight) + self.bias)
        tmp_value = tf.nn.dropout(tmp_value, keep_prob=option.hidden_layer_keep_prop)
        self.weight_2 = tf.Variable(tf.truncated_normal([option.output_cell_num, 2], dtype=tf.float32), name='weight_2')
        self.bias_2 = tf.Variable(tf.constant(0.0, dtype=tf.float32, shape=[1, 2]), name='bias_2')

        self.predict_target = tf.matmul(tmp_value, self.weight_2) + self.bias_2
        # self.predict_target = tf.nn.relu(tf.matmul(tmp_value, self.weight_2) + self.bias_2)

        self.cross_entropy = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(self.predict_target, self.target_data))
        self.minimize = tf.train.AdamOptimizer(learning_rate=option.learning_rate).minimize(self.cross_entropy)
        self._session.run(tf.initialize_all_variables())
        self.saver = tf.train.Saver()

    def train_model(self):
        option = self._option
        for i in range(len(self.all_stock_code)):
            code = self.all_stock_code.pop(0)
            self.update_data(code)
            """每次进入新的code时，重新init所有参数，开始全新一轮"""
            # self._session.run(tf.initialize_all_variables())
            # self.saver = tf.train.Saver()

            for epoch in range(option.epochs):
                logger.info("stockCode == %d, epoch == %d", code, epoch)
                batch_data = batch(batch_size=option.batch_size,
                                   data=self.train_data.loc[self.train_date_range].values,
                                   target=self.target.loc[self.train_date_range].values,
                                   softmax=self.softmax.loc[self.train_date_range].values, shuffle=True)
                feed_dict = {}
                for one_train_data, _, softmax in batch_data:
                    feed_dict = {self.one_train_data: one_train_data, self.target_data: softmax}
                    self._session.run(self.minimize, feed_dict=feed_dict)
                    # print(self._session.run(self.val, feed_dict=feedDict).shape)

                if len(feed_dict) != 0:
                    crossEntropy = self._session.run(self.cross_entropy, feed_dict=feed_dict)
                    logger.info("crossEntropy == %f", crossEntropy)
                self.test()

            if option.is_save_file:
                self.saver.save(self._session, "/home/daiab/ckpt/code-%s.ckpt" % code)
                logger.info("save file code-%s", code)
        if option.loop_time > 1:
            logger.info("loop time == %d" % option.loop_time)
            option.loop_time -= 1
            self.all_stock_code = load_all_code()
            self.train_model()

    def test(self):
        count_arr, right_arr, prop_step_arr = np.zeros(6), np.zeros(6), np.array([0.5, 0.6, 0.7, 0.8, 0.9, 0.95])
        logger.info("test begin ......")
        for day in self.test_date_range:
            train = [self.get_one_epoch_train_data(day)]
            real = self.get_one_epoch_softmax(day)

            predict = self._session.run(self.predict_target, feed_dict={self.one_train_data: train})
            predict = np.exp(predict)
            probability = predict / predict.sum()

            max = probability[0][0] if probability[0][0] > probability[0][1] else probability[0][1]
            tmp_bool_index = prop_step_arr <= max
            count_arr[tmp_bool_index] = count_arr[tmp_bool_index] + 1
            if np.argmax(predict) == np.argmax(real):
                right_arr[tmp_bool_index] = right_arr[tmp_bool_index] + 1

        logger.info("test ratio >>>>> %s", right_arr/count_arr)



def run():
    with tf.Graph().as_default(), tf.Session() as session:
        lstmModel = LstmModel(session)
        lstmModel.build_graph()
        lstmModel.train_model()
        session.close()
        lstmModel.read_db.destory()

if __name__ == '__main__':
    run()



