# CLAUDE.md
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
## 项目背景
测试点转测试用例工具 - 一个PyQt6 GUI应用程序，使用AI学习上传的历史测试用例风格，将测试点（来自Markdown或XMind文件）转换为标准化测试用例。
## 业务背景
hapa 是海外电商+游戏化网站，核心业务是神秘盒子随机开盒，用户支付购买盒子后随机获得物品。
主要玩法包括：开盒、upgrade（升级挑战）、battle（对战）、treasure hunting（寻宝）、bingo、daily lottery、活动等。
开盒获得的物品可回收换取金额或收下发货。
## 代码规范
变量 / 函数：蛇形命名
类：大驼峰
常量：全大写
缩进 4 空格
注释清晰、函数简短、不写重复代码
## 常用命令
python3 main.py
pip install -r requirements.txt
## 关键数据流
1. **Style Learning**: Historical Excel → `ExcelReader.extract_style_samples()` → style text
2. **Parse Test Points**: `.md` or `.xmind` file → Parser → `List[Dict]` with keys: `module`, `feature`, `content`, `level`
3. **Generate**: Test points + style samples → `SiliconFlowClient.generate_testcases_batch()` → JSON test cases
4. **Export**: `List[Dict]` test cases → `ExcelExporter.export()` → `.xlsx` file
## 测试用例生成注意事项
请严格按照以下要求生成测试用例（核心要求）：
1. 用例最开始几条必须是正常的完整流程（必须）
2. 用例标题必须以动词开头，明确预期结果，示例：打开、点击、输入等，必须清晰描述操作对象 + 操作行为，必须隐含 / 明确体现测试目的，禁止模糊描述，长度控制在 5–50 字，简洁无歧义，但是需要描述完整，禁止使用疑问、感叹、描述性语句（强制！！！），如果导入的测试点中有相同的测试点，需要在测试标题中加入上级测试点内容，例如相同等级的节点新用户引导节点和首充用户节点下都有一个验证在ios上的显示，那测试标题分别就应该是验证新用户引导在ios上的显示和首充用户在ios上的显示
3. 优先级分为：高（主流程）、中（重要功能、异常场景、按钮等）、低（UI、边缘场景、文案、规则说明等）
4. 前置条件必须是可执行的具体状态描述，必须具体、明确，禁止模糊、空话，多条前置条件必须分条描述
5. 测试步骤必须使用数字编号（1、2、3…），操作和数据分离，每一步只描述一个独立操作，步骤必须连贯、可复现，每一步需要详细的操作步骤
6. 预期结果必须是可验证的断言，必须与测试步骤一一对应，必须明确：页面 / 提示 / 数据 / 状态变化，禁止使用 "应该正常""可以使用" 等模糊描述
7. 必须以xmind的一级标签为测试项
8. 叶子节点(🍃标记)数量 = 用例数量，必须100%转换，一条都不能少！不允许遗漏、合并、丢弃任何一条测试点（最重要！！！），输入10个叶子节点，必须输出10条用例，输入63个叶子节点，必须输出63条用例
9. test_item必须等于一级测试点名称，禁止使用其他任何内容，一级测试点是"新客流程优化"，所有用例test_item只能写"新客流程优化"，禁止使用二级、三级测试点或其他内容作为test_item
10. 只输出纯JSON数组，禁止输出任何其他文字，禁止输出"根据测试点生成..."等开场白，禁止输出"共X条"等统计文字，直接以 [ 开头，以 ] 结尾
11. 测试步骤data字段处理，不要出现数据及具体数据
12. 一条测试用例如果是需要满足a,b,c三种条件才能触发，为了验证只有a不满足的场景，那前置条件不仅仅要标明a不满足，还要加上满足了b和c