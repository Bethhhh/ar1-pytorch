#!/usr/bin/env python
# -*- coding: utf-8 -*-

################################################################################
# Copyright (c) 2019. Vincenzo Lomonaco. All rights reserved.                  #
# See the accompanying LICENSE file for terms.                                 #
#                                                                              #
# Date: 23-07-2019                                                             #
# Author: Vincenzo Lomonaco                                                    #
# E-mail: vincenzo.lomonaco@unibo.it                                           #
# Website: vincenzolomonaco.com                                                #
################################################################################

""" This file contains the model Class used for the exps"""

__all__ = ['MobileNet', 'mobilenet_w1', 'mobilenet_w3d4', 'mobilenet_wd2', 'mobilenet_wd4', 'fdmobilenet_w1',
           'fdmobilenet_w3d4', 'fdmobilenet_wd2', 'fdmobilenet_wd4']

import os
import torch
import torch.nn as nn
import torch.nn.init as init
from common import conv1x1_block, conv3x3_block, dwconv3x3_block
from utils import replace_bn_with_brn


class DwsConvBlock(nn.Module):
    """
    Depthwise separable convolution block with BatchNorms and activations at each convolution layers. It is used as
    a MobileNet unit.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    stride : int or tuple/list of 2 int
        Strides of the convolution.
    """
    def __init__(self,
                 in_channels,
                 out_channels,
                 stride):
        super(DwsConvBlock, self).__init__()
        self.dw_conv = dwconv3x3_block(
            in_channels=in_channels,
            out_channels=in_channels,
            stride=stride)
        self.pw_conv = conv1x1_block(
            in_channels=in_channels,
            out_channels=out_channels)

    def forward(self, x):
        x = self.dw_conv(x)
        x = self.pw_conv(x)
        return x


class MobileNet(nn.Module):
    """
    MobileNet model from 'MobileNets: Efficient Convolutional Neural Networks for Mobile Vision Applications,'
    https://arxiv.org/abs/1704.04861. Also this class implements FD-MobileNet from 'FD-MobileNet: Improved MobileNet
    with A Fast Downsampling Strategy,' https://arxiv.org/abs/1802.03750.

    Parameters:
    ----------
    channels : list of list of int
        Number of output channels for each unit.
    first_stage_stride : bool
        Whether stride is used at the first stage.
    in_channels : int, default 3
        Number of input channels.
    in_size : tuple of two ints, default (224, 224)
        Spatial size of the expected input image.
    num_classes : int, default 1000
        Number of classification classes.
    """
    def __init__(self,
                 channels,
                 first_stage_stride,
                 in_channels=3,
                 in_size=(224, 224),
                 num_classes=1000):
        super(MobileNet, self).__init__()
        self.in_size = in_size
        self.num_classes = num_classes

        self.features = nn.Sequential()
        init_block_channels = channels[0][0]
        self.features.add_module("init_block", conv3x3_block(
            in_channels=in_channels,
            out_channels=init_block_channels,
            stride=2))
        in_channels = init_block_channels
        for i, channels_per_stage in enumerate(channels[1:]):
            stage = nn.Sequential()
            for j, out_channels in enumerate(channels_per_stage):
                stride = 2 if (j == 0) and ((i != 0) or first_stage_stride) else 1
                stage.add_module("unit{}".format(j + 1), DwsConvBlock(
                    in_channels=in_channels,
                    out_channels=out_channels,
                    stride=stride))
                in_channels = out_channels
            self.features.add_module("stage{}".format(i + 1), stage)
        self.features.add_module("final_pool", nn.AvgPool2d(
            kernel_size=7,
            stride=1))

        self.output = nn.Linear(
            in_features=in_channels,
            out_features=num_classes)

        self._init_params()

    def _init_params(self):
        for name, module in self.named_modules():
            if 'dw_conv.conv' in name:
                init.kaiming_normal_(module.weight, mode='fan_in')
            elif name == 'init_block.conv' or 'pw_conv.conv' in name:
                init.kaiming_normal_(module.weight, mode='fan_out')
            elif 'bn' in name:
                init.constant_(module.weight, 1)
                init.constant_(module.bias, 0)
            elif 'output' in name:
                init.kaiming_normal_(module.weight, mode='fan_out')
                init.constant_(module.bias, 0)

    def forward(self, x):
        x = self.features(x)
        x = x.view(x.size(0), -1)
        x = self.output(x)
        return x

def remove_sequential(network, all_layers):

    for layer in network.children():
        if isinstance(layer, nn.Sequential): # if sequential layer, apply recursively to layers in sequential layer
            #print(layer)
            remove_sequential(layer, all_layers)
        else: # if leaf node, add it to list
            # print(layer)
            all_layers.append(layer)

def remove_DwsConvBlock(cur_layers):

    all_layers = []
    for layer in cur_layers:
        if isinstance(layer, DwsConvBlock):
           #  print("helloooo: ", layer)
            for ch in layer.children():
                all_layers.append(ch)
        else:
            all_layers.append(layer)
    return all_layers


class MyMobilenetV1(nn.Module):
    def __init__(self, pretrained=True, latent_layer_num=20):
        super().__init__()

        model = mobilenet_w1(pretrained=pretrained)
        model.features.final_pool = nn.AvgPool2d(4)
        # replace_bn_with_brn(model, None)

        # print(list(model.modules()))
        # print(list(model.features))
        # print(list(model.children()))
        all_layers = []
        remove_sequential(model, all_layers)
        all_layers = remove_DwsConvBlock(all_layers)
        # print(all_layers)
        # print(list(model.features))

        lat_list = []
        end_list = []

        for i, layer in enumerate(all_layers[:-1]):
            if i <= latent_layer_num:
                lat_list.append(layer)
            else:
                end_list.append(layer)
        # lat_list_names= []
        # end_list_names = []
        # lat = True
        # for name, module in model.features.named_children():
        #     # print(name)
        #
        #     if lat:
        #         lat_list.append(module)
        #     else:
        #         end_list.append(module)
        #
        #     if name == "stage4":
        #         lat = False

        self.lat_features = nn.Sequential(*lat_list)
        self.end_features = nn.Sequential(*end_list)

        self.output = nn.Linear(1024, 50, bias=False)


    def forward(self, x, latent_input=None, return_lat_acts=False):

        if latent_input is not None:
            with torch.no_grad():
                orig_acts = self.lat_features(x)
            lat_acts = torch.cat((orig_acts, latent_input), 0)
        else:
            orig_acts = self.lat_features(x)
            lat_acts = orig_acts

        x = self.end_features(lat_acts)
        x = x.view(x.size(0), -1)
        logits = self.output(x)

        if return_lat_acts:
            return logits, orig_acts
        else:
            return logits

def get_mobilenet(version,
                  width_scale,
                  model_name=None,
                  pretrained=False,
                  root=os.path.join("~", ".torch", "models"),
                  **kwargs):
    """
    Create MobileNet or FD-MobileNet model with specific parameters.

    Parameters:
    ----------
    version : str
        Version of SqueezeNet ('orig' or 'fd').
    width_scale : float
        Scale factor for width of layers.
    model_name : str or None, default None
        Model name for loading pretrained model.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.torch/models'
        Location for keeping the model parameters.
    """

    if version == 'orig':
        channels = [[32], [64], [128, 128], [256, 256], [512, 512, 512, 512, 512, 512], [1024, 1024]]
        first_stage_stride = False
    elif version == 'fd':
        channels = [[32], [64], [128, 128], [256, 256], [512, 512, 512, 512, 512, 1024]]
        first_stage_stride = True
    else:
        raise ValueError("Unsupported MobileNet version {}".format(version))

    if width_scale != 1.0:
        channels = [[int(cij * width_scale) for cij in ci] for ci in channels]

    net = MobileNet(
        channels=channels,
        first_stage_stride=first_stage_stride,
        **kwargs)

    if pretrained:
        if (model_name is None) or (not model_name):
            raise ValueError("Parameter `model_name` should be properly initialized for loading pretrained model.")
        from model_store import download_model
        download_model(
            net=net,
            model_name=model_name,
            local_model_store_dir_path=root)

    return net


def mobilenet_w1(**kwargs):
    """
    1.0 MobileNet-224 model from 'MobileNets: Efficient Convolutional Neural Networks for Mobile Vision Applications,'
    https://arxiv.org/abs/1704.04861.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.torch/models'
        Location for keeping the model parameters.
    """
    return get_mobilenet(version="orig", width_scale=1.0, model_name="mobilenet_w1", **kwargs)


def mobilenet_w3d4(**kwargs):
    """
    0.75 MobileNet-224 model from 'MobileNets: Efficient Convolutional Neural Networks for Mobile Vision Applications,'
    https://arxiv.org/abs/1704.04861.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.torch/models'
        Location for keeping the model parameters.
    """
    return get_mobilenet(version="orig", width_scale=0.75, model_name="mobilenet_w3d4", **kwargs)


def mobilenet_wd2(**kwargs):
    """
    0.5 MobileNet-224 model from 'MobileNets: Efficient Convolutional Neural Networks for Mobile Vision Applications,'
    https://arxiv.org/abs/1704.04861.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.torch/models'
        Location for keeping the model parameters.
    """
    return get_mobilenet(version="orig", width_scale=0.5, model_name="mobilenet_wd2", **kwargs)


def mobilenet_wd4(**kwargs):
    """
    0.25 MobileNet-224 model from 'MobileNets: Efficient Convolutional Neural Networks for Mobile Vision Applications,'
    https://arxiv.org/abs/1704.04861.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.torch/models'
        Location for keeping the model parameters.
    """
    return get_mobilenet(version="orig", width_scale=0.25, model_name="mobilenet_wd4", **kwargs)


def fdmobilenet_w1(**kwargs):
    """
    FD-MobileNet 1.0x model from 'FD-MobileNet: Improved MobileNet with A Fast Downsampling Strategy,'
    https://arxiv.org/abs/1802.03750.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.torch/models'
        Location for keeping the model parameters.
    """
    return get_mobilenet(version="fd", width_scale=1.0, model_name="fdmobilenet_w1", **kwargs)


def fdmobilenet_w3d4(**kwargs):
    """
    FD-MobileNet 0.75x model from 'FD-MobileNet: Improved MobileNet with A Fast Downsampling Strategy,'
    https://arxiv.org/abs/1802.03750.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.torch/models'
        Location for keeping the model parameters.
    """
    return get_mobilenet(version="fd", width_scale=0.75, model_name="fdmobilenet_w3d4", **kwargs)


def fdmobilenet_wd2(**kwargs):
    """
    FD-MobileNet 0.5x model from 'FD-MobileNet: Improved MobileNet with A Fast Downsampling Strategy,'
    https://arxiv.org/abs/1802.03750.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.torch/models'
        Location for keeping the model parameters.
    """
    return get_mobilenet(version="fd", width_scale=0.5, model_name="fdmobilenet_wd2", **kwargs)


def fdmobilenet_wd4(**kwargs):
    """
    FD-MobileNet 0.25x model from 'FD-MobileNet: Improved MobileNet with A Fast Downsampling Strategy,'
    https://arxiv.org/abs/1802.03750.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    root : str, default '~/.torch/models'
        Location for keeping the model parameters.
    """
    return get_mobilenet(version="fd", width_scale=0.25, model_name="fdmobilenet_wd4", **kwargs)

def mobilenet_v1_core50():

    model = mobilenet_w1(pretrained=True)
    model.features.final_pool = nn.AvgPool2d(4)
    model.output = nn.Linear(1024, 50, bias=False)

    return model

def _calc_width(net):
    import numpy as np
    net_params = filter(lambda p: p.requires_grad, net.parameters())
    weight_count = 0
    for param in net_params:
        weight_count += np.prod(param.size())
    return weight_count


def _test():
    import torch

    pretrained = False

    models = [
        mobilenet_w1,
        mobilenet_w3d4,
        mobilenet_wd2,
        mobilenet_wd4,
        fdmobilenet_w1,
        fdmobilenet_w3d4,
        fdmobilenet_wd2,
        fdmobilenet_wd4,
    ]

    for model in models:

        net = model(pretrained=pretrained)

        # net.train()
        net.eval()
        weight_count = _calc_width(net)
        print("m={}, {}".format(model.__name__, weight_count))
        assert (model != mobilenet_w1 or weight_count == 4231976)
        assert (model != mobilenet_w3d4 or weight_count == 2585560)
        assert (model != mobilenet_wd2 or weight_count == 1331592)
        assert (model != mobilenet_wd4 or weight_count == 470072)
        assert (model != fdmobilenet_w1 or weight_count == 2901288)
        assert (model != fdmobilenet_w3d4 or weight_count == 1833304)
        assert (model != fdmobilenet_wd2 or weight_count == 993928)
        assert (model != fdmobilenet_wd4 or weight_count == 383160)

        x = torch.randn(1, 3, 224, 224)
        y = net(x)
        y.sum().backward()
        assert (tuple(y.size()) == (1, 1000))


if __name__ == "__main__":

    model = MyMobilenetV1(pretrained=True)
    for name, param in model.named_parameters():
        # if "dw_conv.conv" in name:
        #     print(name)
        print(name)
        pass
