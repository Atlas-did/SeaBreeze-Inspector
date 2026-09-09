# A4-02 小目标增强·检测专用 Copy-Paste：手写实现与数据制造纪律

> 本模块第二篇。**用目标级 Copy-Paste 提升小目标样本密度。注意 ultralytics 检测模式下 `copy_paste` 参数不生效（它是实例分割专属），必须手写增广。**
> 前置：A1-01 锁定 split；A2-03 尺寸分档。证据层 L3。

## 〇、前置判断

Copy-Paste 的真正作用是**增加"小目标正样本"的密度**，不是增加类别数量或信息量。它对小目标有效的前提：粘贴后目标在物理上仍可识别（不遮挡、不越界、不光照矛盾）。如果只是机械地把小目标贴到随机背景，模型会学"贴片痕迹"而不是"缺陷外观"——那是负收益。

## 一、问题严格定义

- 输入：锁定 train 集的图 + bbox；输出：增广后的训练批次（内存中，不落盘或落盘可复现）。
- 粘贴操作：从标注目标集里采一个目标 patch（含其 bbox），几何变换（缩放/旋转小角度）后贴到另一背景图，bbox 同步变换。
- 约束：不越界、不与已有 bbox 冲突（可允许轻微重叠但需评估）、类比例受控（不改变整体类别平衡，除非专门研究）。

## 二、该做什么

1. 实现增广：在 dataloader 层做（或 albumentations 的自定义变换），不要修改检测主循环。
2. 关键参数：粘贴概率 $$p\in\{0.2,0.4\}$$、目标尺度缩放范围、是否过滤小目标（面积<阈值不贴，防止放大失真）。
3. 与 mosaic/其他增强的组合顺序写入 config，保证可复现。
4. 消融：开/关 copy-paste；在同锁定 test 上报告 AP_S、AP_M、AP_L、P/R/F1。
5. 检查副作用：是否引入"贴片痕迹"可检测伪影（用未参与训练的人工看图或专门特征）。

## 三、技术方案（要点）

- 检测模式下 `copy_paste` 不生效——这一点已在样本文档 §12 修正；若用 ultralytics，需要自定义 Dataset/dataloader 或在预处理管线里做。
- 实现伪代码：

```python
def copy_paste_sample(image, boxes, obj_pool, p=0.3):
    rng = np.random.default_rng(seed)
    if rng.random() > p: return image, boxes
    obj = obj_pool[rng.integers(len(obj_pool))]   # 一个目标 patch(图块+box)
    scale = rng.uniform(0.7, 1.3)
    patch = resize(obj.img, scale); box = scale(obj.box)
    x, y = rng.integers(0, W-box.w), rng.integers(0, H-box.h)
    if max_iou(box, boxes) > 0.3: return image, boxes   # 冲突跳过
    image[y:y+h, x:x+w] = patch
    return image, np.vstack([boxes, box])
```

- 关键：obj_pool 来自**训练集**本身（不要引入域外目标贴进本项目图，那会制造虚假的"跨域"数据）。

## 四、数据层

- 只用锁定 train 集。obj_pool 也来自 train。
- 若目标类别极少，可先在 train 上做类别感知的采样，保证贴的类别分布受控。
- 生成数据若落盘：每个增广样本打 `aug_id, source_id, pasted_targets` 标签，便于审计。

## 五、可能踩的坑

1. **贴到矛盾背景**：叶片裂纹贴到天空或海面上，模型学到"这里有个矩形补丁"而不是裂纹特征。限制粘贴区域（只贴到叶片分割区域内，若有）。
2. **过度粘贴**：目标密度超过真实场景，模型学会"每张图都有很多框"，FN 下降但 P 崩。
3. **小目标贴上去被放大失真**：源 patch 分辨率低，resize 后模糊，模型学到的还是模糊的"小缺陷模板"。
4. **与 mosaic 双重退化**：mosaic 本身会缩小目标，再 copy-paste 可能产生严重伪影；组合顺序要在 val 上验证。
5. **bbox 未同步变换**：几何变换后 box 忘了跟着变，训练标签错位。
6. **类别比例失控**：少样本类被疯狂粘贴，变相过拟合该类模板。加 clamp。
7. **把增广收益说成"数据增强泛化"**：copy-paste 提升主要来自小目标密度，不是样本多样性；论文措辞写清楚。

## 六、评估指标与消融设计

- 主表：B / B+CP(p=0.2) / B+CP(p=0.4) / B+CP+类别受限，报告 mAP@0.5、AP_S/M/L、P/R。
- 副作用检查：增广样本人工看图（每配置 ≥50 张），记录"明显贴片伪影"比例。
- 结论模板：`在锁定测试集上，目标级 Copy-Paste 使 AP_S 提升 Δ，未见 Precision 明显下降`。

## 七、论文写法

可写：

> 采用目标级 Copy-Paste 增强（粘贴概率 p=0.3，受限粘贴区域）提升小目标样本密度，AP_S 提升 Δ，Precision 变化为……。

禁写：`Copy-Paste 增加数据多样性`（它增加密度不是多样性）、`小目标已解决`、未报告 P 的 AP_S 提升。

## 八、诚实自评锚点

- **可交付**：可复现增广实现 + 消融表 + 贴片伪影抽样审计。
- **部分完成**：只实现未消融 → 只报实现，不写 AP 收益。
- **不可声称**：AP 提升（未在同一锁定 test 验证）、泛化提升（未做域外测试）。
- **停止线**：无法从锁定 train 构造 obj_pool、或 bbox 同步无法验证时，停止该路线。
