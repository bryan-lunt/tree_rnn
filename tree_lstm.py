__doc__ = """Implementation of Tree LSTMs described in http://arxiv.org/abs/1503.00075"""

import tree_rnn

import theano
from theano import tensor as T


class ChildSumTreeLSTM(tree_rnn.TreeRNN):
    def create_recursive_unit(self):
        self.W_i = theano.shared(self.init_matrix([self.emb_dim, self.emb_dim]))
        self.U_i = theano.shared(self.init_matrix([self.emb_dim, self.emb_dim]))
        self.b_i = theano.shared(self.init_vector([self.emb_dim]))
        self.W_f = theano.shared(self.init_matrix([self.emb_dim, self.emb_dim]))
        self.U_f = theano.shared(self.init_matrix([self.emb_dim, self.emb_dim]))
        self.b_f = theano.shared(self.init_vector([self.emb_dim]))
        self.W_o = theano.shared(self.init_matrix([self.emb_dim, self.emb_dim]))
        self.U_o = theano.shared(self.init_matrix([self.emb_dim, self.emb_dim]))
        self.b_o = theano.shared(self.init_vector([self.emb_dim]))
        self.W_u = theano.shared(self.init_matrix([self.emb_dim, self.emb_dim]))
        self.U_u = theano.shared(self.init_matrix([self.emb_dim, self.emb_dim]))
        self.b_u = theano.shared(self.init_vector([self.emb_dim]))
        self.params.extend([
            self.W_i, self.U_i, self.b_i,
            self.W_f, self.U_f, self.b_f,
            self.W_o, self.U_o, self.b_o,
            self.W_u, self.U_u, self.b_u])

        def unit(parent_x, child_h, child_c, child_exists):
            h_tilde = T.sum(child_h, axis=0)
            i = T.nnet.sigmoid(T.dot(self.W_i, parent_x) + T.dot(self.U_i, h_tilde) + self.b_i)
            o = T.nnet.sigmoid(T.dot(self.W_o, parent_x) + T.dot(self.U_o, h_tilde) + self.b_o)
            u = T.tanh(T.dot(self.W_u, parent_x) + T.dot(self.U_u, h_tilde) + self.b_u)

            f = (T.nnet.sigmoid(
                    T.dot(self.W_f, parent_x).dimshuffle('x', 0) +
                    T.dot(child_h, self.U_f.T) +
                    self.b_f.dimshuffle('x', 0)) *
                 child_exists.dimshuffle(0, 'x'))

            c = i * u + T.sum(f * child_c, axis=0)
            h = o * c
            return h, c

        return unit

    def create_leaf_unit(self):
        self.h0 = theano.shared(self.init_vector([self.hidden_dim]))
        self.c0 = theano.shared(self.init_vector([self.hidden_dim]))
        self.params.extend([self.h0, self.c0])
        dummy = 1 + 0 * theano.shared(self.init_vector([1]))
        def unit(leaf_x):
            return self.recursive_unit(
                leaf_x,
                self.h0.reshape([1, self.hidden_dim]),
                self.c0.reshape([1, self.hidden_dim]),
                dummy)
        return unit

    def compute_tree(self, emb_x, tree):
        self.recursive_unit = self.create_recursive_unit()
        self.leaf_unit = self.create_leaf_unit()
        num_nodes = tree.shape[0]  # num internal nodes
        num_leaves = self.num_words - num_nodes

        # compute leaf hidden states
        (node_h, node_c), _ = theano.map(
            fn=self.leaf_unit,
            sequences=[emb_x[:num_leaves]])

        # use recurrence to compute internal node hidden states
        def _recurrence(cur_emb, node_info, t, node_h, node_c, last_h):
            child_exists = node_info > -1
            child_h = node_h[node_info - child_exists * t] * child_exists.dimshuffle(0, 'x')
            child_c = node_c[node_info - child_exists * t] * child_exists.dimshuffle(0, 'x')
            parent_h, parent_c = self.recursive_unit(cur_emb, child_h, child_c, child_exists)
            node_h = T.concatenate([node_h,
                                    parent_h.reshape([1, self.hidden_dim])])
            node_c = T.concatenate([node_c,
                                    parent_c.reshape([1, self.hidden_dim])])
            return node_h[1:], node_c[1:], parent_h

        dummy = theano.shared(self.init_vector([self.hidden_dim]))
        (_, _, parent_h), _ = theano.scan(
            fn=_recurrence,
            outputs_info=[node_h, node_c, dummy],
            sequences=[emb_x[num_leaves:], tree, T.arange(num_nodes)],
            n_steps=num_nodes)

        return parent_h[-1]