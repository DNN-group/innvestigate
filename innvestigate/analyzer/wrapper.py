# Begin: Python 2/3 compatibility header small
# Get Python 3 functionality:
from __future__ import\
    absolute_import, print_function, division, unicode_literals
from future.utils import raise_with_traceback, raise_from
# catch exception with: except Exception as e
from builtins import range, map, zip, filter
from io import open
import six
# End: Python 2/3 compatability header small


###############################################################################
###############################################################################
###############################################################################


import keras.models
import keras.backend as K
import numpy as np


from . import base
from .. import layers as ilayers
from .. import utils as iutils
from ..utils import keras as kutils


__all__ = [
    "WrapperBase",
    "AugmentReduceBase",
    "GaussianSmoother",
    "PathIntegrator",
]


###############################################################################
###############################################################################
###############################################################################


class WrapperBase(base.AnalyzerBase):

    def __init__(self, subanalyzer, *args, **kwargs):
        self._subanalyzer = subanalyzer
        model = None

        super(WrapperBase, self).__init__(model,
                                          *args, **kwargs)

    def analyze(self, *args, **kwargs):
        return self._subanalyzer.analyze(*args, **kwargs)

    def _get_state(self):
        sa_class_name, sa_state = self._subanalyzer.save()

        state = {}
        state.update({"subanalyzer_class_name": sa_class_name})
        state.update({"subanalyzer_state": sa_state})
        return state

    @classmethod
    def _state_to_kwargs(clazz, state):
        sa_class_name = state.pop("subanalyzer_class_name")
        sa_state = state.pop("subanalyzer_state")
        assert len(state) == 0

        subanalyzer = base.AnalyzerBase.load(sa_class_name, sa_state)
        kwargs = {"subanalyzer": subanalyzer}
        return kwargs


###############################################################################
###############################################################################
###############################################################################


class AugmentReduceBase(WrapperBase):

    def __init__(self, subanalyzer, *args, **kwargs):
        self._augment_by_n = kwargs.pop("augment_by_n", 2)
        super(AugmentReduceBase, self).__init__(subanalyzer,
                                                *args, **kwargs)

        self._keras_based_augment_reduce = False
        if isinstance(self._subanalyzer, base.AnalyzerNetworkBase):
            # Take the keras analyzer model and
            # add augment and reduce functionality.
            self._keras_based_augment_reduce = True

    def compile_analyzer(self):
        if not self._keras_based_augment_reduce:
            return

        self._subanalyzer.compile_analyzer()

        if self._subanalyzer._n_debug_output > 0:
            raise Exception("No debug output at subanalyzer is supported.")

        model = self._subanalyzer._analyzer_model
        if None in model.input_shape[1:]:
            raise ValueError("The input shape for the model needs "
                             "to be fully specified (except the batch axis). "
                             "Model input shape is: %s" % (model.input_shape,))

        inputs = model.inputs[:self._subanalyzer._n_data_input]
        extra_inputs = model.inputs[self._subanalyzer._n_data_input:]
        # todo: check this, index seems not right.
        outputs = model.outputs[:self._subanalyzer._n_data_input]
        extra_outputs = model.outputs[self._subanalyzer._n_data_input:]

        if len(extra_outputs) > 0:
            raise Exception("No extra output is allowed "
                            "with this wrapper.")

        new_inputs = iutils.to_list(self._keras_based_augment(inputs))
        tmp = iutils.to_list(model(new_inputs))
        new_outputs = iutils.to_list(self._keras_based_reduce(tmp))
        new_constant_inputs = self._keras_get_constant_inputs()

        new_model = keras.models.Model(
            inputs=inputs+extra_inputs+new_constant_inputs,
            outputs=new_outputs+extra_outputs)
        new_model.compile(optimizer="sgd", loss="mse")
        self._subanalyzer._analyzer_model = new_model

    def analyze(self, X, *args, **kwargs):
        if self._keras_based_augment_reduce is True:
            if not hasattr(self._subanalyzer, "_analyzer_model"):
                self.compile_analyzer()
            return self._subanalyzer.analyze(X, *args, **kwargs)
        else:
            # todo: remove python based code.
            # also tests.
            raise DeprecationWarning("Not supported anymore.")
            return_list = isinstance(X, list)

            X = self._python_based_augment(iutils.to_list(X))
            ret = self._subanalyzer.analyze(X, *args, **kwargs)
            ret = self._python_based_reduce(ret)

            if return_list is True:
                return ret
            else:
                return ret[0]

    def _python_based_augment(self, X):
        return [np.repeat(x, self._augment_by_n, axis=0) for x in X]

    def _python_based_reduce(self, X):
        tmp = [x.reshape((-1, self._augment_by_n)+x.shape[1:]) for x in X]
        tmp = [x.mean(axis=1) for x in tmp]
        return tmp

    def _keras_get_constant_inputs(self):
        return list()

    def _keras_based_augment(self, X):
        repeat = ilayers.Repeat(self._augment_by_n, axis=0)
        return [repeat(x) for x in iutils.to_list(X)]

    def _keras_based_reduce(self, X):
        X_shape = [K.int_shape(x) for x in iutils.to_list(X)]
        reshape = [ilayers.Reshape((-1, self._augment_by_n)+shape[1:])
                   for shape in X_shape]
        mean = ilayers.Mean(axis=1)

        return [mean(reshape_x(x)) for x, reshape_x in zip(X, reshape)]

    def _get_state(self):
        state = super(AugmentReduceBase, self)._get_state()
        state.update({"augment_by_n": self._augment_by_n})
        return state

    @classmethod
    def _state_to_kwargs(clazz, state):
        augment_by_n = state.pop("augment_by_n")
        kwargs = super(AugmentReduceBase, clazz)._state_to_kwargs(state)
        kwargs.update({"augment_by_n": augment_by_n})
        return kwargs


###############################################################################
###############################################################################
###############################################################################


class GaussianSmoother(AugmentReduceBase):

    def __init__(self, subanalyzer, *args, **kwargs):
        self._noise_scale = kwargs.pop("noise_scale", 1)
        super(GaussianSmoother, self).__init__(subanalyzer,
                                               *args, **kwargs)

    def _python_based_augment(self, X):
        tmp = super(GaussianSmoother, self)._python_based_augment(X)
        ret = [x + np.random.normal(0, self._noise_scale, size=x.shape)
               for x in tmp]
        return ret

    def _keras_based_augment(self, X):
        tmp = super(GaussianSmoother, self)._keras_based_augment(X)
        noise = ilayers.TestPhaseGaussianNoise(stddev=self._noise_scale)
        return [noise(x) for x in tmp]

    def _get_state(self):
        state = super(GaussianSmoother, self)._get_state()
        state.update({"noise_scale": self._noise_scale})
        return state

    @classmethod
    def _state_to_kwargs(clazz, state):
        noise_scale = state.pop("noise_scale")
        kwargs = super(GaussianSmoother, clazz)._state_to_kwargs(state)
        kwargs.update({"noise_scale": noise_scale})
        return kwargs


###############################################################################
###############################################################################
###############################################################################


class PathIntegrator(AugmentReduceBase):

    def __init__(self, subanalyzer, *args, **kwargs):
        steps = kwargs.pop("steps", 16)
        self._reference_inputs = kwargs.pop("reference_inputs", 0)
        self._keras_constant_inputs = None
        super(PathIntegrator, self).__init__(subanalyzer,
                                             *args,
                                             augment_by_n=steps,
                                             **kwargs)

    def _python_based_compute_difference(self, X):
        if getattr(self, "_difference", None) is None:
            reference_inputs = iutils.to_list(self._reference_inputs)
            difference = [ri-x for ri, x in zip(reference_inputs, X)]
            self._difference = difference
        return self._difference

    def _python_based_augment(self, X):
        difference = self._python_based_compute_difference(X)

        tmp = super(PathIntegrator, self)._python_based_augment(X)
        tmp = [x.reshape((-1, self._augment_by_n)+x.shape[1:]) for x in tmp]

        # Make broadcastable.
        difference = [x.reshape((-1, 1)+x.shape[1:]) for x in difference]

        alpha = (K.cast_to_floatx(np.arange(self._augment_by_n)) /
                 self._augment_by_n)
        # Make broadcastable.
        alpha = [alpha.reshape((1, self._augment_by_n) +
                               tuple(np.ones_like(x.shape[2:])))
                 for x in difference]
        # Compute path steps.
        path_steps = [a * d for a, d in zip(alpha, difference)]

        ret = [x+p for x, p in zip(tmp, path_steps)]
        ret = [x.reshape((-1,)+x.shape[2:]) for x in ret]
        return ret

    def _python_based_reduce(self, X):
        tmp = super(PathIntegrator, self)._python_based_reduce(X)
        # todo: make this part nicer!
        difference = self._python_based_compute_difference(X)
        del self._difference

        return [x*d for x, d in zip(tmp, difference)]

    def _keras_set_constant_inputs(self, inputs):
        tmp = [K.variable(x) for x in inputs]
        self._keras_constant_inputs = [
            keras.layers.Input(tensor=x, shape=x.shape[1:])
            for x in tmp]

    def _keras_get_constant_inputs(self):
        return self._keras_constant_inputs

    def _keras_based_compute_difference(self, X):
        if self._keras_constant_inputs is None:
            def none_to_one(tmp):
                return [1 if x is None else x for x in tmp]

            if isinstance(self._reference_inputs, list):
                tmp = [np.broadcast_to(ri, none_to_one(K.int_shape(x)))
                       for x, ri in zip(X, self._reference_inputs)]
            else:
                tmp = [np.broadcast_to(self._reference_inputs,
                                       none_to_one(K.int_shape(x)))
                       for x in X]
            self._keras_set_constant_inputs(tmp)

        reference_inputs = self._keras_get_constant_inputs()
        return [keras.layers.Subtract()([ri, x])
                for ri, x in zip(reference_inputs, X)]

    def _keras_based_augment(self, X):
        tmp = super(PathIntegrator, self)._keras_based_augment(X)
        tmp = [ilayers.Reshape((-1, self._augment_by_n)+K.int_shape(x)[1:])(x)
               for x in tmp]

        difference = self._keras_based_compute_difference(X)
        self._keras_difference = difference
        # Make broadcastable.
        difference = [ilayers.Reshape((-1, 1)+K.int_shape(x)[1:])(x)
                      for x in difference]

        # Compute path steps.
        multiply_with_linspace = ilayers.MultiplyWithLinspace(
            0, 1,
            n=self._augment_by_n,
            axis=1)
        path_steps = [multiply_with_linspace(d) for d in difference]

        ret = [keras.layers.Add()([x, p]) for x, p in zip(tmp, path_steps)]
        ret = [ilayers.Reshape((-1,)+K.int_shape(x)[2:])(x) for x in ret]
        return ret

    def _keras_based_reduce(self, X):
        tmp = super(PathIntegrator, self)._keras_based_reduce(X)
        difference = self._keras_difference
        del self._keras_difference

        return [keras.layers.Multiply()([x, d])
                for x, d in zip(tmp, difference)]

    def _get_state(self):
        state = super(PathIntegrator, self)._get_state()
        state.update({"reference_inputs": self._reference_inputs})
        return state

    @classmethod
    def _state_to_kwargs(clazz, state):
        reference_inputs = state.pop("reference_inputs")
        kwargs = super(PathIntegrator, clazz)._state_to_kwargs(state)
        kwargs.update({"reference_inputs": reference_inputs})
        # We use steps instead.
        kwargs.update({"steps": kwargs["augment_by_n"]})
        del kwargs["augment_by_n"]
        return kwargs
