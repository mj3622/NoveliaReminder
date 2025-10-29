from pathlib import Path
from typing import Any

import yaml


class YamlReader:
    """简洁的 YAML 配置文件读取工具"""

    def __init__(self, config_path: str):
        """
        初始化 YAML 读取器并加载配置文件

        Args:
            config_path: 配置文件的相对路径（相对于根路径）
        """
        self.config_path = Path(config_path)
        self._config_data = {}

        # 自动尝试添加扩展名
        file_path = self.config_path
        if not file_path.exists():
            for ext in ['.yaml', '.yml']:
                test_path = self.config_path.with_suffix(ext)
                if test_path.exists():
                    file_path = test_path
                    break

        if not file_path.exists():
            print(f"配置文件不存在: {file_path}")
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                self._config_data = yaml.safe_load(file) or {}
            print(f"配置文件加载成功: {file_path}")
        except Exception as e:
            print(f"配置文件加载失败: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        根据键获取配置值

        Args:
            key: 配置键，支持点分隔的嵌套键（如 'database.host'）
            default: 键不存在时返回的默认值

        Returns:
            Any: 配置值
        """
        if not self._config_data:
            return default

        # 支持点分隔的嵌套键访问
        keys = key.split('.')
        current_data = self._config_data

        for k in keys:
            if isinstance(current_data, dict) and k in current_data:
                current_data = current_data[k]
            else:
                return default

        return current_data

    def get_all(self) -> dict:
        """
        获取所有配置数据

        Returns:
            dict: 所有配置的字典
        """
        return self._config_data.copy()

