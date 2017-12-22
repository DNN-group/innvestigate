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


from . import base
from .. import layers as ilayers
from .. import utils

import keras.backend as K
import keras.models
import keras
import keras.activations


__all__ = [
    "BaselineGradient",
    "Gradient",
    "Deconvnet",
]


###############################################################################
###############################################################################
###############################################################################


class BaselineGradient(base.BaseNetwork):

    properties = {
        "name": "BaselineGradient",
        "show_as": "rgb",
    }


    def _create_analysis(self, model):
        return ilayers.Gradient()(model.inputs+[model.outputs[0],])


class Gradient(base.BaseReverseNetwork):

    properties = {
        "name": "Gradient",
        "show_as": "rgb",
    }

    def __init__(self, *args, **kwargs):
        # we assume there is only one head!
        gradient_head_processed = [False]
        def gradient_reverse(Xs, Ys, reversed_Ys, reverse_state):
            if gradient_head_processed[0] is not True:
                # replace function value with ones as the last element
                # chain rule is a one.
                gradient_head_processed[0] = True
                reversed_Ys = utils.listify(ilayers.OnesLike()(reversed_Ys))
            return ilayers.GradientWRT(len(Xs))(Xs+Ys+reversed_Ys)

        self.default_reverse = gradient_reverse
        return super(Gradient, self).__init__(*args, **kwargs)


class Deconvnet(base.BaseReverseNetwork):

    properties = {
        "name": "Deconvnet",
        # todo: set right value
        "show_as": "rgb",
    }

    def __init__(self, *args, **kwargs):
        # we assume there is only one head!
        gradient_head_processed = [False]
        def gradient_reverse(Xs, Ys, reversed_Ys, reverse_state):
            if gradient_head_processed[0] is not True:
                # replace function value with ones as the last element
                # chain rule is a one.
                gradient_head_processed[0] = True
                reversed_Ys = utils.listify(ilayers.OnesLike()(reversed_Ys))
            layer = reverse_state["layer"]
            # todo: make failsafer
            # todo: modularize
            if(hasattr(layer, "activation") and
               layer.activation == keras.activations.relu):
                activation = keras.layers.Activation("relu")
                reversed_Ys = ilayers.easy_apply(activation, reversed_Ys)

                # todo: cache and do this only once per layer
                config = layer.get_config()
                config["name"] = "reversed_%s" % config["name"]
                config["activation"] = None
                layer_wo_relu = layer.__class__.from_config(config)
                Ys_wo_relu = ilayers.easy_apply(layer_wo_relu, Xs)
                layer_wo_relu.set_weights(layer.get_weights())

                return ilayers.GradientWRT(len(Xs))(Xs+Ys_wo_relu+reversed_Ys)
            else:
                return ilayers.GradientWRT(len(Xs))(Xs+Ys+reversed_Ys)   

        self.default_reverse = gradient_reverse
        return super(Deconvnet, self).__init__(*args, **kwargs)