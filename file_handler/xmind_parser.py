"""
XMind格式测试点解析器 - 叶子节点版
只统计叶子节点作为测试点数量，确保分批处理时测试用例数量与测试点数量一致
"""
import time
import zipfile
import json
import xml.etree.ElementTree as ET
import re
from pathlib import Path
from typing import List, Dict


class XMindParser:
    """XMind测试点解析类 - 最终修复版"""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.content = None
        self.file_type = None
        self.ns_uri = ""  # 存储命名空间URI

    def load(self):
        """加载XMind文件"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {self.file_path}")

        with zipfile.ZipFile(self.file_path, 'r') as zf:
            namelist = zf.namelist()

            if 'content.json' in namelist:
                self.file_type = 'json'
                with zf.open('content.json') as f:
                    self.content = json.loads(f.read().decode('utf-8'))
            elif 'content.xml' in namelist:
                self.file_type = 'xml'
                with zf.open('content.xml') as f:
                    self.content = f.read().decode('utf-8')
            else:
                raise ValueError(f"无法识别的XMind文件格式: {namelist}")

        return self

    def parse(self) -> List[Dict]:
        """解析测试点为结构化数据"""
        if self.content is None:
            self.load()

        if self.file_type == 'json':
            points = self._parse_json()
        else:
            points = self._parse_xml()

        print(f"[调试] XMind解析完成，共 {len(points)} 个测试点（仅叶子节点）")
        print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

        # 打印所有解析出的测试点
        print("\n" + "=" * 60)
        print("【XMind解析】测试点详情（仅叶子节点）")
        print("=" * 60)
        for i, point in enumerate(points, 1):
            indent = "  " * point['level']
            module_info = f"[{point['module']}] " if point['module'] else ""
            full_path = " → ".join(point.get('full_path', []))
            print(f"{i}. {module_info}{full_path}")
        print("=" * 60 + "\n")

        return points

    def _parse_json(self) -> List[Dict]:
        """解析XMind Zen/2026 (JSON格式)"""
        test_points = []

        if isinstance(self.content, list) and len(self.content) > 0:
            root_sheet = self.content[0]
        elif isinstance(self.content, dict):
            root_sheet = self.content
        else:
            return test_points

        root_topic = root_sheet.get('rootTopic', {})
        if not root_topic:
            return test_points

        self._traverse_json_topic(root_topic, test_points, level=0)
        return test_points

    def _traverse_json_topic(self, topic: Dict, points: List[Dict], level: int, parent_module: str = "", parent_path: List[str] = None):
        """递归遍历JSON格式的topic - 只收集叶子节点作为测试点"""
        if not topic:
            return

        if parent_path is None:
            parent_path = []

        title = topic.get('title', '')
        if not title:
            return

        # 获取子节点
        children = topic.get('children', {}).get('attached', []) if topic.get('children') else []
        is_leaf = len(children) == 0

        # 构建当前路径（用于叶子节点的完整层级信息）
        current_path = parent_path + [title]

        if level == 0:
            # 根节点作为模块名
            module = title
        else:
            module = parent_module

        # 只有叶子节点才添加到测试点列表
        if is_leaf and level >= 1:
            points.append({
                'module': module,
                'feature': parent_path[-1] if len(parent_path) >= 1 else "",
                'content': title,
                'level': level,
                'is_leaf': True,
                'full_path': current_path  # 完整路径，方便后续使用
            })

        # 递归子主题
        for child in children:
            self._traverse_json_topic(child, points, level + 1, module, current_path)

    def _parse_xml(self) -> List[Dict]:
        """解析XMind 8/Legacy (XML格式) - 最终修复版"""
        test_points = []

        root = ET.fromstring(self.content)

        # 提取命名空间URI
        self.ns_uri = self._extract_namespace(root.tag)
        print(f"[调试] 检测到命名空间: {self.ns_uri}")

        # 找到sheet
        sheet = self._find_element(root, 'sheet')
        if sheet is None:
            sheet = root

        # 找到root topic（直接子元素）
        root_topic = None
        for child in sheet:
            if self._local_tag(child.tag) == 'topic':
                root_topic = child
                break

        if root_topic is None:
            print("[调试] 错误: 未找到root topic")
            return test_points

        title = self._get_text(root_topic, 'title')
        print(f"[调试] Root Topic标题: {title}")

        # 开始遍历
        self._traverse_xml_topic(root_topic, test_points, level=0)

        return test_points

    def _extract_namespace(self, tag: str) -> str:
        """从标签提取命名空间URI"""
        match = re.match(r'\{([^}]+)\}', tag)
        return match.group(1) if match else ""

    def _local_tag(self, tag: str) -> str:
        """获取标签名（去掉命名空间）"""
        return tag.split('}')[-1] if '}' in tag else tag

    def _find_element(self, parent, tag: str):
        """查找元素（支持命名空间）"""
        # 先尝试直接查找
        for child in parent:
            if self._local_tag(child.tag) == tag:
                return child

        # 使用命名空间查找
        if self.ns_uri:
            elem = parent.find(f'{{{self.ns_uri}}}{tag}')
            if elem is not None:
                return elem

        return None

    def _get_text(self, element, tag: str) -> str:
        """获取子元素的文本"""
        for child in element:
            if self._local_tag(child.tag) == tag:
                return child.text or ""

        # 使用命名空间查找
        if self.ns_uri:
            child = element.find(f'{{{self.ns_uri}}}{tag}')
            if child is not None:
                return child.text or ""

        return ""

    def _get_children_topics(self, topic) -> list:
        """
        获取直接的子topic元素 - 关键修复
        XMind结构: <topic><children><topics><topic>...</topic></topics></children></topic>
        """
        children = []

        for child in topic:
            local_tag = self._local_tag(child.tag)

            if local_tag == 'topic':
                # 直接子topic
                children.append(child)
            elif local_tag == 'children':
                # 在children中查找topics
                for subchild in child:
                    if self._local_tag(subchild.tag) == 'topics':
                        # 在topics中查找所有topic
                        for topic_elem in subchild:
                            if self._local_tag(topic_elem.tag) == 'topic':
                                children.append(topic_elem)

        return children

    def _traverse_xml_topic(self, topic, points: List[Dict], level: int, parent_module: str = "", parent_path: List[str] = None):
        """递归遍历XML格式的topic - 只收集叶子节点作为测试点"""
        if topic is None:
            return

        if parent_path is None:
            parent_path = []

        title = self._get_text(topic, 'title')
        if not title:
            return

        # 获取直接子topic（关键：不使用递归查找）
        children = self._get_children_topics(topic)
        is_leaf = len(children) == 0

        # 构建当前路径（用于叶子节点的完整层级信息）
        current_path = parent_path + [title]

        if level == 0:
            # 根节点作为模块名
            module = title
        else:
            module = parent_module

        # 只有叶子节点才添加到测试点列表
        if is_leaf and level >= 1:
            points.append({
                'module': module,
                'feature': parent_path[-1] if len(parent_path) >= 1 else "",
                'content': title,
                'level': level,
                'is_leaf': True,
                'full_path': current_path  # 完整路径，方便后续使用
            })

        # 递归处理直接子节点
        for child in children:
            self._traverse_xml_topic(child, points, level + 1, module, current_path)

    def to_text(self) -> str:
        """转换为纯文本格式"""
        points = self.parse()

        if not points:
            return "未解析到任何测试点"

        sections = []
        current_module = ""

        for point in points:
            if point['module'] != current_module:
                current_module = point['module']
                sections.append(f"\n【{current_module}】")

            full_path = point.get('full_path', [point['content']])
            sections.append(f"  - {' → '.join(full_path)}")

        return "\n".join(sections)