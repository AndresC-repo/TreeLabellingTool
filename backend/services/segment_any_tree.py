"""
SegmentAnyTree Model Architecture

Architecture: 7-layer sparse 3D UNet (spconv 2.x) with 3 heads
Channels: 16→32→48→64→80→96→112 (linear +16 per stage)
~30M parameters

spconv 2.x replaces MinkowskiEngine as the sparse convolution backend.

spconv layer types used here:
  SubMConv3d          – submanifold conv: output coords == input coords.
                        Used in residual blocks (never changes the active set).
  SparseConv3d        – strided conv for downsampling (stride=2 halves spatial dims).
                        Stores its coordinate map under indice_key for the decoder.
  SparseInverseConv3d – inverse (transposed) conv for upsampling.
                        Looks up indice_key from the matching SparseConv3d
                        to restore exact encoder coordinates — no manual tracking.
  SparseSequential    – sequential container that handles mixed sparse/dense layers.

Replace-feature pattern:
  spconv tensors are (logically) immutable in their coordinate structure.
  To change only the features (e.g. residual add, skip-concat), use:
    new_tensor = old_tensor.replace_feature(new_feature_matrix)
  This returns a new SparseConvTensor sharing the same indice_dict
  (all stored coordinate maps), so subsequent SparseInverseConv3d layers
  can still find their encoder kernel maps.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import spconv.pytorch as spconv
from spconv.pytorch import SparseConvTensor


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

class ResBlock(nn.Module):
    """Two 3×3 submanifold convolutions with optional channel projection.

    SubMConv3d keeps the set of active voxels unchanged, which is exactly what
    we need for residual blocks: input and output share the same coordinates.
    """

    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.block = spconv.SparseSequential(
            spconv.SubMConv3d(in_ch,  out_ch, kernel_size=3, bias=False),
            nn.BatchNorm1d(out_ch, eps=1e-3, momentum=0.01),
            nn.ReLU(inplace=True),
            spconv.SubMConv3d(out_ch, out_ch, kernel_size=3, bias=False),
            nn.BatchNorm1d(out_ch, eps=1e-3, momentum=0.01),
        )
        if in_ch != out_ch:
            self.downsample = spconv.SparseSequential(
                spconv.SubMConv3d(in_ch, out_ch, kernel_size=1, bias=False),
                nn.BatchNorm1d(out_ch, eps=1e-3, momentum=0.01),
            )
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: SparseConvTensor) -> SparseConvTensor:
        residual = x
        out = self.block(x)
        if hasattr(self, 'downsample'):
            residual = self.downsample(x)
        out = out.replace_feature(out.features + residual.features)
        return out.replace_feature(self.relu(out.features))


class DownModule(nn.Module):
    """Encoder stage: one conv (strided or submanifold) + 2 ResBlocks.

    stride=1  → SubMConv3d (channel change, no spatial downsampling; for stem)
    stride=2  → SparseConv3d with indice_key (stores coords for decoder)
    """

    def __init__(self, in_ch: int, out_ch: int, stride: int = 1,
                 indice_key: str | None = None):
        super().__init__()
        conv_out = in_ch if stride > 1 else out_ch

        if stride > 1:
            self.conv_in = spconv.SparseSequential(
                spconv.SparseConv3d(
                    in_ch, conv_out, kernel_size=3, stride=stride,
                    padding=1, bias=False, indice_key=indice_key,
                ),
                nn.BatchNorm1d(conv_out, eps=1e-3, momentum=0.01),
                nn.ReLU(inplace=True),
            )
        else:
            self.conv_in = spconv.SparseSequential(
                spconv.SubMConv3d(in_ch, conv_out, kernel_size=3, bias=False),
                nn.BatchNorm1d(conv_out, eps=1e-3, momentum=0.01),
                nn.ReLU(inplace=True),
            )

        self.blocks = nn.ModuleList([
            ResBlock(conv_out, out_ch),
            ResBlock(out_ch,   out_ch),
        ])

    def forward(self, x: SparseConvTensor) -> SparseConvTensor:
        x = self.conv_in(x)
        for block in self.blocks:
            x = block(x)
        return x


class UpModule(nn.Module):
    """Decoder stage: one inverse conv (upsampling) or submanifold + 2 ResBlocks.

    stride=2  → SparseInverseConv3d with indice_key (restores encoder coords)
    stride=1  → SubMConv3d (channel projection only; for the last decoder level)
    """

    def __init__(self, in_ch: int, out_ch: int, stride: int = 1,
                 indice_key: str | None = None):
        super().__init__()
        self.stride = stride

        if stride > 1:
            self.conv_in = spconv.SparseSequential(
                spconv.SparseInverseConv3d(
                    in_ch, in_ch, kernel_size=3, bias=False,
                    indice_key=indice_key,
                ),
                nn.BatchNorm1d(in_ch, eps=1e-3, momentum=0.01),
                nn.ReLU(inplace=True),
            )
            block_in = in_ch
        else:
            self.conv_in = spconv.SparseSequential(
                spconv.SubMConv3d(in_ch, out_ch, kernel_size=3, bias=False),
                nn.BatchNorm1d(out_ch, eps=1e-3, momentum=0.01),
                nn.ReLU(inplace=True),
            )
            block_in = out_ch

        self.blocks = nn.ModuleList([
            ResBlock(block_in, out_ch),
            ResBlock(out_ch,   out_ch),
        ])

    def forward(self, x: SparseConvTensor) -> SparseConvTensor:
        x = self.conv_in(x)
        for block in self.blocks:
            x = block(x)
        return x


# ---------------------------------------------------------------------------
# UNet backbone
# ---------------------------------------------------------------------------

class BackboneUNet(nn.Module):
    """7-level sparse 3D UNet.

    Channel progression (linear +16 per stage):
      Encoder: in→16, 16→32, 32→48, 48→64, 64→80, 80→96, 96→112
      Decoder: 112→96, 192→80, 160→64, 128→48, 96→32, 64→16, 32→16

    Decoder in_ch already accounts for skip-connection concatenation:
      up[0]: bottleneck alone (112)
      up[1]: 96 (from up[0]) + 96 (enc[5] skip)  = 192
      up[2]: 80 (from up[1]) + 80 (enc[4] skip)  = 160
      up[3]: 64 (from up[2]) + 64 (enc[3] skip)  = 128
      up[4]: 48 (from up[3]) + 48 (enc[2] skip)  = 96
      up[5]: 32 (from up[4]) + 32 (enc[1] skip)  = 64
      up[6]: 16 (from up[5]) + 16 (enc[0] skip)  = 32

    indice_key pairing (forward SparseConv3d ↔ inverse SparseInverseConv3d):
      down[1]  ↔  up[5]   'spconv1'
      down[2]  ↔  up[4]   'spconv2'
      down[3]  ↔  up[3]   'spconv3'
      down[4]  ↔  up[2]   'spconv4'
      down[5]  ↔  up[1]   'spconv5'
      down[6]  ↔  up[0]   'spconv6'
    """

    # (in_ch, out_ch), stride, indice_key for each encoder stage
    DOWN_CHANNELS = [
        (4, 16), (16, 32), (32, 48), (48, 64), (64, 80), (80, 96), (96, 112)
    ]
    DOWN_STRIDES = [1,     2,          2,          2,          2,          2,          2]
    DOWN_IKEYS  = [None, 'spconv1', 'spconv2', 'spconv3', 'spconv4', 'spconv5', 'spconv6']

    # (in_ch, out_ch), stride, indice_key for each decoder stage
    UP_CHANNELS = [
        (112, 96), (192, 80), (160, 64), (128, 48), (96, 32), (64, 16), (32, 16)
    ]
    UP_STRIDES  = [2,          2,          2,          2,          2,          2,         1]
    UP_IKEYS    = ['spconv6', 'spconv5', 'spconv4', 'spconv3', 'spconv2', 'spconv1', None]

    def __init__(self, in_channels: int = 3):
        super().__init__()

        # Override in_ch for the stem to match the actual feature dimension
        down_channels = list(self.DOWN_CHANNELS)
        down_channels[0] = (in_channels, 16)

        self.down_modules = nn.ModuleList([
            DownModule(in_ch, out_ch, stride, ikey)
            for (in_ch, out_ch), stride, ikey
            in zip(down_channels, self.DOWN_STRIDES, self.DOWN_IKEYS)
        ])

        self.up_modules = nn.ModuleList([
            UpModule(in_ch, out_ch, stride, ikey)
            for (in_ch, out_ch), stride, ikey
            in zip(self.UP_CHANNELS, self.UP_STRIDES, self.UP_IKEYS)
        ])

    def forward(self, x: SparseConvTensor) -> SparseConvTensor:
        # --- Encoder ---
        encoder_features = []
        for down in self.down_modules:
            x = down(x)
            encoder_features.append(x)

        # --- Decoder ---
        for i, up in enumerate(self.up_modules):
            if i > 0:
                skip = encoder_features[-(i + 1)]
                x = x.replace_feature(
                    torch.cat([x.features, skip.features], dim=1)
                )
            x = up(x)

        return x


# ---------------------------------------------------------------------------
# Prediction heads + full model
# ---------------------------------------------------------------------------

class FastBatchNorm1d(nn.Module):
    """BatchNorm wrapper whose sub-attribute name matches torch_points3d keys.

    The pretrained SegmentAnyTree checkpoint stores BatchNorm parameters under
    the path  …Semantic.0.0.1.batch_norm.weight  (etc.).  Wrapping BatchNorm1d
    inside a module with attribute name 'batch_norm' lets us load those weights
    without any key remapping.
    """

    def __init__(self, num_features: int):
        super().__init__()
        self.batch_norm = nn.BatchNorm1d(num_features)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.batch_norm(x)


class SegmentAnyTree(nn.Module):
    """Complete SegmentAnyTree model.

    Three output heads on top of the UNet backbone:
      Semantic  – per-point binary classification (tree / non-tree)
      Offset    – 3D offset vectors toward tree instance centres
      Embed     – 5D discriminative embeddings for instance clustering

    Capital-letter attribute names (Backbone, Semantic, Offset, Embed)
    match the key prefixes used in the torch_points3d pretrained checkpoint.
    """

    def __init__(self, in_channels: int = 3, num_classes: int = 2,
                 embedding_dim: int = 5, dropout: float = 0.5):
        super().__init__()

        out_ch = 16  # backbone output channels

        self.Backbone = BackboneUNet(in_channels)

        self.Semantic = nn.Sequential(
            nn.Sequential(nn.Sequential(
                nn.Linear(out_ch, out_ch),
                FastBatchNorm1d(out_ch),
                nn.ReLU(),
                nn.Dropout(p=dropout),
            )),
            nn.Linear(out_ch, num_classes),
        )

        self.Offset = nn.Sequential(
            nn.Sequential(nn.Sequential(
                nn.Linear(out_ch, out_ch),
                FastBatchNorm1d(out_ch),
                nn.ReLU(),
                nn.Dropout(p=dropout),
            )),
            nn.Linear(out_ch, 3),
        )

        self.Embed = nn.Sequential(
            nn.Sequential(nn.Sequential(
                nn.Linear(out_ch, out_ch),
                FastBatchNorm1d(out_ch),
                nn.ReLU(),
                nn.Dropout(p=dropout),
            )),
            nn.Linear(out_ch, embedding_dim),
        )

    def forward(self, sparse_tensor: SparseConvTensor) -> dict:
        features = self.Backbone(sparse_tensor)
        feat = features.features   # (N, 16) dense feature matrix

        return {
            'semantic_logits': self.Semantic(feat),
            'offsets':         self.Offset(feat),
            'embeddings':      self.Embed(feat),
        }

    def get_num_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
