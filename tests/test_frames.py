#!/usr/bin/env python3
"""Coordinate frame conversion roundtrip tests - Phase 2 deliverable."""

import sys, numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from backend.utils.units import (
    zup_cm_to_yup_m, yup_m_to_zup_cm,
    zup_m_to_yup_m, yup_m_to_zup_m,
    m_to_cm, cm_to_m, mm_to_cm, cm_to_mm,
)


class TestCoordinateRoundtrip:
    def test_zup_cm_to_yup_m_and_back(self):
        """Backend(cm,z-up) to Web(m,y-up) and back must be identity."""
        original = np.array([150.0, -80.0, 200.0])
        web = zup_cm_to_yup_m(original)
        restored = yup_m_to_zup_cm(web)
        assert np.allclose(original, restored, atol=1e-6)

    def test_zup_m_to_yup_m_and_back(self):
        """Sim(m,z-up) to Web(m,y-up) and back must be identity."""
        original = np.array([1.5, -0.8, 2.0])
        web = zup_m_to_yup_m(original)
        restored = yup_m_to_zup_m(web)
        assert np.allclose(original, restored, atol=1e-6)

    def test_height_axis_mapping(self):
        """Height axis: z-up Z must map to y-up Y."""
        zup = np.array([1.0, 2.0, 5.0])
        yup = zup_m_to_yup_m(zup)
        expected = np.array([1.0, 5.0, -2.0])
        assert np.allclose(yup, expected, atol=1e-6)

    def test_ground_is_zero(self):
        """Ground height must be 0 in both coordinate systems."""
        ground = np.array([10.0, 5.0, 0.0])
        yup = zup_m_to_yup_m(ground)
        assert yup[1] == 0.0

    def test_origin_invariant(self):
        """Origin must be the same in both coordinate systems."""
        origin = np.array([0.0, 0.0, 0.0])
        assert np.allclose(zup_m_to_yup_m(origin), origin)
        assert np.allclose(zup_cm_to_yup_m(origin * 100), origin)


class TestUnitConversion:
    def test_m_to_cm_and_back(self):
        for val in [1.5, 0.0, 100.0, 0.01]:
            assert abs(cm_to_m(m_to_cm(val)) - val) < 1e-9

    def test_cm_to_mm_and_back(self):
        for val in [55.0, 45.0, 35.0]:
            assert abs(mm_to_cm(cm_to_mm(val)) - val) < 1e-9

    def test_array_conversion(self):
        arr = np.array([1.0, 2.0, 3.0])
        assert np.allclose(cm_to_m(m_to_cm(arr)), arr)


if __name__ == "__main__":
    print("=" * 50)
    print("  Coordinate frame roundtrip tests")
    print("=" * 50)
    t = TestCoordinateRoundtrip()
    t.test_zup_cm_to_yup_m_and_back()
    t.test_zup_m_to_yup_m_and_back()
    t.test_height_axis_mapping()
    t.test_ground_is_zero()
    t.test_origin_invariant()
    u = TestUnitConversion()
    u.test_m_to_cm_and_back()
    u.test_cm_to_mm_and_back()
    u.test_array_conversion()
    print("\n[OK] All coordinate frame tests passed!")