# P1-08 · A2 train_cli 死参数清理 —— 让训练命令行「没有传了不生效的坑」

> 对应计划:`SeaBreeze_攻坚计划_v1.md` P1-8 · 证据脚本 `research/专项/A2/train_cli.py`
> 一句话结论:**`--cls_pw` 参数被解析了但根本没传进 `model.train()`,而且 ultralytics 没有这个参数——想用它调类别权重的人会被无声地骗走**。清理方案:删除死参数,换成 ultralytics 真正生效的 `fl_gamma`(focal loss)与类别加权方案,并加一个「训练后回读 args.yaml 确认参数生效」的自检。这是 15 分钟的小活,但对「训练可复现、参数口径一致」是必要的。

---

## 1. 结论先行

| 项 | 现状 | 改造后 |
|---|---|---|
| `--cls_pw` | 解析了但从未使用 | 删除;换成 `fl_gamma`(ultralytics 原生 focal loss gamma) |
| 类别不平衡处理 | 无(只能靠默认) | 显式支持 `--fl_gamma`,必要时数据集级类别权重 |
| 复现自检 | 无 | 训练完成后回读 `args.yaml`,打印关键参数确认生效 |
| 文档一致性 | 参数表与代码行为不符 | `--help` 输出与代码行为一致 |

**为什么值得做**:训练 CLI 是「多轮训练(11s/8s、binary/multi-class、v4/v5 各版本)」的门面。你后面要跑很多轮,`--cls_pw` 这种「传了没反应」的死参数会在某轮被误信——比如有人以为开了类别权重,实际没开,结果和结论就悄悄偏了。训练代码的**参数诚实性**是「pipeline 稳定无问题」的一部分。

---

## 2. 问题定位(代码实锤)

`train_cli.py`:

```python
ap.add_argument('--cls_pw', type=float, default=1.0,
                help='类别权重倍率(1.0=默认自动按频率)')   # 解析了
...
model.train(
    data=a.data, imgsz=a.imgsz, batch=a.batch, epochs=a.epochs,
    seed=a.seed, project=a.project, name=a.name,
    device=a.device, patience=a.patience,
    fliplr=0.5, mosaic=1.0, hsv_h=0.015, hsv_s=0.7, hsv_v=0.4,
)   # ← 这里没有 a.cls_pw
```

1. `--cls_pw` 被 `parse_args()` 解析,但 `model.train()` 调用里**没有任何 `a.cls_pw` 的传递**;
2. ultralytics 的 `train()` 参数里**不存在 `cls_pw`**(正确拼写无关,它根本没有这个参数名;有 `cls` 指类别损失增益、`fl_gamma` 指 focal loss 伽马);
3. 后果:传 `--cls_pw 2.0` 会静默无效——**不报错、不生效**。help 文案「类别权重倍率」还暗示它有效。

**同一脚本里其他值得顺带核实的点**:
- `patience=50` 默认早停:多轮训练要固定口径(评审关心「best checkpoint 按什么规则选」),建议把 `patience` 的语义写进注释或打印(当前 v4 按 mAP50-95 选 best 的规则不在 CLI 里);
- 增强参数(fliplr/mosaic/hsv)是硬编码而非参数:多轮对比时**必须保持一致**(或显式传参),否则对比不干净——建议提到 `--fliplr` 等可选参数,默认值沿用 v4。

---

## 3. 改造方案(15 分钟)

### 3.1 删除死参数,换真参数

```python
ap.add_argument('--fl_gamma', type=float, default=0.0,
                help='focal loss 伽马(0=关闭;类别不平衡时 1.5~2.0)')
# 删除 --cls_pw
```

`model.train(...)` 增加 `fl_gamma=a.fl_gamma`。

### 3.2 类别权重:用 ultralytics 官方路径,别自造

- ultralytics 检测任务对类别不平衡的标准做法是 **focal loss**(`fl_gamma`)而不是手动类权重;`--cls`(类别损失增益)也可用但语义不同;
- 若确实需要按训练集频率加权,在数据准备侧做(如 `data/processed/*.yaml` 里标注样本数),CLI 不重复造;
- **文档同步**:把 `--help` 的文案与 README 的用法对齐,写明「类别不平衡的入口是 `--fl_gamma`」。

### 3.3 加自检:训练后回读 args.yaml

```python
import yaml, glob, os
runs = glob.glob(os.path.join(a.project, a.name, 'args.yaml'))
if runs:
    cfg = yaml.safe_load(open(runs[-1], encoding='utf-8'))
    got = {k: cfg.get(k) for k in ('model', 'imgsz', 'epochs', 'seed', 'fl_gamma',
                                   'fliplr', 'mosaic', 'hsv_h', 'hsv_s', 'hsv_v')}
    print(f'[CHECK] 训练参数确认: {got}')
    # 断言 fl_gamma 生效
    assert abs(float(cfg.get('fl_gamma', 0.0)) - a.fl_gamma) < 1e-6, 'fl_gamma 未生效!'
else:
    print('[WARN] 未找到 args.yaml,参数生效性未自检')
```

这样任何「传了没生效」的参数问题会在训练结束时立刻暴露。

### 3.4 顺带:增强参数显式化(可选)

把 `fliplr/mosaic/hsv_*` 也提成 CLI 参数,默认值与 v4 一致。多轮训练对比时,**每个影响结果的旋钮都在命令行可见、可复现**——这是你后面「11s/8s、binary/multi」多轮对比的基础。

---

## 4. 验收标准

- [ ] `python train_cli.py --help` 不再出现 `cls_pw`,出现 `fl_gamma`;
- [ ] 任意传 `--fl_gamma 1.5` 跑 1 epoch 的 dry-run,args.yaml 里 `fl_gamma` 为 1.5,自检 print 通过;
- [ ] 传 `--cls_pw` 会直接报未知参数(而不是静默忽略);
- [ ] 多轮对比时(11s vs 8s、binary vs multi),除刻意变化项外其余参数在命令行显式一致。

---

## 5. 依赖与阻塞

| 项 | 状态 |
|---|---|
| 脚本修改 | 我代做,现在就能做 |
| 真机验证 | 训练机上有 ultralytics 即可跑 dry-run;无 GPU 也能用 `--device cpu` + `epochs 1` 验证参数自检逻辑 |
| 与 v5 训练的关系 | 你 v5 先做 LLM 图片清洗再训;本 CLI 清理先落地,保证 v5 多轮训练时参数口径干净 |
