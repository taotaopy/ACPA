###########################################################################
# Created by: CASIA IVA
# Email: jliu@nlpr.ia.ac.cn
# Copyright (c) 2018
###########################################################################

import numpy as np
import torch
import torch.nn as nn
import math
from torch.nn import Module, Sequential, Conv2d, ReLU,AdaptiveMaxPool2d, AdaptiveAvgPool2d, \
    NLLLoss, BCELoss, CrossEntropyLoss, AvgPool2d, MaxPool2d, Parameter, Linear, Sigmoid, Softmax, Dropout, Embedding
from torch.nn import functional as F
from torch.autograd import Variable
torch_ver = torch.__version__[:3]

__all__ = ['PAM_Module', 'CAM_Module']  #This is from DANet


class PAM_Module(Module):
    """ Position attention module"""
    #Ref from SAGAN
    def __init__(self, in_dim):
        super(PAM_Module, self).__init__()
        self.chanel_in = in_dim

        self.query_conv = Conv2d(in_channels=in_dim, out_channels=in_dim//8, kernel_size=1)  #通道被压缩1/8
        self.key_conv = Conv2d(in_channels=in_dim, out_channels=in_dim//8, kernel_size=1)
        self.value_conv = Conv2d(in_channels=in_dim, out_channels=in_dim, kernel_size=1)
        self.gamma = Parameter(torch.zeros(1))  #gamma是一个可训练的值，让其初始值为0

        self.softmax = Softmax(dim=-1)
    def forward(self, x):
        """
            inputs :
                x : input feature maps( B X C X H X W)
            returns :
                out : attention value + input feature
                attention: B X (HxW) X (HxW)
        """
        m_batchsize, C, height, width = x.size()
        proj_query = self.query_conv(x).view(m_batchsize, -1, width*height).permute(0, 2, 1)
        proj_key = self.key_conv(x).view(m_batchsize, -1, width*height)
        energy = torch.bmm(proj_query, proj_key)
        attention = self.softmax(energy)
        proj_value = self.value_conv(x).view(m_batchsize, -1, width*height)

        out = torch.bmm(proj_value, attention.permute(0, 2, 1))   #每个位置乘上权重图
        out = out.view(m_batchsize, C, height, width)

        out = self.gamma*out + x  #这个gamma初始值为0，就是让这个训练结果慢慢融入网络中（特别是在与寻来你模型中）
        return out


class CAM_Module(Module):   #通道注意力中间没压缩通道
    """ Channel attention module"""
    def __init__(self, in_dim):
        super(CAM_Module, self).__init__()
        self.chanel_in = in_dim


        self.gamma = Parameter(torch.zeros(1))
        self.softmax  = Softmax(dim=-1)
    def forward(self,x):
        """
            inputs :
                x : input feature maps( B X C X H X W)
            returns :
                out : attention value + input feature
                attention: B X C X C
        """
        m_batchsize, C, height, width = x.size()
        proj_query = x.view(m_batchsize, C, -1)
        proj_key = x.view(m_batchsize, C, -1).permute(0, 2, 1)
        energy = torch.bmm(proj_query, proj_key)
        energy_new = torch.max(energy, -1, keepdim=True)[0].expand_as(energy)-energy    #论文里也没有，不知道这里为什么加上了这操作，搞不懂
        attention = self.softmax(energy_new)
        proj_value = x.view(m_batchsize, C, -1)

        out = torch.bmm(attention, proj_value)
        out = out.view(m_batchsize, C, height, width)

        out = self.gamma*out + x
        return out


# class DANetHead(nn.Module):  # 在这个head里面是先把要进入注意力模块的特征图缩小通道，
#     def __init__(self, in_channels, out_channels,norm_layer,Attention):
#         super(DANetHead, self).__init__()
#         self.attention=Attention
#         inter_channels = in_channels // 4
#         self.conv5a = nn.Sequential(nn.Conv2d(in_channels, inter_channels, 3, padding=1, bias=False),
#                                     norm_layer(inter_channels),
#                                     nn.ReLU())
#
#         self.conv5c = nn.Sequential(nn.Conv2d(in_channels, inter_channels, 3, padding=1, bias=False),
#                                     norm_layer(inter_channels),
#                                     nn.ReLU())
#
#         self.sa = PAM_Module(inter_channels)
#         self.sc = CAM_Module(inter_channels)
#         self.conv51 = nn.Sequential(nn.Conv2d(inter_channels, inter_channels, 3, padding=1, bias=False),
#                                     norm_layer(inter_channels),
#                                     nn.ReLU())
#         self.conv52 = nn.Sequential(nn.Conv2d(inter_channels, inter_channels, 3, padding=1, bias=False),
#                                     norm_layer(inter_channels),
#                                     nn.ReLU())
#
#         self.conv6 = nn.Sequential(nn.Dropout2d(0.1, False), nn.Conv2d(inter_channels, out_channels, 1))
#         self.conv7 = nn.Sequential(nn.Dropout2d(0.1, False), nn.Conv2d(inter_channels, out_channels, 1))
#
#         self.conv8 = nn.Sequential(nn.Dropout2d(0.1, False), nn.Conv2d(inter_channels, out_channels, 1))
#
#     def forward(self, x):
#         feat1 = self.conv5a(x)
#         sa_feat = self.sa(feat1)
#         sa_conv = self.conv51(sa_feat)
#         sa_output = self.conv6(sa_conv)
#
#         feat2 = self.conv5c(x)
#         sc_feat = self.sc(feat2)
#         sc_conv = self.conv52(sc_feat)
#         sc_output = self.conv7(sc_conv)
#
#         feat_sum = sa_conv + sc_conv
#
#         sasc_output = self.conv8(feat_sum)
#
#         # if self.attention=='sasc':
#         #     return sasc_output
#         # elif self.attention=='sa':
#         #     return sa_output
#         # elif self.attention=='sc':
#         #     return sc_output
#         # elif self.attention=='all':
#         return [sasc_output,sa_output,sc_output]

class DANetHead(nn.Module):  # 在这个head里面是先把要进入注意力模块的特征图缩小通道，
    def __init__(self, in_channels, out_channels,norm_layer,Attention):
        super(DANetHead, self).__init__()
        self.attention=Attention
        inter_channels = in_channels // 4
        self.conv5a = nn.Sequential(nn.Conv2d(in_channels, inter_channels, 3, padding=1, bias=False),
                                    norm_layer(inter_channels),
                                    nn.ReLU())

        self.conv5c = nn.Sequential(nn.Conv2d(in_channels, inter_channels, 3, padding=1, bias=False),
                                    norm_layer(inter_channels),
                                    nn.ReLU())

        self.sa = PAM_Module(inter_channels)
        self.sc = CAM_Module(inter_channels)
        self.conv51 = nn.Sequential(nn.Conv2d(inter_channels, out_channels, 3, padding=1, bias=False),
                                    norm_layer(out_channels),
                                    nn.ReLU())
        self.conv52 = nn.Sequential(nn.Conv2d(inter_channels, out_channels, 3, padding=1, bias=False),
                                    norm_layer(out_channels),
                                    nn.ReLU())

        self.conv6 = nn.Sequential(nn.Dropout2d(0.1, False), nn.Conv2d( out_channels, 1, 1))
        self.conv7 = nn.Sequential(nn.Dropout2d(0.1, False), nn.Conv2d( out_channels, 1, 1))

        self.conv8 = nn.Sequential(nn.Dropout2d(0.1, False), nn.Conv2d( out_channels,1, 1))

    def forward(self, x):
        feat1 = self.conv5a(x)
        sa_feat = self.sa(feat1)
        sa_conv = self.conv51(sa_feat)
        sa_output = self.conv6(sa_conv)

        feat2 = self.conv5c(x)
        sc_feat = self.sc(feat2)
        sc_conv = self.conv52(sc_feat)
        sc_output = self.conv7(sc_conv)

        feat_sum = sa_conv + sc_conv

        sasc_output = self.conv8(feat_sum)

        # if self.attention=='sasc':
        #     return sasc_output
        # elif self.attention=='sa':
        #     return sa_output
        # elif self.attention=='sc':
        #     return sc_output
        # elif self.attention=='all':
        return [feat_sum ,sa_conv,sc_conv],[sasc_output,sa_output,sc_output]