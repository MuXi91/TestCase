"""
测试点转测试用例 - GUI主程序
"""

import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QFileDialog,
    QComboBox, QMessageBox, QProgressBar, QGroupBox, QSpinBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from ai_engine.siliconflow_client import SiliconFlowClient
from ai_engine.claude_cli_client import ClaudeCLIClient
# 导入项目模块
from config import config
from generator import TestcaseGenerator
from exporter import ExcelExporter


class ConnectionTestThread(QThread):
    """连接测试线程"""
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, client):
        super().__init__()
        self.client = client

    def run(self):
        success, message = self.client.test_connection()
        self.finished.emit(success, message)


class GeneratorThread(QThread):
    """后台生成线程"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, generator, test_point_file, file_type, batch_size=5):
        super().__init__()
        self.generator = generator
        self.test_point_file = test_point_file
        self.file_type = file_type
        self.batch_size = batch_size
        # 用于收集进度消息
        self._progress_messages = []

    def _collect_progress(self, message: str):
        """收集进度消息（线程安全，由 ClaudeCLIClient 调用）"""
        self._progress_messages.append(message)
        # 通过 signal 发送到主线程更新 UI
        self.progress.emit(message)

    def run(self):
        import traceback
        try:
            self.progress.emit("正在解析测试点...")

            # 设置进度回调
            if hasattr(self.generator, 'ai_client'):
                self.generator.ai_client.progress_callback = self._collect_progress

            if self.file_type == 'markdown':
                testcases = self.generator.generate_from_markdown(self.test_point_file, batch_size=self.batch_size)
            else:
                testcases = self.generator.generate_from_xmind(self.test_point_file, batch_size=self.batch_size)

            self.progress.emit(f"生成完成，共 {len(testcases)} 条用例")
            self.finished.emit(testcases)

        except Exception as e:
            error_detail = f"{str(e)}\n\n堆栈信息:\n{traceback.format_exc()[:1000]}"
            self.progress.emit(f"❌ 发生错误: {str(e)}")
            self.error.emit(error_detail)


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("测试点转测试用例 AI工具")
        self.setMinimumSize(800, 600)

        self.generator = None
        self.current_testcases = []

        self.init_ui()
        self.init_ai_client()

    def init_ui(self):
        """初始化UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # ===== 配置区域 =====
        config_group = QGroupBox("AI配置")
        config_layout = QVBoxLayout()

        # 后端选择
        backend_layout = QHBoxLayout()
        backend_layout.addWidget(QLabel("后端:"))
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["SiliconFlow", "Claude CLI"])
        self.backend_combo.currentTextChanged.connect(self.on_backend_changed)
        backend_layout.addWidget(self.backend_combo)
        backend_layout.addStretch()
        config_layout.addLayout(backend_layout)

        # Claude CLI 模型选择 - 仅Claude CLI时显示
        claude_model_layout = QHBoxLayout()
        self.claude_model_label = QLabel("CLI模型:")
        claude_model_layout.addWidget(self.claude_model_label)
        self.claude_model_combo = QComboBox()
        self.claude_model_combo.addItems(["glm-5", "kimi-k2.5", "claude-sonnet-4-6", "claude-opus-4-6"])
        claude_model_layout.addWidget(self.claude_model_combo)
        claude_model_layout.addStretch()
        config_layout.addLayout(claude_model_layout)

        # API Key显示（脱敏）- 仅SiliconFlow时显示
        api_layout = QHBoxLayout()
        self.api_key_label_title = QLabel("API Key:")
        api_layout.addWidget(self.api_key_label_title)
        self.api_key_label = QLabel("从环境变量或~/.zshrc加载中...")
        self.api_key_label.setStyleSheet("color: green;")
        api_layout.addWidget(self.api_key_label)
        api_layout.addStretch()
        config_layout.addLayout(api_layout)

        # 模型选择 - 仅SiliconFlow时显示
        model_layout = QHBoxLayout()
        self.model_label = QLabel("模型:")
        model_layout.addWidget(self.model_label)
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
            "Qwen/Qwen2.5-72B-Instruct",
            "Qwen/Qwen2.5-32B-Instruct"
        ])
        model_layout.addWidget(self.model_combo)
        model_layout.addStretch()
        config_layout.addLayout(model_layout)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # 类型选择
        # mode_select = QHBoxLayout()
        # mode_select.addWidget(QLabel('类型:'))
        # self.mode_select = QComboBox()
        # self.mode_select.addItems([
        #     "活动",
        #     "个人中心",
        #     "battle",
        #     "treasure",
        #     "乐透",
        #     "bingo",
        #     "升级",
        #     "盒柜",
        #     "开盒",
        #     "充值送",
        #     "充值"
        # ])
        # mode_select.addWidget(self.mode_select)
        # mode_select.addStretch()
        # config_layout.addLayout(mode_select)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)


        # ===== 风格学习区域 =====
        style_group = QGroupBox("步骤1: 学习历史用例风格")
        style_layout = QHBoxLayout()

        self.style_path_edit = QLineEdit()
        self.style_path_edit.setPlaceholderText("选择历史测试用例Excel文件...")
        style_layout.addWidget(self.style_path_edit)

        style_btn = QPushButton("浏览...")
        style_btn.clicked.connect(self.select_style_file)
        style_layout.addWidget(style_btn)

        self.learn_btn = QPushButton("学习风格")
        self.learn_btn.clicked.connect(self.learn_style)
        self.learn_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        style_layout.addWidget(self.learn_btn)

        # 样本数量
        style_layout.addWidget(QLabel("样本数:"))
        self.sample_spin = QSpinBox()
        self.sample_spin.setRange(1, 20)
        self.sample_spin.setValue(10)
        style_layout.addWidget(self.sample_spin)

        style_group.setLayout(style_layout)
        layout.addWidget(style_group)

        # ===== 测试点导入区域 =====
        import_group = QGroupBox("步骤2: 导入测试点")
        import_layout = QHBoxLayout()

        self.test_point_path_edit = QLineEdit()
        self.test_point_path_edit.setPlaceholderText("选择测试点文件 (.md 或 .xmind)...")
        import_layout.addWidget(self.test_point_path_edit)

        import_btn = QPushButton("浏览...")
        import_btn.clicked.connect(self.select_test_point_file)
        import_layout.addWidget(import_btn)

        # 批次大小控制
        import_layout.addWidget(QLabel("批次大小:"))
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 20)
        self.batch_spin.setValue(10)  # 默认5个测试点每批
        self.batch_spin.setToolTip("每批处理的测试点数量，越小越稳定但速度慢")
        import_layout.addWidget(self.batch_spin)

        import_group.setLayout(import_layout)
        layout.addWidget(import_group)

        # ===== 生成控制区域 =====
        control_layout = QHBoxLayout()

        self.generate_btn = QPushButton("🚀 生成测试用例")
        self.generate_btn.clicked.connect(self.generate_testcases)
        self.generate_btn.setEnabled(False)
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-size: 14px;
                padding: 10px 20px;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        control_layout.addWidget(self.generate_btn)

        self.export_btn = QPushButton("💾 导出Excel")
        self.export_btn.clicked.connect(self.export_excel)
        self.export_btn.setEnabled(False)
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-size: 14px;
                padding: 10px 20px;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        control_layout.addWidget(self.export_btn)

        layout.addLayout(control_layout)

        # ===== 进度显示 =====
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # ===== 日志显示区域 =====
        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # ===== 预览区域 =====
        preview_group = QGroupBox("生成结果预览")
        preview_layout = QVBoxLayout()

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        preview_layout.addWidget(self.preview_text)

        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

    def init_ai_client(self):
        """初始化AI客户端 - 默认使用SiliconFlow"""
        try:
            # 更新模型选择
            current_model = config.model
            index = self.model_combo.findText(current_model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)

            # 显示API Key状态（脱敏）
            masked_key = config.api_key[:8] + "..." + config.api_key[-4:] if len(config.api_key) > 12 else "***"
            self.api_key_label.setText(f"已加载 ({masked_key})")

            # 默认隐藏Claude CLI模型选择
            self.claude_model_combo.setVisible(False)
            self.claude_model_label.setVisible(False)

            # 创建AI客户端 - 默认SiliconFlow
            self._init_siliconflow_client()

            self.log("✅ AI客户端初始化成功 (SiliconFlow)")

        except Exception as e:
            self.api_key_label.setText("加载失败")
            self.api_key_label.setStyleSheet("color: red;")
            self.log(f"❌ 初始化失败: {str(e)}")
            QMessageBox.critical(self, "错误",
                                 f"API Key配置错误: {str(e)}\n\n请设置环境变量 SILICONFLOW_API_KEY\n或在 ~/.zshrc 中定义 aaaa 变量")

    def on_backend_changed(self, backend: str):
        """切换AI后端"""
        if backend == "SiliconFlow":
            # 显示SiliconFlow相关UI
            self.model_combo.setVisible(True)
            self.model_label.setVisible(True)
            self.api_key_label.setVisible(True)
            self.api_key_label_title.setVisible(True)
            # 隐藏Claude CLI模型选择
            self.claude_model_combo.setVisible(False)
            self.claude_model_label.setVisible(False)
            self._init_siliconflow_client()
            self.log("✅ 已切换到 SiliconFlow 后端")
        else:  # Claude CLI
            # 隐藏SiliconFlow相关UI
            self.model_combo.setVisible(False)
            self.model_label.setVisible(False)
            self.api_key_label.setVisible(False)
            self.api_key_label_title.setVisible(False)
            # 显示Claude CLI模型选择
            self.claude_model_combo.setVisible(True)
            self.claude_model_label.setVisible(True)
            # 创建Claude CLI客户端
            selected_model = self.claude_model_combo.currentText()
            self.ai_client = ClaudeCLIClient(progress_callback=self.log, model=selected_model)

            # 在后台线程测试连接，避免阻塞UI
            self.log(f"正在测试 Claude CLI 连接 (模型: {selected_model})...")
            self.connection_test_thread = ConnectionTestThread(self.ai_client)
            self.connection_test_thread.finished.connect(self.on_connection_test_finished)
            self.connection_test_thread.start()

        # 切换后端后需要重新学习风格
        self.generator = None
        self.generate_btn.setEnabled(False)

    def on_connection_test_finished(self, success: bool, message: str):
        """连接测试完成回调"""
        if success:
            self.log(f"✅ {message}")
            self.log(f"✅ 已切换到 Claude CLI 后端")
        else:
            self.log(f"❌ {message}")
            self.log(f"❌ Claude CLI 连接失败，请检查配置")
            QMessageBox.critical(self, "连接失败",
                f"Claude CLI 连接测试失败\n\n"
                f"错误: {message}\n\n"
                f"请检查:\n"
                f"1. 代理服务 192.168.2.1:3000 是否正常运行\n"
                f"2. API Token 是否有效\n"
                f"3. 模型是否支持")

    def _init_siliconflow_client(self):
        """初始化SiliconFlow客户端"""
        try:
            self.ai_client = SiliconFlowClient(
                api_key=config.api_key,
                model=self.model_combo.currentText(),
                base_url=config.base_url
            )
            # 更新模型选择绑定
            self.model_combo.currentTextChanged.connect(self._update_siliconflow_model)
        except Exception as e:
            raise Exception(f"SiliconFlow初始化失败: {str(e)}")

    def _update_siliconflow_model(self, model: str):
        """更新SiliconFlow模型"""
        if hasattr(self, 'ai_client') and isinstance(self.ai_client, SiliconFlowClient):
            self.ai_client.model = model

    def log(self, message):
        """添加日志"""
        self.log_text.append(message)

    def select_style_file(self):
        """选择风格学习文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择历史用例Excel", "", "Excel文件 (*.xlsx *.xls)"
        )
        if file_path:
            self.style_path_edit.setText(file_path)

    def select_test_point_file(self):
        """选择测试点文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择测试点文件", "",
            "所有文件 (*);;Markdown文件 (*.md);;XMind文件 (*.xmind)"
        )
        if file_path:
            self.test_point_path_edit.setText(file_path)

    def learn_style(self):
        """学习历史用例风格"""
        style_file = self.style_path_edit.text()
        if not style_file:
            QMessageBox.warning(self, "提示", "请先选择历史用例Excel文件")
            return

        try:
            self.log(f"📚 正在学习风格: {style_file}")

            # 创建生成器并学习风格
            self.generator = TestcaseGenerator(self.ai_client)
            self.generator.learn_style(style_file, self.sample_spin.value())

            self.log("✅ 风格学习完成，可以生成测试用例了")
            self.generate_btn.setEnabled(True)

            # QMessageBox.information(self, "成功", "风格学习完成！")

        except Exception as e:
            self.log(f"❌ 学习失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"学习风格失败: {str(e)}")

    def generate_testcases(self):
        """生成测试用例"""
        test_point_file = self.test_point_path_edit.text()
        if not test_point_file:
            QMessageBox.warning(self, "提示", "请先选择测试点文件")
            return

        # 判断文件类型
        file_type = 'markdown' if test_point_file.endswith('.md') else 'xmind'

        # 禁用按钮
        self.generate_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.progress_bar.setRange(0, 0)  # 无限进度

        # 启动后台线程
        batch_size = self.batch_spin.value()
        self.log(f"使用批次大小: {batch_size}")
        self.thread = GeneratorThread(self.generator, test_point_file, file_type, batch_size)
        self.thread.progress.connect(self.log)
        self.thread.finished.connect(self.on_generation_finished)
        self.thread.error.connect(self.on_generation_error)
        self.thread.start()

    def on_generation_finished(self, testcases):
        """生成完成回调"""
        self.current_testcases = testcases
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)

        # 预览显示
        preview = f"共生成 {len(testcases)} 条测试用例:\n\n"
        for i, tc in enumerate(testcases[:5], 1):
            preview += f"【{i}】{tc.get('title', 'N/A')}\n"
            preview += f"    优先级: {tc.get('priority', 'N/A')}\n\n"

        if len(testcases) > 5:
            preview += f"... 还有 {len(testcases) - 5} 条用例"

        self.preview_text.setText(preview)
        self.log(f"✅ 生成完成，共 {len(testcases)} 条用例")

        self.generate_btn.setEnabled(True)
        self.export_btn.setEnabled(True)

    def on_generation_error(self, error_msg):
        """生成错误回调"""
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.log(f"❌ 生成失败: {error_msg}")
        QMessageBox.critical(self, "错误", f"生成失败: {error_msg}")
        self.generate_btn.setEnabled(True)

    def export_excel(self):
        """导出Excel"""
        if not self.current_testcases:
            QMessageBox.warning(self, "提示", "没有可导出的测试用例")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存测试用例", "测试用例.xlsx", "Excel文件 (*.xlsx)"
        )

        if not file_path:
            return

        try:
            exporter = ExcelExporter()
            exporter.export(self.current_testcases, file_path)

            self.log(f"💾 已导出到: {file_path}")
            QMessageBox.information(self, "成功", f"测试用例已导出到:\n{file_path}")

        except Exception as e:
            self.log(f"❌ 导出失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()