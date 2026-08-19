#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A3-02 特征一致性训练(路线 A:ultralytics Trainer 子类化)——把「接口骨架」变成能出消融表的真训练

适配版本: ultralytics==8.4.98 / torch 2.13(2026-08 在训练机与本机 venv 实测)。升级 ultralytics 时
只需核对本文件三处「版本敏感」内容:
  1. _LAYER_INDICES / _FEATURE_CHANNELS —— yolo11s 喂给 Detect 头的 P3/P4/P5 层号与通道数;
  2. _do_train 数据路径:8.4.x 是 ``self.model(batch)``(整包 dict 进 forward),不是旧版
     ``preds = self.model(batch["img"]); loss = self.model.loss(batch, preds)``;
     ConsistencyModel.forward 已兼容两种(见 forward),升级时核对 _do_train 的实际调用;
  3. get_dataset / get_dataloader 的签名(8.4.98 实测),以及 _setup_train 里
     ``self.get_dataloader(self.get_dataset(), batch_size=..., rank=..., mode=...)`` 的实参。

方法(与《抗雾感知特征一致性训练方案》§12 评审修正一致):
    L = L_yolo(clean) + L_yolo(fog)·visible_mask + λ_feat·Σ_{p∈P3,P4,P5} ||proj(z_f_p) − proj(z_c_p)||₁
  - 检测版只做 backbone/FPN 多尺度特征一致性,不做检测头输出一致性(不设 L_cons);
  - BYOL 式 stop-gradient + predictor 防塌缩(不用 InfoNCE,单卡 batch 小、负样本不够);
  - P3/P4/P5 多尺度投影头(1×1 conv + 全局池化 + MLP);
  - invisible 样本关闭检测损失(visible_mask 由 A3-01 的 pairs.csv 给出);
  - λ_feat cosine 退火(λ_feat → λ_end);
  - 推理零开销:投影头只是训练期 aux 分支,导出用 strip() 剥离。

数据管线(P1-07 审查的 3 缺口 + 新发现 1 项,已一并修复):
  [缺口一] 配对数据从未接入训练器 → 现在重写 get_dataset/get_dataloader,返回 PairedFogDataset
            + paired_collate_fn,并补 letterbox(clean/fog 同缩放,标签归一化坐标不变);
  [缺口二] 标签恒为空 → 现在 _load_labels 按 YOLO 格式读 labels_root/<stem>.txt;
  [缺口三] visible 掩码算了没用 → collate 里 invisible 的 fog 样本不再追加检测标签;
  [缺口四] forward 不路由 dict → 8.4.x _do_train 的 self.model(batch) 会绕过包装器 loss()。
           现在 forward(dict) → self.loss(batch),L_feat 在真实训练里才真正生效。
  [自检]   --data-smoke 落一个 on-disk 小型配对数据集,走真实 get_dataloader 拉 batch,
            断言 n_clean 存在且 L_feat>0(能一次性拦住以上 4 个缺口)。

本文件可独立导入;纯 torch 组件(ProjectionHead/BYOLPredictor/feature_consistency_loss/
cosine_schedule)不依赖 ultralytics。GPU 训练入口见文件尾 main()。

用法(需 GPU,协议与 v4 对齐: yolo11s / imgsz=1024 / batch=8 / epochs=200 / seed=0):
  python patch_ultralytics_for_consistency.py \
      --model yolo11s.pt --data data/paired/pairs_fog.yaml --imgsz 1024 \
      --batch 8 --epochs 200 --seed 0 --project runs/fog-consistency --name v11s-feat \
      --lam-feat 1.0 --lam-end 0.1

数据 yaml(pairs_fog.yaml)需同时满足 ultralytics 的 check_det_dataset 与本文件的 paired 字段:
  path: /abs/path/to/data/paired        # 所有相对路径相对此目录
  train: images/train                    # 标准 YOLO 键(check_det_dataset 需要,目录须存在)
  val: images/val
  nc: 1
  names: {0: defect}
  paired:
    pairs_csv: pairs.csv                 # 列: clean, fog, beta, type, invisible_flag, split
    img_root: .                          # pairs.csv 里 clean/fog 相对此目录
    labels_root: labels                  # <图片 basename 去扩展名>.txt,每行 "cls cx cy w h"(归一化)
    train_split: train                   # pairs.csv 的 split 列取值,用于划分
    val_split: val
"""
import argparse
import math
import os
import sys

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

ADAPTED_ULTRALYTICS = "8.4.98"

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


class _FeatureHook:
    """可 pickle 的前向 hook(闭包不能 pickle,ultralytics save_model 会 torch.save 整个
    模型图,闭包 hook 直接炸;类实例可序列化)。写入宿主 ConsistencyModel._features。"""

    def __init__(self, owner, scale):
        self.owner = owner
        self.scale = scale

    def __call__(self, module, inp, out):
        self.owner._features[self.scale] = out[0] if isinstance(out, (tuple, list)) else out


# =====================================================================
# ultralytics 侵入部分(懒加载,保证纯 torch 组件可脱离 ultralytics 导入)
# =====================================================================
class ConsistencyModel(torch.nn.Module):
    """在 DetectionModel 上追加特征一致性 aux 分支的包装。

    通过前向 hook 捕获 P3/P4/P5 特征,loss() 里在 YOLO 检测损失上追加 λ_feat·L_feat。
    forward 对 dict(整包 batch)走 self.loss —— 匹配 8.4.x _do_train 的 ``self.model(batch)``
    结构;对张量(推理/冒烟)委托给内部 DetectionModel。`names/nc/args/stride/criterion`
    等属性仍由内部模型持有,训练器对 model 的其余访问不受影响。"""

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
            self._hooks.append(layer.register_forward_hook(_FeatureHook(self, scale)))
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

    def forward(self, x, *args, **kwargs):
        # [缺口四] 8.4.x _do_train 用 self.model(batch) 喂整包 dict;dict 必须走我们的
        # loss()(内部 DetectionModel 会把 dict 短路到它自己的 loss,吃掉 L_feat)。
        if isinstance(x, dict):
            return self.loss(x, *args, **kwargs)
        self._features = {}
        return self.model(x, *args, **kwargs)

    def loss(self, batch, preds=None):
        img = batch["img"]
        if preds is None:
            # 旧版结构(或外部直接调 loss(batch)):先前向一次填充 hook 特征 + 得到 preds
            self._features = {}
            preds = self.model(img)
        # 内部 DetectionModel.loss 会用它自己的 criterion 算检测损失(传 preds 避免二次前向)
        base, items = self.model.loss(batch, preds)
        # 版本敏感:DetectionLoss 返回 [3,] 向量;升级后若变 0 维标量,cat 会崩
        assert base.ndim >= 1, "DetectionLoss 返回标量?需要重写 loss 拼接(版本敏感点)"
        feat = self._feature_consistency(batch)
        if feat is None:
            # 非配对 batch(如验证器自建的常规 YOLO 数据,无 n_clean)→ L_feat=0。
            # 仍返回 4 维向量,兼容 validator 的 self.loss(zeros_like(4))累加。
            z = torch.zeros(1, dtype=base.dtype, device=base.device)
            return torch.cat([base, z]), torch.cat([items, z])
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

    读 A3-01 的 pairs.csv(列: clean, fog, beta, type, invisible_flag, split),按 split 划分子集。
    返回 dict:{'clean': CxHxW uint8 RGB, 'fog': 同, 'labels': Nx5 [cls,cx,cy,w,h](归一), 'visible': bool}。
    clean 与 fog 同源同尺寸,letterbox 参数一致 → 归一化标签坐标不因 padding 而偏。
    输出与 ultralytics build_dataset 的 Format 一致(CHW uint8 RGB,训练循环里由
    preprocess_batch 做 /255),保证 batch 契约对得上。
    """

    def __init__(self, pairs_csv, img_root, labels_root, split=None, imgsz=1024):
        import csv
        self.samples = []
        with open(pairs_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if split is not None and row.get("split", split) != split:
                    continue
                self.samples.append(row)
        self.img_root = img_root
        self.labels_root = labels_root
        self.imgsz = imgsz

    def __len__(self):
        return len(self.samples)

    @property
    def labels(self):
        """ultralytics 的 get_class_counts(读 cls)/plot_training_labels(读 bboxes)会访问
        dataset.labels;配对数据集不显式带这两个向量,返回空 → 类权重退化为 1、标签图为空,
        不扭曲训练。"""
        return [{"cls": torch.zeros((0,), dtype=torch.float32),
                 "bboxes": torch.zeros((0, 4), dtype=torch.float32)} for _ in self.samples]

    def _letterbox(self, img):
        """等比缩放 + 对称 pad 到 imgsz(对齐 ultralytics 协议)。
        返回 (uint8 HWC BGR, ratio_pad=(r, (dw, dh)))。"""
        import cv2
        h, w = img.shape[:2]
        r = min(self.imgsz / h, self.imgsz / w)
        nh, nw = max(1, round(h * r)), max(1, round(w * r))
        img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        top = (self.imgsz - nh) // 2
        bottom = self.imgsz - nh - top
        left = (self.imgsz - nw) // 2
        right = self.imgsz - nw - left
        img = cv2.copyMakeBorder(img, top, bottom, left, right,
                                 cv2.BORDER_CONSTANT, value=(114, 114, 114))
        return img, (r, (left, top))

    def __getitem__(self, i):
        import cv2
        row = self.samples[i]
        clean_raw = cv2.imread(os.path.join(self.img_root, row["clean"]))
        fog_raw = cv2.imread(os.path.join(self.img_root, row["fog"]))
        if clean_raw is None or fog_raw is None:
            raise FileNotFoundError(f"缺图: {row['clean']} 或 {row['fog']}")
        ori_shape = tuple(clean_raw.shape[:2])  # letterbox 前的原图 (h, w),验证 scale_boxes 需要
        clean, clean_rp = self._letterbox(clean_raw)
        fog, fog_rp = self._letterbox(fog_raw)
        assert clean_rp == fog_rp, "clean/fog 同源同尺寸,ratio_pad 应一致"
        # BGR HWC → RGB CHW uint8(与 ultralytics Format 一致)
        item = {"clean": torch.from_numpy(np.ascontiguousarray(clean.transpose(2, 0, 1)[::-1])),
                "fog": torch.from_numpy(np.ascontiguousarray(fog.transpose(2, 0, 1)[::-1])),
                "labels": self._load_labels(row["clean"]),
                "visible": int(row.get("invisible_flag", "0")) == 0,
                "im_file": [os.path.join(self.img_root, row["clean"]),
                            os.path.join(self.img_root, row["fog"])],
                "ori_shape": ori_shape,     # (h, w)
                "ratio_pad": clean_rp}      # (r, (dw, dh)),与 ultralytics 契约一致
        return item

    def _load_labels(self, clean_relpath):
        """[缺口二] 按 YOLO 格式读 labels_root/<basename 去扩展名>.txt(每行 cls cx cy w h,归一化)。"""
        stem = os.path.splitext(os.path.basename(clean_relpath))[0]
        txt = os.path.join(self.labels_root, stem + ".txt")
        if not os.path.isfile(txt):
            return torch.zeros((0, 5), dtype=torch.float32)
        labs = np.loadtxt(txt, ndmin=2, dtype=np.float32)
        if labs.ndim == 1:
            labs = labs.reshape(1, -1)
        if labs.shape[1] < 5:  # 空行/缺列 → 视为无标签
            return torch.zeros((0, 5), dtype=torch.float32)
        return torch.from_numpy(labs[:, :5].astype(np.float32))


def paired_collate_fn(batch):
    """把 [clean_img, fog_img, labels, visible] 拼成 ultralytics 可吃的 batch。

    约定 img 张量前 B 张为 clean、后 B 张为 fog,B 记入 batch['n_clean'];标签拼接并加 batch_idx。
    [缺口三] invisible 的 fog 样本不追加检测标签(雾吞掉的目标不该强训),退化为纯 L_feat 配对。
    """
    clean = torch.stack([b["clean"] for b in batch])
    fog = torch.stack([b["fog"] for b in batch])
    img = torch.cat([clean, fog], dim=0)
    B = len(batch)

    clss, boxes, bix = [], [], []
    for i, b in enumerate(batch):            # clean 段(i)始终有标签
        for lab in b["labels"]:
            clss.append([lab[0]]); boxes.append(lab[1:5].tolist()); bix.append(i)
    for i, b in enumerate(batch):            # fog 段(i+B):仅 visible=1 追加
        if b["visible"]:
            for lab in b["labels"]:
                clss.append([lab[0]]); boxes.append(lab[1:5].tolist()); bix.append(i + B)
    out = {"img": img, "n_clean": B}
    if clss:
        out["cls"] = torch.tensor(clss, dtype=torch.float32)
        out["bboxes"] = torch.tensor(boxes, dtype=torch.float32)
        out["batch_idx"] = torch.tensor(bix, dtype=torch.float32)  # 扁平 (N,),与 ultralytics 契约一致
    else:  # 空 batch 兜底(ultralytics 的 loss 需要这些键)
        out["cls"] = torch.zeros((0, 1), dtype=torch.float32)
        out["bboxes"] = torch.zeros((0, 4), dtype=torch.float32)
        out["batch_idx"] = torch.zeros((0,), dtype=torch.float32)
    out["visible"] = torch.tensor([1.0 if b["visible"] else 0.0 for b in batch])
    out["im_file"] = [p for b in batch for p in b["im_file"]]  # plot_training_samples 需要
    # 验证器 _prepare_batch 需要 per-image 的 ori_shape / ratio_pad(每样本贡献 2 张图,共 2B 条)
    out["ori_shape"] = [b["ori_shape"] for b in batch for _ in (0, 1)]
    out["ratio_pad"] = [b["ratio_pad"] for b in batch for _ in (0, 1)]
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

            # ---- 数据管线(缺口一):配对数据接入 ----
            # get_dataset 保持基类不动(8.4.98 BaseTrainer.get_dataset 只做「解析 yaml →
            # self.data 数据字典」,不建 Dataset;训练器用它拿 nc/names,不能覆盖)。
            def _paired_cfg(self, mode="train"):
                """自 yaml 解析配对字段,相对路径以 yaml 所在目录为基准。不依赖 ultralytics
                的 check_det_dataset,冒烟/训练都能独立工作。"""
                import yaml
                with open(self.args.data, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                paired = cfg.get("paired", {})
                base = os.path.dirname(os.path.abspath(self.args.data))
                split_key = "val_split" if mode == "val" else "train_split"
                return {
                    "pairs_csv": os.path.join(base, paired.get("pairs_csv", "pairs.csv")),
                    "img_root": os.path.join(base, paired.get("img_root", ".")),
                    "labels_root": os.path.join(base, paired.get("labels_root", "labels")),
                    "split": paired.get(split_key, mode),
                }

            def get_dataloader(self, dataset_path, batch_size=16, rank=0, mode="train"):
                """接管 DataLoader:返回 PairedFogDataset + paired_collate_fn。

                8.4.98 实参形态:(dataset_path, batch_size, rank, mode);dataset_path 忽略,
                train/val 由 mode 决定。注意:验证阶段同样走配对数据(visible 掩码已按配对
                语义剔除 invisible 标签);如需「验证用纯 clean 的常规 YOLO 度量」,后续在
                get_validator 里换成标准 build_yolo_dataset 即可(见文档备注)。
                """
                cfg = self._paired_cfg(mode)
                ds = PairedFogDataset(cfg["pairs_csv"], cfg["img_root"], cfg["labels_root"],
                                      split=cfg["split"], imgsz=self.args.imgsz)
                return torch.utils.data.DataLoader(
                    ds, batch_size=batch_size, shuffle=(mode == "train"),
                    collate_fn=paired_collate_fn, num_workers=0)

            def get_model(self, cfg=None, weights=None, verbose=True):
                inner = DetectionModel(cfg, nc=self.data["nc"], ch=self.data.get("channels", 3),
                                       verbose=verbose)
                if weights:
                    inner.load(weights)
                wrapped = ConsistencyModel(inner, lam_feat=self._lam_feat, lam_end=self._lam_end,
                                           epochs=self.args.epochs or 100)
                return wrapped

            def label_loss_items(self, loss_items=None, prefix="train"):
                """基类只记 3 列(box/cls/dfl);我们 4 项,补第 4 列 feat_loss 进 results.csv。"""
                keys = [f"{prefix}/box_loss", f"{prefix}/cls_loss",
                        f"{prefix}/dfl_loss", f"{prefix}/feat_loss"]
                if loss_items is not None:
                    return dict(zip(keys, [round(float(x), 5) for x in loss_items]))
                return keys

            def set_model_attributes(self):
                """基类把 nc/names/args 赋给包装器;检测损失 v8DetectionLoss 读的是内部
                DetectionModel.args,这里镜像到内层(缺了它 loss 会 AttributeError)。"""
                super().set_model_attributes()
                inner = getattr(self.model, "model", None)
                if inner is not None:
                    for k in ("nc", "names", "args"):
                        if hasattr(self.model, k):
                            setattr(inner, k, getattr(self.model, k))

            def get_validator(self):
                v = super().get_validator()
                self.loss_names = ("box_loss", "cls_loss", "dfl_loss", "feat_loss")
                return v

        return _ConsistencyTrainer


# =====================================================================
# CPU 冒烟自检
# =====================================================================
def selftest():
    """模型级冒烟:包装器的 forward + loss 端到端跑通,L_feat 有贡献(不覆盖数据管线)。"""
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

    # 走真实训练结构: self.model(batch) 整包进 forward → 内部转 loss()
    loss, items = model(batch)
    total = loss.sum()
    total.backward()
    grad_ok = any(p.grad is not None and p.grad.abs().sum() > 0 for p in model.proj_heads.parameters())

    feat = model._feature_consistency(batch)
    print("[OK] 模型级冒烟通过(CPU)")
    print(f"  总损失={total.item():.4f}  loss_items={[round(float(x),4) for x in items]}")
    print(f"  L_feat 分量={float(feat.item() if feat is not None else 0):.4f} (>0 即特征一致性已生效)")
    print(f"  投影头可训练且有梯度: {grad_ok}")
    print(f"  适配 ultralytics=={ADAPTED_ULTRALYTICS};P3/P4/P5 层号={_LAYER_INDICES}")
    assert feat is not None and float(feat.item()) > 0, "L_feat 未生效"
    assert grad_ok, "投影头无梯度"
    return model


def data_path_smoke(root=None):
    """数据路径冒烟(用户点名的"最有价值自检"):落一个 on-disk 小型配对数据集,
    build() → trainer.get_dataloader() 拉真实 batch,断言 n_clean 存在且 L_feat>0。

    一次性拦住 4 个缺口:数据集未接入、标签没加载、visible 掩码没生效、
    dict 没路由到 loss()。对任意目标机(训练机/本机)都能跑,几分钟内完成。
    """
    import shutil
    import subprocess
    import tempfile
    import yaml
    import cv2

    root = root or tempfile.mkdtemp(prefix="a3_datas_moke_")
    os.makedirs(os.path.join(root, "images", "train"), exist_ok=True)
    os.makedirs(os.path.join(root, "images", "val"), exist_ok=True)
    os.makedirs(os.path.join(root, "labels"), exist_ok=True)

    rng = np.random.default_rng(0)
    n_train, n_val = 2, 1  # train 2 张(batch=2 恰好同批),其中 1 张 invisible 验证掩码
    rows = []
    for i, (n, split) in enumerate([(n_train, "train")] + [(n_val, "val")]):
        for j in range(n):
            img = (rng.uniform(40, 120, (240, 320, 3))).astype(np.uint8)
            cv2.rectangle(img, (120, 90), (200, 150), (255, 255, 255), -1)  # 合成"缺陷"
            fog = cv2.GaussianBlur(img, (7, 7), 0)
            fog = np.clip(fog * 0.6 + 40, 0, 255).astype(np.uint8)
            stem = f"img_{split}_{j}"
            cv2.imwrite(os.path.join(root, "images", split, f"{stem}.jpg"), img)
            cv2.imwrite(os.path.join(root, "images", split, f"{stem}_fog.jpg"), fog)
            # 归一化 YOLO 标签:中心(0.5,0.5),宽高(0.25,0.25)
            with open(os.path.join(root, "labels", f"{stem}.txt"), "w") as f:
                f.write(f"0 0.5 0.5 0.25 0.25\n")
            visible = 0 if (split == "train" and j == 1) else 1  # train 里留 1 张 invisible
            rows.append({"clean": f"images/{split}/{stem}.jpg", "fog": f"images/{split}/{stem}_fog.jpg",
                         "beta": 0.8, "type": "synthetic", "invisible_flag": visible, "split": split})
    import csv
    with open(os.path.join(root, "pairs.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["clean", "fog", "beta", "type", "invisible_flag", "split"])
        w.writeheader(); w.writerows(rows)

    yaml_path = os.path.join(root, "pairs_fog.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump({
            "path": root, "train": os.path.join("images", "train"), "val": os.path.join("images", "val"),
            "nc": 1, "names": {0: "defect"},
            "paired": {"pairs_csv": "pairs.csv", "img_root": ".", "labels_root": "labels",
                       "train_split": "train", "val_split": "val"}}, f, allow_unicode=True)

    # 走真实训练器构建
    from ultralytics.cfg import get_cfg
    cfg = get_cfg()  # IterableSimpleNamespace:无 update/to_dict/下标,只能 setattr
    for k, v in {"model": "yolo11s.yaml", "data": yaml_path, "imgsz": 320, "batch": 2,
                 "epochs": 1, "seed": 0, "device": "cpu",
                 "project": os.path.join(root, "runs"), "name": "smoke", "workers": 0}.items():
        setattr(cfg, k, v)
    TrainerCls = ConsistencyTrainer.build(lam_feat=1.0, lam_end=0.1)
    trainer = TrainerCls(cfg=cfg, overrides={})  # 8.4.98 BaseTrainer 直接 overrides.pop,须传 dict
    trainer.data = {"nc": 1, "channels": 3, "names": {0: "defect"}}
    trainer.setup_model()
    trainer.set_model_attributes()  # 把 nc/names/args 镜像到内层 DetectionModel(否则 loss 报 AttributeError)

    dl = trainer.get_dataloader(None, batch_size=2, rank=0, mode="train")
    batch = next(iter(dl))
    assert "n_clean" in batch, "batch 缺 n_clean(数据集未接入)"
    n_clean = int(batch["n_clean"])
    assert n_clean == 2, f"n_clean 应为 2,实际 {n_clean}"
    assert batch["img"].shape[0] == 2 * n_clean, f"img 应为 2B={2*n_clean} 张,实际 {batch['img'].shape[0]}"
    n_det = int(batch["cls"].shape[0])
    assert n_det == 3, f"visible 掩码未生效: 期望 3 个检测标签(2 clean + 1 fog-visible, invisible 的 fog 已剔除),实际 {n_det}"
    assert sorted(batch["visible"].tolist()) == [0.0, 1.0], "visible 掩码异常(应有 visible 与 invisible 各 1)"
    assert "ori_shape" in batch and len(batch["ori_shape"]) == 2 * n_clean, \
        "batch 缺 per-image ori_shape(验证器 _prepare_batch 需要)"
    assert "ratio_pad" in batch and len(batch["ratio_pad"]) == 2 * n_clean, \
        "batch 缺 per-image ratio_pad(验证器 _prepare_batch 需要)"

    # 走真实训练循环的前向路径: preprocess_batch(img/255) → model(batch)
    img = batch["img"].float() / 255.0
    batch_f = dict(batch); batch_f["img"] = img
    loss, items = trainer.model(batch_f)
    feat_loss = float(items[-1].item()) if items is not None and len(items) else 0.0
    total = float(loss.sum().item())
    assert feat_loss > 0, f"L_feat=0(特征一致性未生效);loss_items={items}"
    assert abs(items[3].item() - feat_loss) < 1e-6, "feat_loss 应是 loss 第 4 项"

    print("[OK] 数据路径冒烟通过(CPU, on-disk)")
    print(f"  batch: n_clean={n_clean}, img={tuple(batch['img'].shape)}, "
          f"det 标签数={batch['cls'].shape[0]}(fog invisible 已按掩码剔除)")
    print(f"  总损失={total:.4f}, loss_items={[round(float(x), 6) for x in items]}, L_feat>0 ✅")
    print(f"  冒烟数据在: {root}")
    return root


def main():
    ap = argparse.ArgumentParser(description="A3-02 特征一致性训练(ultralytics 路线 A)")
    ap.add_argument("--selftest", action="store_true", help="模型级冒烟(forward+loss 跑通)")
    ap.add_argument("--data-smoke", nargs="?", const="_auto", metavar="DIR",
                    help="on-disk 数据路径冒烟(真实 dataloader,断言 n_clean + L_feat>0);"
                         "可选 DIR 指定冒烟数据目录(默认临时目录)")
    # 训练参数(与 v4 对齐)
    ap.add_argument("--model", default="yolo11s.pt")
    ap.add_argument("--data", help="数据 yaml(需含 paired 字段: pairs_csv / img_root / labels_root)")
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
    if a.data_smoke:
        root = None if a.data_smoke == "_auto" else a.data_smoke
        data_path_smoke(root)
        return

    if not a.data:
        raise SystemExit("[ERR] 训练需 --data(数据 yaml) 或 --selftest / --data-smoke 冒烟自检")
    if a.imgsz != 1024:
        print(f"[WARN] 建议 imgsz=1024 与 v4 对齐(当前 {a.imgsz})")

    from ultralytics.cfg import get_cfg
    cfg = get_cfg()  # IterableSimpleNamespace:无 update/to_dict/下标,只能 setattr
    for k, v in {"model": a.model, "data": a.data, "imgsz": a.imgsz, "batch": a.batch,
                 "epochs": a.epochs, "seed": a.seed, "project": a.project,
                 "name": a.name, "device": a.device}.items():
        setattr(cfg, k, v)
    TrainerCls = ConsistencyTrainer.build(lam_feat=a.lam_feat, lam_end=a.lam_end)
    trainer = TrainerCls(cfg=cfg, overrides={})  # 8.4.98 BaseTrainer 直接 overrides.pop,须传 dict
    trainer.train()


if __name__ == "__main__":
    main()
