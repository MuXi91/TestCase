"""
配置管理模块
支持从代码、环境变量、~/.zshrc读取配置
"""

import os
import re
from pathlib import Path


class Config:
    """配置管理类"""

    # 默认配置
    DEFAULT_MODEL = "Qwen/Qwen2.5-72B-Instruct"
    DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"

    def __init__(self):
        self.api_key = self._get_api_key()
        self.model = os.getenv("SILICONFLOW_MODEL", self.DEFAULT_MODEL)
        self.base_url = os.getenv("SILICONFLOW_BASE_URL", self.DEFAULT_BASE_URL)

    def _get_api_key(self):
        """获取API Key，优先级：代码 > 环境变量 > ~/.zshrc"""
        # 1. 尝试从代码直接读取（这里预留，实际可在代码中硬编码）
        code_key = getattr(Config, 'HARDCODED_API_KEY', None)
        if code_key:
            return code_key

        # 2. 尝试从环境变量读取
        env_key = os.getenv("SILICONFLOW_API_KEY")
        if env_key:
            return env_key

        # 3. 从 ~/.zshrc 读取变量名 aaaa 的值
        zshrc_key = self._read_from_zshrc("SILICONFLOW_KEY")
        if zshrc_key:
            return zshrc_key

        raise ValueError("未找到API Key，请设置 SILICONFLOW_API_KEY 环境变量或在~/.zshrc中定义 SILICONFLOW_KEY 变量")

    def _read_from_zshrc(self, var_name):
        """从~/.zshrc读取指定变量值"""
        zshrc_path = Path.home() / ".zshrc"
        if not zshrc_path.exists():
            return None

        try:
            content = zshrc_path.read_text(encoding='utf-8')
            # 匹配 export aaaa="xxx" 或 export aaaa='xxx' 或 aaaa=xxx
            patterns = [
                rf'export\s+{var_name}\s*=\s*["\']([^"\']+)["\']',
                rf'export\s+{var_name}\s*=\s*([^\s]+)',
                rf'{var_name}\s*=\s*["\']([^"\']+)["\']',
                rf'{var_name}\s*=\s*([^\s]+)'
            ]
            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return None


# 全局配置实例
config = Config()