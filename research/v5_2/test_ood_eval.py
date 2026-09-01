#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for ood_eval.py — pure CPU, no ultralytics import, no GPU.

Covers the contracts that make the one-shot OOD protocol trustworthy:
manifest schema, bucket edges, IoU matching, slice aggregation, the D7
one-shot lock, and the report schema. Run:
    venv\\Scripts\\python.exe -m pytest research/v5_2/test_ood_eval.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ood_eval as oe  # noqa: E402


# ---------------------------------------------------------------- manifest

def test_load_manifest_happy(tmp_path):
    m = tmp_path / "m.csv"
    m.write_text("image,split,scene_block_id,sha256\n"
                 "images/train/DJI_0014_0_0.jpg,id_val,DJI_0014,abc\n"
                 "images/train/DJI_0014_0_1.jpg,id_val,DJI_0014,def\n",
                 encoding="utf-8")
    rows = oe.load_manifest(str(m))
    assert len(rows) == 2
    assert rows[0]["scene_block_id"] == "DJI_0014"
    assert rows[1]["sha256"] == "def"


def test_load_manifest_missing_column(tmp_path):
    m = tmp_path / "m.csv"
    m.write_text("image,split,sha256\nimages/a.jpg,id_val,x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="scene_block_id"):
        oe.load_manifest(str(m))


def test_load_manifest_missing_file(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        oe.load_manifest(str(tmp_path / "nope.csv"))


def test_resolve_image_re_roots_basename():
    p = oe.resolve_image("/data/v5_2/ood_test", "images/train/DJI_0007_0_0.jpg")
    assert p.replace("\\", "/").endswith("ood_test/images/DJI_0007_0_0.jpg")


# ---------------------------------------------------------------- buckets

def test_short_side_edges():
    assert oe.short_side_bucket(30, 100) == "<=32"
    assert oe.short_side_bucket(32, 100) == "<=32"      # edge inclusive
    assert oe.short_side_bucket(33, 100) == "<=64"
    assert oe.short_side_bucket(128, 300) == "<=128"
    assert oe.short_side_bucket(129, 300) == ">128"


def test_aspect_edges():
    assert oe.aspect_bucket(50, 10) == "<=5"
    assert oe.aspect_bucket(55, 11) == "<=5"            # exactly 5.0, edge inclusive
    assert oe.aspect_bucket(50, 9) == "<=10"            # 5.56 → next bucket
    assert oe.aspect_bucket(60, 10) == "<=10"
    assert oe.aspect_bucket(210, 10) == ">20"
    assert oe.aspect_bucket(100, 100) == "<=5"          # square is 1.0


def test_bucket_label_stats_keys():
    short, aspect = oe.bucket_label_stats([(0, 0, 20, 200), (0, 0, 200, 200)])
    assert short["<=32"] == [0]
    assert short.get("<=128", []) == [1] or short.get(">128", []) == [1]
    assert "<=5" in aspect


# ---------------------------------------------------------------- iou / match

def test_iou_identical_and_disjoint():
    assert oe.iou_xyxy((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert oe.iou_xyxy((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    # half-overlap 10x10 boxes shifted by 5: IoU = 25/75
    assert abs(oe.iou_xyxy((0, 0, 10, 10), (5, 0, 15, 10)) - 25 / 75) < 1e-9


def test_match_perfect_detection():
    gt = [(0, 0, 10, 10), (20, 20, 30, 30)]
    dets = [{"box": (0, 0, 10, 10), "conf": 0.9},
            {"box": (20, 20, 30, 30), "conf": 0.8}]
    tp, fp, matched = oe.match_detections_detailed(gt, dets)
    assert (tp, fp) == (2, 0)
    assert matched == {0, 1}


def test_match_below_iou_threshold_is_fp_and_fn():
    gt = [(0, 0, 10, 10)]
    dets = [{"box": (0, 0, 10, 4), "conf": 0.9}]   # IoU = 40/100 = 0.4 < 0.5
    tp, fp, matched = oe.match_detections_detailed(gt, dets)
    assert (tp, fp) == (0, 1)
    assert matched == set()


def test_match_confidence_ordering_greedy():
    # one GT, two overlapping dets: only the higher-conf det wins
    gt = [(0, 0, 10, 10)]
    dets = [{"box": (0, 0, 10, 10), "conf": 0.6},
            {"box": (0, 0, 10, 10), "conf": 0.9}]
    tp, fp, _ = oe.match_detections_detailed(gt, dets)
    assert (tp, fp) == (1, 1)


def test_aggregate_math():
    assert oe.aggregate([(2, 1, 1)]) == {"tp": 2, "fp": 1, "fn": 1,
                                         "precision": 0.6667, "recall": 0.6667,
                                         "f1": 0.6667}
    # zero-division safety: no predictions, no GT
    assert oe.aggregate([])["precision"] == 0.0


# ---------------------------------------------------------------- guard (D7)

def test_ood_lock_refuses_second_run(tmp_path):
    oe.write_ood_lock(str(tmp_path), "baseline", "model.pt", "report.json",
                      {"mAP50": 0.42})
    with pytest.raises(RuntimeError, match="D7 violation"):
        oe.check_ood_lock(str(tmp_path), "baseline")


def test_ood_lock_slots_are_independent(tmp_path):
    oe.write_ood_lock(str(tmp_path), "baseline", "model.pt", "r1.json", {})
    # final slot untouched by a baseline run — both slots get their own shot
    oe.check_ood_lock(str(tmp_path), "final")            # no raise
    with pytest.raises(RuntimeError, match="slot 'baseline'"):
        oe.check_ood_lock(str(tmp_path), "baseline")


def test_ood_lock_payload_fields(tmp_path):
    lp = oe.write_ood_lock(str(tmp_path), "final", __file__, "report.json", {})
    with open(lp, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert set(payload) >= {"slot", "finished_utc", "model_path",
                            "model_sha256", "report", "headline"}
    assert payload["slot"] == "final"
    assert payload["model_sha256"]


def test_id_val_has_no_lock_ever(tmp_path):
    # id_val evaluation flow must not create the lock (only main() writes it,
    # and only for ood_test) — the guard itself must stay silent here.
    assert not os.path.isfile(oe.lock_path_for(str(tmp_path), "baseline"))
    oe.check_ood_lock(str(tmp_path), "baseline")  # no raise


# ---------------------------------------------------------------- report

def _synthetic_inputs(tmp_path, monkeypatch):
    """Two scene blocks: DJI_A with a TP-able GT, DJI_B with a tiny GT."""
    rows = [{"image": "images/a.jpg", "scene_block_id": "DJI_A", "sha256": ""},
            {"image": "images/b.jpg", "scene_block_id": "DJI_B", "sha256": ""}]
    split_dir = str(tmp_path)
    os.makedirs(os.path.join(split_dir, "images"), exist_ok=True)

    # 200x200 white png via raw bytes (PIL-free: minimal valid PNG)
    import struct, zlib
    def png(path, w=200, h=200):
        def chunk(tag, data):
            c = tag + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I",
                                              zlib.crc32(c) & 0xFFFFFFFF)
        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
        with open(path, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

    pa = os.path.join(split_dir, "images", "a.jpg")
    pb = os.path.join(split_dir, "images", "b.jpg")
    png(pa)
    png(pb)

    # GT: a = 60x60 box (short side 60 → "<=64"); b = 20x20 box (→ "<=32")
    det = oe._predict_boxes  # keep a reference for restore
    def fake_predict(model, image_paths, conf, imgsz):
        out = {}
        for p in image_paths:
            if p.endswith("a.jpg"):
                out[p] = [{"box": (10.0, 10.0, 70.0, 70.0), "conf": 0.8}]
            else:
                out[p] = []          # tiny GT missed → FN
        return out
    monkeypatch.setattr(oe, "_predict_boxes", fake_predict)

    gt_by_image = {
        pa: ([(10, 10, 70, 70)], [(40.0, 40.0, 60.0, 60.0)]),
        pb: ([(90, 90, 110, 110)], [(100.0, 100.0, 20.0, 20.0)]),
    }
    return rows, split_dir, gt_by_image, det


def test_build_report_slices_and_verdict(tmp_path, monkeypatch):
    rows, split_dir, gt_by_image, _ = _synthetic_inputs(tmp_path, monkeypatch)
    paths = [oe.resolve_image(split_dir, r["image"]) for r in rows]
    det_by_image = oe._predict_boxes(None, paths, oe.DIAG_CONF, 1024)
    report = oe.build_report(rows, split_dir, "nonexistent_model.pt",
                             det_by_image, gt_by_image,
                             {"mAP50": 0.5}, limit=None)
    assert report["scene_slices"]["DJI_A"]["tp"] == 1
    assert report["scene_slices"]["DJI_A"]["recall"] == 1.0
    assert report["scene_slices"]["DJI_B"]["fn"] == 1
    assert report["scene_slices"]["DJI_B"]["recall"] == 0.0
    # bucket edges line up with the synthetic GT geometry
    assert report["short_side_recall"]["<=64"]["tp"] == 1
    assert report["short_side_recall"]["<=32"]["fn"] == 1
    assert report["verdict_hints"]["ood_recall_not_near_zero"] is True
    assert report["verdict_hints"]["scene_spread_detected"] is True
    assert report["meta"]["model_sha256"] is None      # model file not present


def test_build_report_citability_flag(tmp_path, monkeypatch):
    rows, split_dir, gt_by_image, _ = _synthetic_inputs(tmp_path, monkeypatch)
    paths = [oe.resolve_image(split_dir, r["image"]) for r in rows]
    det_by_image = oe._predict_boxes(None, paths, oe.DIAG_CONF, 1024)
    r1 = oe.build_report(rows, split_dir, "no.pt", det_by_image, gt_by_image,
                         {}, limit=2)
    assert r1["meta"]["numbers_are_citable"] is False      # limited run
    r2 = oe.build_report(rows, split_dir, "no.pt", det_by_image, gt_by_image,
                         {}, limit=None)
    assert r2["meta"]["numbers_are_citable"] is True       # full id_val run
    # and an ood_test full run is NEVER auto-citable without the lock flow
    od = os.path.join(str(tmp_path), "ood_test")
    os.makedirs(od, exist_ok=True)
    od_paths = [oe.resolve_image(od, r["image"]) for r in rows]
    det_od = dict(zip(od_paths, (det_by_image[p] for p in paths)))
    gt_od = dict(zip(od_paths, (gt_by_image[p] for p in paths)))
    r3 = oe.build_report(rows, od, "no.pt", det_od, gt_od, {}, limit=None)
    assert r3["meta"]["numbers_are_citable"] is False
