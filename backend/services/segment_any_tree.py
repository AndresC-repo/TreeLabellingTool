"""
SegmentAnyTree Model Architecture

Matches the official pretrained weights from:
https://github.com/SmartForest-no/SegmentAnyTree

Architecture: 7-layer sparse 3D UNet (MinkowskiEngine) with 3 heads
Channels: 16→32→48→64→80→96→112 (linear +16 per stage)
~30M parameters
"""

import torch
import torch.nn as nn
import MinkowskiEngine as ME


class ResBlock(nn.Module):
    def __init__(self, in_ch, out_ch, D=3):
        super().__init__()
        self.block = nn.Sequential(
            ME.MinkowskiConvolution(in_ch, out_ch, kernel_size=3, stride=1, dimension=D),
            ME.MinkowskiBatchNorm(out_ch),
            ME.MinkowskiReLU(),
            ME.MinkowskiConvolution(out_ch, out_ch, kernel_size=3, stride=1, dimension=D),
            ME.MinkowskiBatchNorm(out_ch),
        )
        if in_ch != out_ch:
            self.downsample = nn.Sequential(
                ME.MinkowskiConvolution(in_ch, out_ch, kernel_size=1, stride=1, dimension=D),
                ME.MinkowskiBatchNorm(out_ch),
            )
        self.relu = ME.MinkowskiReLU()

    def forward(self, x):
        residual = x
        out = self.block(x)
        if hasattr(self, 'downsample'):
            residual = self.downsample(x)
        return self.relu(out + residual)


class DownModule(nn.Module):
    def __init__(self, in_ch, out_ch, stride=1, D=3):
        super().__init__()
        conv_out = in_ch if stride > 1 else out_ch
        self.conv_in = nn.Sequential(
            ME.MinkowskiConvolution(in_ch, conv_out, kernel_size=3, stride=stride, dimension=D),
            ME.MinkowskiBatchNorm(conv_out),
            ME.MinkowskiReLU(),
        )
        self.blocks = nn.ModuleList([
            ResBlock(conv_out, out_ch, D),
            ResBlock(out_ch, out_ch, D),
        ])

    def forward(self, x):
        x = self.conv_in(x)
        for block in self.blocks:
            x = block(x)
        return x


class UpModule(nn.Module):
    def __init__(self, in_ch, out_ch, stride=1, D=3):
        super().__init__()
        self.stride = stride
        if stride > 1:
            self.conv_in = nn.Sequential(
                ME.MinkowskiConvolutionTranspose(
                    in_ch, in_ch, kernel_size=3, stride=stride, dimension=D
                ),
                ME.MinkowskiBatchNorm(in_ch),
                ME.MinkowskiReLU(),
            )
            block_in = in_ch
        else:
            self.conv_in = nn.Sequential(
                ME.MinkowskiConvolution(
                    in_ch, out_ch, kernel_size=3, stride=1, dimension=D
                ),
                ME.MinkowskiBatchNorm(out_ch),
                ME.MinkowskiReLU(),
            )
            block_in = out_ch

        self.blocks = nn.ModuleList([
            ResBlock(block_in, out_ch, D),
            ResBlock(out_ch, out_ch, D),
        ])

    def forward(self, x):
        x = self.conv_in(x)
        for block in self.blocks:
            x = block(x)
        return x


class BackboneUNet(nn.Module):
    DOWN_CHANNELS = [
        (4, 16), (16, 32), (32, 48), (48, 64), (64, 80), (80, 96), (96, 112)
    ]
    DOWN_STRIDES = [1, 2, 2, 2, 2, 2, 2]

    UP_CHANNELS = [
        (112, 96), (192, 80), (160, 64), (128, 48), (96, 32), (64, 16), (32, 16)
    ]
    UP_STRIDES = [2, 2, 2, 2, 2, 2, 1]

    def __init__(self, in_channels=3):
        super().__init__()
        down_channels = list(self.DOWN_CHANNELS)
        down_channels[0] = (in_channels, 16)

        self.down_modules = nn.ModuleList([
            DownModule(in_ch, out_ch, stride)
            for (in_ch, out_ch), stride in zip(down_channels, self.DOWN_STRIDES)
        ])
        self.up_modules = nn.ModuleList([
            UpModule(in_ch, out_ch, stride)
            for (in_ch, out_ch), stride in zip(self.UP_CHANNELS, self.UP_STRIDES)
        ])

    def forward(self, x):
        encoder_features = []
        for down in self.down_modules:
            x = down(x)
            encoder_features.append(x)

        for i, up in enumerate(self.up_modules):
            if i > 0:
                skip = encoder_features[-(i + 1)]
                x = ME.cat(x, skip)
            x = up(x)

        return x


class FastBatchNorm1d(nn.Module):
    def __init__(self, num_features):
        super().__init__()
        self.batch_norm = nn.BatchNorm1d(num_features)

    def forward(self, x):
        return self.batch_norm(x)


class SegmentAnyTree(nn.Module):
    def __init__(self, in_channels=3, num_classes=2, embedding_dim=5):
        super().__init__()
        out_ch = 16

        self.Backbone = BackboneUNet(in_channels)

        self.Semantic = nn.Sequential(
            nn.Sequential(nn.Sequential(
                nn.Linear(out_ch, out_ch),
                FastBatchNorm1d(out_ch),
                nn.ReLU(),
            )),
            nn.Linear(out_ch, num_classes),
        )

        self.Offset = nn.Sequential(
            nn.Sequential(nn.Sequential(
                nn.Linear(out_ch, out_ch),
                FastBatchNorm1d(out_ch),
                nn.ReLU(),
            )),
            nn.Linear(out_ch, 3),
        )

        self.Embed = nn.Sequential(
            nn.Sequential(nn.Sequential(
                nn.Linear(out_ch, out_ch),
                FastBatchNorm1d(out_ch),
                nn.ReLU(),
            )),
            nn.Linear(out_ch, embedding_dim),
        )

    def forward(self, sparse_tensor):
        features = self.Backbone(sparse_tensor)
        feat = features.F
        return {
            'semantic_logits': self.Semantic(feat),
            'offsets':         self.Offset(feat),
            'embeddings':      self.Embed(feat),
        }
