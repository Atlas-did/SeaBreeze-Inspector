"""
统一配置加载器 — 支持YAML配置解析、环境变量覆盖、类型校验。

技术选型说明：本项目使用YAML作为配置格式，原因如下：
1. 支持注释 — 大学生团队需要配置文件中写说明和调试笔记
2. 层次清晰 — 缩进天然分层，适合复杂嵌套配置
3. 人类可读 — 编辑时不需要处理引号和逗号
4. 生态成熟 — PyYAML库稳定可靠，Python社区广泛使用

⚠️ 重要提醒：编辑YAML文件时缩进必须用空格，绝对不能用Tab！
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Union

try:
    import yaml
except ImportError as e:
    raise ImportError(
        "缺少PyYAML依赖。请运行: pip install pyyaml\n"
        "本项目使用YAML作为配置格式，必须安装此库。"
    ) from e

# 项目根目录：从本文件所在位置向上回溯3层
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

DEFAULT_CONFIG_DIRS: List[Path] = [
    PROJECT_ROOT / "config",
    Path("/etc/offshore-wind-uav/"),
    Path.home() / ".config/offshore-wind-uav",
]


class ConfigError(Exception):
    """配置相关错误的基类"""
    pass


class ConfigKeyError(ConfigError):
    """配置键缺失或访问错误"""
    pass


class ConfigTypeError(ConfigError):
    """配置值类型不匹配"""
    pass


class Config:
    """
    统一的配置对象，支持字典式访问和属性式访问。

    用法示例:
        cfg = ConfigLoader.load("drone_config")
        speed = cfg.flight.default_speed
        speed = cfg["flight"]["default_speed"]
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        for key, value in data.items():
            if isinstance(value, dict):
                setattr(self, key, Config(value))
            else:
                setattr(self, key, value)
        self._raw = data

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        raise ConfigKeyError(
            f"配置键不存在: '{key}'。可用的键: {list(self._raw.keys())}"
        )

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def to_dict(self) -> Dict[str, Any]:
        return self._raw

    def __repr__(self) -> str:
        return f"Config({list(self._raw.keys())})"


class ConfigLoader:
    """
    配置加载器：负责查找、加载、合并配置文件，并支持环境变量覆盖。
    """

    _cache: Dict[str, Config] = {}
    ENV_PREFIX: str = "UAVARM"
    ENV_NESTED_SEP: str = "__"

    # -----------------------------------------------------------------
    # 配置schema定义 (P0-8: 类型校验)
    # 格式: {config_name: {field_path: (expected_type, is_required, default_value)}}
    # -----------------------------------------------------------------
    _SCHEMAS: Dict[str, Dict[str, tuple]] = {
        "drone_config": {
            "connection.wifi_prefix": (str, True, "Tello"),
            "connection.connect_timeout": ((int, float), True, 10),
            "flight.default_speed": ((int, float), True, 20),
            "flight.max_speed": ((int, float), True, 50),
            "flight.default_hover_height": ((int, float), True, 100),
            "flight.max_height": ((int, float), True, 300),
            "flight.hover_stabilize_time": ((int, float), True, 2.0),
            "flight.control_rate_hz": ((int, float), False, 10.0),
            "flight.waypoint_reach_radius": ((int, float), False, 30),
            "flight.takeoff_done_margin": ((int, float), False, 10),
            "safety.battery_warn": ((int, float), False, 30),
            "safety.low_battery_land_threshold": ((int, float), True, 20),
            "safety.battery_kill": ((int, float), False, 10),
            "safety.attitude_max_deg": ((int, float), False, 30),
            "safety.link_timeout_s": ((int, float), False, 2.0),
            "safety.boundary.z_max": ((int, float), False, 300),
            "safety.safe_point.x": ((int, float), False, 0),
            "safety.safe_point.y": ((int, float), False, 0),
            "safety.safe_point.z": ((int, float), False, 100),
            "mission.inspect_timeout_s": ((int, float), False, 30),
            "safety.near_wall_min_distance": ((int, float), True, 100),
            "imu_noise.accel_noise_std": ((int, float), True, 0.05),
            "imu_noise.optical_flow_noise_std": ((int, float), True, 2.0),
            "imu_noise.barometer_noise_std": ((int, float), True, 10.0),
            "mode.debug": (bool, False, False),
        },
        "arm_config": {
            "hardware.serial.baudrate": (int, True, 115200),
            "kinematics.link_lengths.l1": ((int, float), True, 55),
            "kinematics.link_lengths.l2": ((int, float), True, 45),
            "kinematics.link_lengths.l3": ((int, float), True, 35),
            "servo.max_speed_dps": ((int, float), False, 60),
        },
        "yolo_config": {
            "model.input_size": (int, True, 640),
            "model.device": (str, True, "cpu"),
            "inference.conf_threshold": ((int, float), True, 0.45),
            "inference.iou_threshold": ((int, float), True, 0.5),
            "inference.max_detections": (int, True, 50),
            "training.epochs": (int, False, 200),
            "training.batch_size": (int, False, 8),
            "training.learning_rate": ((int, float), False, 0.001),
        },
    }

    @classmethod
    def load(
        cls,
        name: str,
        config_dir: Union[str, Path, None] = None,
        use_cache: bool = True,
        apply_env_override: bool = True,
    ) -> Config:
        cache_key = f"{config_dir or 'default'}:{name}"
        if use_cache and cache_key in cls._cache:
            return cls._cache[cache_key]

        config_path = cls._find_config_file(name, config_dir)
        raw_data = cls._parse_yaml(config_path)

        if apply_env_override:
            raw_data = cls._apply_env_overrides(name, raw_data)

        cls._validate_types(raw_data, config_path)

        config = Config(raw_data)
        if use_cache:
            cls._cache[cache_key] = config

        return config

    @classmethod
    def _find_config_file(
        cls, name: str, config_dir: Union[str, Path, None] = None
    ) -> Path:
        filename = f"{name}.yaml"
        search_dirs = []
        if config_dir is not None:
            search_dirs.append(Path(config_dir))
        search_dirs.extend(DEFAULT_CONFIG_DIRS)

        for directory in search_dirs:
            candidate = directory / filename
            if candidate.exists():
                return candidate

        searched = "\n  - ".join(str(d / filename) for d in search_dirs)
        raise ConfigError(
            f"找不到配置文件: '{filename}'\n"
            f"已搜索路径:\n  - {searched}\n"
            f"请确认配置文件存在，或用 config_dir 参数指定路径。"
        )

    @classmethod
    def _parse_yaml(cls, path: Path) -> Dict[str, Any]:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            raise ConfigError(f"无法读取配置文件: {path}") from e

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            error_msg = str(e)
            if "found character" in error_msg and "\\t" in error_msg:
                raise ConfigError(
                    f"YAML解析失败（{path.name}）: 检测到Tab缩进！\n"
                    f"YAML格式要求用空格缩进，绝对不能用Tab键。\n"
                    f"请将编辑器设置为：Tab自动转空格，缩进宽度2格。\n"
                    f"原始错误: {error_msg}"
                ) from e
            raise ConfigError(
                f"YAML解析失败（{path.name}）:\n{error_msg}\n"
                f"请检查文件格式是否正确。"
            ) from e

        if not isinstance(data, dict):
            raise ConfigError(
                f"配置文件根节点必须是字典，但解析结果是: {type(data).__name__}"
            )
        return data

    @classmethod
    def _apply_env_overrides(
        cls, name: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        config_prefix = f"{cls.ENV_PREFIX}_{name.upper()}__"

        for env_key, env_value in os.environ.items():
            if not env_key.startswith(config_prefix):
                continue

            path_str = env_key[len(config_prefix):]
            path_parts = [p.lower() for p in path_str.split(cls.ENV_NESTED_SEP)]
            cls._set_nested_value(data, path_parts, env_value, env_key)

        return data

    @classmethod
    def _set_nested_value(
        cls,
        data: Dict[str, Any],
        path_parts: List[str],
        value: str,
        env_key: str,
    ) -> None:
        current = data
        for part in path_parts[:-1]:
            if part not in current:
                raise ConfigKeyError(
                    f"环境变量覆盖失败: '{env_key}'\n"
                    f"中间键 '{part}' 在配置中不存在。"
                )
            if not isinstance(current[part], dict):
                raise ConfigKeyError(
                    f"环境变量覆盖失败: '{env_key}'\n"
                    f"'{part}' 不是字典，无法继续嵌套。"
                )
            current = current[part]

        leaf_key = path_parts[-1]
        if leaf_key not in current:
            raise ConfigKeyError(
                f"环境变量覆盖失败: '{env_key}'\n"
                f"叶子键 '{leaf_key}' 在配置中不存在。"
            )

        original = current[leaf_key]
        converted = cls._convert_type(value, original, env_key)
        current[leaf_key] = converted

    @classmethod
    def _convert_type(cls, value: str, original: Any, env_key: str) -> Any:
        if isinstance(original, bool):
            if value.lower() in ("true", "1", "yes", "on"):
                return True
            elif value.lower() in ("false", "0", "no", "off"):
                return False
            raise ConfigTypeError(
                f"环境变量 '{env_key}' 布尔值解析失败: '{value}'"
            )
        elif isinstance(original, int):
            try:
                return int(value)
            except ValueError:
                raise ConfigTypeError(
                    f"环境变量 '{env_key}' 应为整数，但得到: '{value}'"
                )
        elif isinstance(original, float):
            try:
                return float(value)
            except ValueError:
                raise ConfigTypeError(
                    f"环境变量 '{env_key}' 应为浮点数，但得到: '{value}'"
                )
        elif isinstance(original, list):
            raise ConfigTypeError(
                f"环境变量 '{env_key}' 目标为列表，暂不支持从环境变量覆盖列表。"
            )
        else:
            return value

    # =========================================================================
    # 类型校验 (P0-8: 实现配置类型校验)
    # =========================================================================

    @staticmethod
    def _get_nested(data: Dict[str, Any], path: str) -> Any:
        """从嵌套字典中获取指定路径的值 (e.g. "flight.max_speed" → data["flight"]["max_speed"])"""
        keys = path.split(".")
        current = data
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        return current

    @classmethod
    def _validate_types(cls, data: Dict[str, Any], path: Path) -> None:
        """根据schema校验配置字段类型

        检查项:
        1. 必填字段存在性
        2. 字段值类型是否正确
        3. 数值字段范围合理性 (非负验证)
        """
        config_name = path.stem  # e.g. drone_config.yaml → drone_config
        schema = cls._SCHEMAS.get(config_name, {})

        if not schema:
            return  # 无schema定义, 跳过校验

        for field_path, (expected_type, required, _default) in schema.items():
            value = cls._get_nested(data, field_path)

            # 必填检查
            if value is None and required:
                raise ConfigKeyError(
                    "配置校验失败 ({}) — 必填字段 '{}' 缺失".format(
                        path.name, field_path
                    )
                )

            if value is None:
                continue  # 可选字段缺失, 跳过

            # 类型检查 (支持多类型, 如 (int, float))
            types = (
                expected_type
                if isinstance(expected_type, tuple)
                else (expected_type,)
            )
            if not isinstance(value, types):
                type_names = " | ".join(t.__name__ for t in types)
                raise ConfigTypeError(
                    "配置校验失败 ({}) — 字段 '{}' 类型错误: 期望 {}, 实际 {}".format(
                        path.name, field_path, type_names,
                        type(value).__name__,
                    )
                )

            # 数值范围检查: 非负数
            if isinstance(value, (int, float)) and value < 0:
                raise ConfigTypeError(
                    "配置校验失败 ({}) — 字段 '{}' 值异常: {} < 0".format(
                        path.name, field_path, value
                    )
                )

    @classmethod
    def clear_cache(cls) -> None:
        """清除配置缓存，用于开发时热重载"""
        cls._cache.clear()

    @classmethod
    def reload(cls, name: str, **kwargs: Any) -> Config:
        """强制重新加载配置（忽略缓存）"""
        return cls.load(name, use_cache=False, **kwargs)
