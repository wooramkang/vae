import tensorflow as tf
import numpy as np
import time
import matplotlib.pyplot as plt
from scipy.stats import norm

from tensorflow.examples.tutorials.mnist import input_data


class VAE(object):
    def __init__(self, n_batch=100, n_input=784, n_latent=2, n_hidden=500, learning_rate=0.001,
                 stddev_init=0.1, weight_decay_factor=0, n_step=10**6, seed=0, activation=tf.tanh,
                 checkpoint_path='model.ckpt'):
        self.n_batch = n_batch
        self.n_input = n_input
        self.n_latent = n_latent
        self.n_hidden = n_hidden
        self.learning_rate = learning_rate
        self.stddev_init = stddev_init
        self.weight_decay_factor = weight_decay_factor
        self.n_step = n_step
        self.seed = seed
        self.checkpoint_path = checkpoint_path
        self.activation = activation

    def _create_graph(self):
        np.random.seed(self.seed)
        tf.set_random_seed(self.seed)

        with tf.Graph().as_default() as graph:
            self.loss = self._create_model()
            self.optimizer = self._create_optimizer(self.loss, self.learning_rate)
            self.initializer = tf.global_variables_initializer()
            self.saver = tf.train.Saver()
            graph.finalize()
        return graph

    def _create_weights(self, shape):
        W = tf.Variable(tf.random_normal(shape, stddev=self.stddev_init))
        b = tf.Variable(np.zeros([shape[0], shape[1], 1]).astype(np.float32))
        return W, b

    def _create_weight_decay(self):
        if self.weight_decay_factor > 0:
            return self.weight_decay_factor / 2.0 * tf.reduce_sum([tf.nn.l2_loss(v) for v in tf.trainable_variables()])
        else:
            return 0

    def _create_encoder(self, x):
        with tf.variable_scope('encoder'):
            W3, b3 = self._create_weights([self.n_batch, self.n_hidden, self.n_input])
            W4, b4 = self._create_weights([self.n_batch, self.n_latent, self.n_hidden])
            W5, b5 = self._create_weights([self.n_batch, self.n_latent, self.n_hidden])

            h = self.activation(W3 @ x + b3)
            mu = W4 @ h + b4
            log_sigma_squared = W5 @ h + b5
            sigma_squared = tf.exp(log_sigma_squared)
            sigma = tf.sqrt(sigma_squared)
        return mu, log_sigma_squared, sigma_squared, sigma

    def _create_decoder(self, z):
        with tf.variable_scope('decoder'):
            W1, b1 = self._create_weights([self.n_batch, self.n_hidden, self.n_latent])
            W2, b2 = self._create_weights([self.n_batch, self.n_input, self.n_hidden])

            y_logit = W2 @ self.activation(W1 @ z + b1) + b2
            y = tf.sigmoid(y_logit)
        return y_logit, y

    def _create_model(self):
        self.x = tf.placeholder(tf.float32, [self.n_batch, self.n_input])
        x = tf.reshape(self.x, [self.n_batch, self.n_input, 1])
        mu, log_sigma_squared, sigma_squared, sigma = self._create_encoder(x)

        self.epsilon = tf.placeholder(tf.float32, self.n_latent)
        epsilon = tf.reshape(self.epsilon, [1, self.n_latent, 1])
        self.z = mu + sigma * epsilon
        y_logit, self.y = self._create_decoder(self.z)

        regularizer = -0.5 * tf.reduce_sum(1 + log_sigma_squared - tf.square(mu) - sigma_squared, 1)
        recon_error = tf.reduce_sum(tf.nn.sigmoid_cross_entropy_with_logits(logits=y_logit, labels=x), 1)
        weight_decay = self._create_weight_decay()
        loss = tf.reduce_mean(regularizer + recon_error) + weight_decay
        return loss

    def _create_optimizer(self, loss, learning_rate):
        self.current_step = tf.Variable(0, trainable=False)
        #optimizer = tf.train.AdagradOptimizer(learning_rate).minimize(loss, global_step=batch)
        optimizer = tf.train.AdamOptimizer(learning_rate).minimize(loss, global_step=self.current_step)
        return optimizer

    def fit(self, X, refit=False):
        graph = self._create_graph()
        session = tf.Session(graph=graph)
        coord = tf.train.Coordinator()
        threads = tf.train.start_queue_runners(session, coord)

        try:
            session.run(self.initializer) if not refit else self.saver.restore(session, self.checkpoint_path)
            initial_step = session.run(self.current_step)
            start = time.time()
            for step in range(initial_step, self.n_step):
                x = X.next_batch(self.n_batch)[0]
                epsilon = np.random.randn(self.n_latent).astype(np.float32)
                loss, _ = session.run([self.loss, self.optimizer], {self.x: x, self.epsilon: epsilon})

                if step % 100 == 0:
                    print('step: %d, mini-batch error: %1.4f, took %ds' % (step, loss, (time.time()-start)))
                    start = time.time()

        except KeyboardInterrupt:
            print('ending training')
        finally:
            self.saver.save(session, self.checkpoint_path)
            session.close()
            coord.request_stop()
            coord.join(threads)
            print('finished training')

    def _sample_2d_grid(self, grid_width):
        epsilon = norm.ppf(np.linspace(0, 1, grid_width + 2)[1:-1])
        epsilon_2d = np.dstack(np.meshgrid(epsilon, epsilon)).reshape(-1, 2)
        return epsilon_2d

    def decode(self, z, n_batch=None):
        graph = self._create_graph()
        with tf.Session(graph=graph) as session:
            self.saver.restore(session, self.checkpoint_path)
            n_iter = n_batch // self.n_batch if n_batch is not None else 1
            batch = lambda i: z[i * self.n_batch:(i + 1) * self.n_batch, :, np.newaxis]
            y = [session.run(self.y, {self.z: batch(i)}) for i in range(n_iter)]
        return y

    def mosaic(self, grid_width=20):
        z = self._sample_2d_grid(grid_width)
        w = int(np.sqrt(self.n_input))
        mos = np.bmat(np.reshape(self.decode(z, n_batch=grid_width ** 2), [grid_width, grid_width, w, w]).tolist())
        return mos

if __name__ == '__main__':
    data = input_data.read_data_sets('MNIST data')
    vae = VAE(activation=tf.nn.relu)
    vae.fit(data.train, refit=True)
    mosaic = vae.mosaic()
    plt.imshow(mosaic, cmap='gray')
    plt.axis('off')
    plt.show()