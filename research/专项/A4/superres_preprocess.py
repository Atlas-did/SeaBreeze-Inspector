#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A4-03 超分预处理(需 GPU + Real-ESRGAN 权重;排在 SAHI/高分辨率重训之后)
两条路径: 推理时超分(I→SR→detect) / 训练时超分(低清 patch 超分入训练集,需审计)。
重点: 超分不增加真实信息,有伪纹理风险;端到端时延必须实测。
"""
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='RealESRGAN_x4plus.pth',
                    help='Real-ESRGAN 权重(从 xinntao/Real-ESRGAN 下载)')
    ap.add_argument('--image', required=True)
    ap.add_argument('--scale', type=int, default=2, choices=[2, 4])
    a = ap.parse_args()
    print('[A4-03] 超分预处理接口(需 GPU + Real-ESRGAN 权重下载)')
    print(f'  权重={a.model}, scale={a.scale}x, 输入={a.image}')
    print('  链路: I → SR(×scale) → detect')
    print('  诚实纪律:')
    print('   1) 超分不增加真实信息,AP 提升≈分辨率提升,直接重训高分辨率更划算;')
    print('   2) 伪纹理可能被当缺陷(Precision 崩)/细纹被抹平(FN 升),须伪影审计;')
    print('   3) 4× 在 1280 图上端到端数百 ms~数 s(CPU),P95 必须实测;')
    print('   4) 排在 SAHI(切片)与高分辨率重训之后,是兜底方案。')


if __name__ == '__main__':
    main()
