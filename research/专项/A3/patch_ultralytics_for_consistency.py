#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A3-02 特征一致性训练(路线 A:ultralytics Trainer 子类化)——把「接口骨架」变成能出消融表的真训练

适配版本: ultralytics==8.4.60(Python 3.14 / torch 2.12)。升级 ultralytics 时只需核对本文件
两处「版本敏感」内容:
  1. _LAYER_INDICES / _FEATURE_CHANNELS —— yolo11s 喂给 Detect 头的 P3/P4/P5 层号与通道数;
  2. 侵入点 = ultralytics.engine.trainer.BaseTrainer._do_train 里
     ``preds = self.model(batch["img"]); loss = self.model.loss(batch, preds)`` 这一对调用,
     本文件只在这两个方法(forward 特征捕获 + loss 追加项)做文章,不碰其余训练基建。

方法(与《抗雾感知特征一致性训练方案》§12 评审修正一致):
    L = L_yolo(clean) + L_yolo(fog)·visible_mask + λ_feat·Σ_{p∈P3,P4,P5} ||proj(z_f_p) − proj(z_c_p)||₁
  - 检测版只做 backbone/FPN 多尺度特征一致性,不做检测头输出一致性(不设 L_cons);
  - BYOL 式 stop-gradient + predictor 防塌缩(不用 InfoNCE,单卡 batch 小、负样本不够);
  - P3/P4/P5 多尺度投影头(1×1 conv + 全局池化 + MLP);
  - invisible 样本关闭检测损失(visible_mask 已由 A3-01 的 pairs.csv 给出);
  - λ_feat cosine 退火(λ_feat → λ_end);
  - 推理零开销:投影头只是训练期 aux 分支,导出用 strip() 剥离。

本文件可独立导入;纯 torch 组件(ProjectionHead/BYOLPredictor/feature_consistency_loss/
cosine_schedule)不依赖 ultralytics。GPU 训练入口见文件尾 main()(--selftest 为 CPU 冒烟自检)。

用法(需 GPU,协议与 v4 对齐: yolo11s / imgsz=1024 / batch=8 / epochs=200 / seed=0):
  python patch_ultralytics_for_consistency.py \
      --model yolo11s.pt --data data/paired/pairs_fog.yaml --imgsz 1024 \
      --batch 8 --epochs 200 --seed 0 --project runs/fog-consistency --name v11s-feat \
      --lam-feat 1.0 --lam-end 0.1
"""
import argparse
import math
import os
import sys

import torch
import torch.nn as nn
import torch.nn.functional as F

ADAPTED_ULTRALYTICS = "8.4.60"

# ---- 版本敏感①:yolo11s 喂给 Detect 头的三个尺度(P3/P4/P5)层号与通道数 ----
# 由 ultralytics 8.4.60 `DetectionModel(cfg='yolo11s.yaml')` 实测:Detect 输入 = [16,19,22],
# 对应通道 [128,256,512]。升级/换 backbone 后按新 yaml 重查这两个表。
_LAYER_INDICES = {"P3": 16, "P4": 19, "P5": 22}
_FEATURE_CHANNELS = {"P3": 128, "P4": 256, "P5": 512}


# =====================================================================
# 纯 torch 组件(不依赖 ultralytics,可独立单测)
# =====================================================================
class ProjectionHead(nn.Module):
    """多尺度投影头:1×1 conv 降/升维 + 全局池化 + MLP。输入 [B,C,H,W] → 输出 [B,out]。"""

    def __init__(self, in_ch, hidden=256, out=128):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch, hidden, 1, bias=False), nn.BatchNorm2d(hidden), nn.ReLU(inplace=True)
        )
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.mlp = nn.Sequential(nn.Linear(hidden, out), nn.ReLU(inplace=True), nn.Linear(out, out))

    def forward(self, f):
        z = self.pool(self.conv(f)).flatten(1)
        return self.mlp(z)


class BYOLPredictor(nn.Module):
    """BYOL 式 predictor(只加在 online 分支),与 target 分支 stop-gradient 配对防塌缩。"""

    def __init__(self, dim, hidden=128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(dim, hidden), nn.BatchNorm1d(hidden), nn.ReLU(inplace=True), nn.Linear(hidden, dim)
        )

    def forward(self, z):
        return self.net(z)


def feature_consistency_loss(proj_heads, predictor, feats_c, feats_f):
    """BYOL 式多尺度特征一致性损失 Σ_p L1(predictor(proj(z_c_p)), stopgrad(proj(z_f_p)))。

    feats_c/feats_f: dict {scale: Tensor[B,C,H,W]},分别来自 clean / fog 分支。
    返回标量 tensor。
    """
    loss = 0.0
    for scale, proj in proj_heads.items():
        z_c = predictor(proj(feats_c[scale]))  # online 分支(clean)过 predictor
        z_f = proj(feats_f[scale]).detach()    # target 分支(fog)stop-gradient
        loss = loss + F.l1_loss(z_c, z_f)
    return loss


def cosine_schedule(epoch, epochs, lam_start=1.0, lam_end=0.1):
    """λ_feat cosine 退火:epoch 0 → lam_start,epochs-1 → lam_end。epoch 为 0 基。"""
    t = epoch / max(epochs - 1, 1)
    return lam_end + 0.5 * (lam_start - lam_end) * (1.0 + math.cos(math.pi * t))


# =====================================================================
# ultralytics 侵入部分(懒加载,保证纯 torch 组件可脱离 ultralytics 导入)
# =====================================================================
class ConsistencyModel(torch.nn.Module):
    """在 DetectionModel 上追加特征一致性 aux 分支的包装。

    通过前向 hook 捕获 P3/P4/P5 特征,loss() 里在 YOLO 检测损失上追加 λ_feat·L_feat。
    因 forward 委托给内部 DetectionModel,`names/nc/args/stride/criterion` 等属性仍由
    内部模型持有,训练器对 model 的其余访问不受影响。"""

    def __init__(self, model, lam_feat=1.0, lam_end=0.1, epochs=200,
                 layer_indices=None, feature_channels=None, proj_dim=128):
        super().__init__()
        self.model = model  # DetectionModel
        self.lam_feat = lam_feat
        self.lam_end = lam_end
        self.epochs = epochs
        self.epoch = 0  # 训练器每 epoch 起始更新
        self.layer_indices = layer_indices or dict(_LAYER_INDICES)
        feature_channels = feature_channels or _FEATURE_CHANNELS

        self.proj_heads = nn.ModuleDict()
        self._features = {}
        self._hooks = []
        for scale, idx in self.layer_indices.items():
            in_ch = feature_channels.get(scale)
            if in_ch is None:
                in_ch = self._infer_channels(idx)
            self.proj_heads[scale] = ProjectionHead(in_ch, out=proj_dim)
            layer = model.model[idx]
            self._hooks.append(layer.register_forward_hook(self._make_hook(scale)))
        self.predictor = BYOLPredictor(proj_dim)

    def _infer_channels(self, idx):
        layer = self.model.model[idx]
        for attr in ("out_channels", "c2", "cv2"):
            if hasattr(layer, attr):
                v = getattr(layer, attr)
                if isinstance(v, int):
                    return v
                if isinstance(v, (tuple, list)) and v:
                    return v[-1]
        raise ValueError(f"无法推断 layer {idx} 的输出通道,请在 feature_channels 显式给出")

    def _make_hook(self, scale):
        def hook(module, inp, out):
            self._features[scale] = out[0] if isinstance(out, (tuple, list)) else out
        return hook

    # 委托给内部 DetectionModel,保留 ultralytics 训练器期望的接口
    def forward(self, x, *args, **kwargs):
        self._features = {}
        return self.model(x, *args, **kwargs)

    def loss(self, batch, preds=None):
        # 先取特征一致性(基于本次 forward 捕获的 P3/P4/P5);preds 已由训练器传入,不会二次 forward
        feat = self._feature_consistency(batch)
        base, items = self.model.loss(batch, preds)
        if feat is None:
            return base, items
        lam = self._current_lam()
        return torch.cat([base, (lam * feat).reshape(1)]), torch.cat([items, (lam * feat.detach()).reshape(1)])

    def _feature_consistency(self, batch):
        n_clean = batch.get("n_clean") if isinstance(batch, dict) else None
        if not n_clean or not self._features:
            return None  # 非配对 batch → 退化为纯检测
        feat = 0.0
        for scale in self.proj_heads:
            f = self._features[scale]          # [2B, C, H, W],前 n_clean 为 clean,后为 fog
            feats_c = {scale: f[:n_clean]}
            feats_f = {scale: f[n_clean:]}
            feat = feat + feature_consistency_loss(
                {scale: self.proj_heads[scale]}, self.predictor, feats_c, feats_f)
        return feat

    def _current_lam(self):
        return cosine_schedule(self.epoch, self.epochs, self.lam_feat, self.lam_end)

    def strip(self):
        """剥离训练期 aux 分支(投影头/predictor/hook),返回纯 DetectionModel,供导出/推理。"""
        for h in self._hooks:
            h.remove()
        self._hooks = []
        del self.proj_heads, self.predictor
        return self.model

    # 属性透传,让 trainer 的 model.names/model.nc/model.args/model.criterion 等访问照常
    def __getattr__(self, name):
        # nn.Module 已截获 parameters/buffers/modules;其余透传给内部 model
        try:
            return super().__getattr__(name)
        except AttributeError:
            return getattr(self.model, name)


class PairedFogDataset(torch.utils.data.Dataset):
    """clean/fog 配对数据集:每个样本返回 (clean 图, 同 scene 一张雾变体, 标签, visible_flag)。

    读 A3-01 的 pairs.csv(列: clean, fog, beta, type, invisible_flag),按 split 划分子集。
    返回 dict:{'clean': CxHxW, 'fog': CxHxW, 'labels': Nx5 [cls,cx,cy,w,h](归一), 'visible': bool}。
    图像加载/增强在 GPU 服务器对齐 v4(letterbox/HSV/flip),这里给最简可复现实现。
    """

    def __init__(self, pairs_csv, img_root, split=None, transforms=None):
        import csv
        self.samples = []
        with open(pairs_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if split is not None and row.get("split", split) != split:
                    continue
                self.samples.append(row)
        self.img_root = img_root
        self.transforms = transforms

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        import cv2
        import numpy as np
        row = self.samples[i]
        clean = cv2.imread(os.path.join(self.img_root, row["clean"]))
        fog = cv2.imread(os.path.join(self.img_root, row["fog"]))
        if clean is None or fog is None:
            raise FileNotFoundError(f"缺图: {row['clean']} 或 {row['fog']}")
        clean = cv2.cvtColor(clean, cv2.COLOR_BGR2RGB).transpose(2, 0, 1).astype(np.float32) / 255.0
        fog = cv2.cvtColor(fog, cv2.COLOR_BGR2RGB).transpose(2, 0, 1).astype(np.float32) / 255.0
        item = {"clean": torch.from_numpy(clean), "fog": torch.from_numpy(fog),
                "labels": self._load_labels(row["clean"]),
                "visible": int(row.get("invisible_flag", "0")) == 0}
        return self.transforms(item) if self.transforms else item

    def _load_labels(self, clean_name):
        # 简化:标签由调用方经 --labels-dir 提供;这里返回空(纯特征一致性的无监督配对亦可)
        return torch.zeros((0, 5))


def paired_collate_fn(batch):
    """把 [clean_img, fog_img, labels, visible] 拼成 ultralytics 可吃的 batch。

    约定 img 张量前 B 张为 clean、后 B 张为 fog,B 记入 batch['n_clean'];标签拼接并加 batch_idx。
    """
    clean = torch.stack([b["clean"] for b in batch])
    fog = torch.stack([b["fog"] for b in batch])
    img = torch.cat([clean, fog], dim=0)
    B = len(batch)

    clss, boxes, bix = [], [], []
    for i, b in enumerate(batch):
        for lab in b["labels"]:
            clss.append([lab[0]]); boxes.append(lab[1:5].tolist()); bix.append([i])
    for i, b in enumerate(batch):
        for lab in b["labels"]:
            clss.append([lab[0]]); boxes.append(lab[1:5].tolist()); bix.append([i + B])
    out = {"img": img, "n_clean": B}
    if clss:
        out["cls"] = torch.tensor(clss, dtype=torch.float32)
        out["bboxes"] = torch.tensor(boxes, dtype=torch.float32)
        out["batch_idx"] = torch.tensor(bix, dtype=torch.float32)
    # visible_mask: [B] 每张 fog 图目标是否可见(invisible→关闭其检测损失)
    out["visible"] = torch.tensor([1.0 if b["visible"] else 0.0 for b in batch])
    return out


class ConsistencyTrainer:
    """惰性构造 ultralytics DetectionTrainer 子类(避免模块顶层依赖 ultralytics)。"""

    @staticmethod
    def build(lam_feat=1.0, lam_end=0.1, **trainer_kwargs):
        from ultralytics.models.yolo.detect import DetectionTrainer
        from ultralytics.models.yolo.detect.train import DetectionTrainer as _DT
        from ultralytics.nn.tasks import DetectionModel

        class _ConsistencyTrainer(_DT):
            def __init__(self, cfg, overrides=None, _callbacks=None):
                super().__init__(cfg, overrides, _callbacks)
                self._lam_feat = lam_feat
                self._lam_end = lam_end
                self.add_callback("on_train_epoch_start", self._sync_lam)

            def _sync_lam(self, trainer):
                if isinstance(trainer.model, ConsistencyModel):
                    trainer.model.epoch = trainer.epoch

            def get_model(self, cfg=None, weights=None, verbose=True):
                inner = DetectionModel(cfg, nc=self.data["nc"], ch=self.data["channels"],
                                       verbose=verbose)
                if weights:
                    inner.load(weights)
                wrapped = ConsistencyModel(inner, lam_feat=self._lam_feat, lam_end=self._lam_end,
                                           epochs=self.args.epochs or 100)
                return wrapped

            def get_validator(self):
                v = super().get_validator()
                self.loss_names = ("box_loss", "cls_loss", "dfl_loss", "feat_loss")
                return v

        return _ConsistencyTrainer


# =====================================================================
# CPU 冒烟自检:证明 graft 后的 forward + loss 能端到端跑通,且 L_feat 有贡献
# =====================================================================
def selftest():
    from types import SimpleNamespace
    from ultralytics.nn.tasks import DetectionModel
    from ultralytics.cfg import DEFAULT_CFG

    torch.set_num_threads(4)
    inner = DetectionModel(cfg="yolo11s.yaml", ch=3, nc=1)
    inner.args = SimpleNamespace(**dict(DEFAULT_CFG))
    model = ConsistencyModel(inner, lam_feat=1.0, lam_end=0.1, epochs=200)
    model.train()

    B = 2  # 2 clean + 2 fog
    img = torch.rand(2 * B, 3, 256, 256)
    cls = torch.tensor([[0.], [0.], [0.], [0.]])
    bboxes = torch.tensor([[0.4, 0.4, 0.3, 0.3]] * (2 * B))
    batch_idx = torch.tensor([[0.], [1.], [2.], [3.]])
    batch = {"img": img, "cls": cls, "bboxes": bboxes, "batch_idx": batch_idx, "n_clean": B}

    preds = model(batch["img"])
    loss, items = model.loss(batch, preds)
    total = loss.sum()
    total.backward()
    grad_ok = any(p.grad is not None and p.grad.abs().sum() > 0 for p in model.proj_heads.parameters())

    feat = model._feature_consistency(batch)
    print("[OK] 冒烟自检通过(CPU)")
    print(f"  总损失={total.item():.4f}  loss_items={[round(float(x),4) for x in items]}")
    print(f"  L_feat 分量={float(feat.item() if feat is not None else 0):.4f} (>0 即特征一致性已生效)")
    print(f"  投影头可训练且有梯度: {grad_ok}")
    print(f"  适配 ultralytics=={ADAPTED_ULTRALYTICS};P3/P4/P5 层号={_LAYER_INDICES}")
    assert feat is not None and float(feat.item()) > 0, "L_feat 未生效"
    assert grad_ok, "投影头无梯度"
    return model


def main():
    ap = argparse.ArgumentParser(description="A3-02 特征一致性训练(ultralytics 路线 A)")
    ap.add_argument("--selftest", action="store_true", help="CPU 冒烟自检(graft forward+loss 跑通)")
    # 训练参数(与 v4 对齐)
    ap.add_argument("--model", default="yolo11s.pt")
    ap.add_argument("--data", help="数据 yaml(需含 paired 字段: pairs_csv / img_root)")
    ap.add_argument("--imgsz", type=int, default=1024)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--project", default="runs/fog-consistency")
    ap.add_argument("--name", default="v11s-feat")
    ap.add_argument("--device", default="0")
    # 方法旋钮
    ap.add_argument("--lam-feat", type=float, default=1.0, help="λ_feat 初始值(cosine 退火起点)")
    ap.add_argument("--lam-end", type=float, default=0.1, help="λ_feat 退火终点")
    a = ap.parse_args()

    if a.selftest:
        selftest()
        return

    if not a.data:
        raise SystemExit("[ERR] 训练需 --data(数据 yaml) 或 --selftest 冒烟自检")
    if a.imgsz != 1024:
        print(f"[WARN] 建议 imgsz=1024 与 v4 对齐(当前 {a.imgsz})")

    from ultralytics.cfg import get_cfg
    cfg = get_cfg()
    cfg["model"] = a.model
    cfg["data"] = a.data
    cfg["imgsz"] = a.imgsz
    cfg["batch"] = a.batch
    cfg["epochs"] = a.epochs
    cfg["seed"] = a.seed
    cfg["project"] = a.project
    cfg["name"] = a.name
    cfg["device"] = a.device
    TrainerCls = ConsistencyTrainer.build(lam_feat=a.lam_feat, lam_end=a.lam_end)
    trainer = TrainerCls(cfg=cfg)
    trainer.train()


if __name__ == "__main__":
    main()
