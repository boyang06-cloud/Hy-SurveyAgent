# Hy-SurveyAgent 工作台设计规范

## 设计依据

使用 ui-ux-pro-max 检索 academic research workspace minimal 与 research dashboard productivity。
学术配色、可读性和 Swiss Modernism 的栅格建议适用；返回的 Newsletter / Product Demo
落地页结构不适用本项目，因此不采用该部分，工作台布局按真实研究任务设计。

## 视觉与交互

- 桌面三栏：任务导航 / 研究内容 / 执行与证据；小屏改为单列和顶部导航。
- 暖白底色、深蓝主操作、金色证据强调；颜色值集中为 CSS 语义变量。
- 中文使用系统无衬线字体；英文标题与正文阅读区使用 Georgia / 中文衬线回退。
- 页面内不加载远程字体、脚本、统计或媒体。
- 8px 间距节奏；正文 16px、1.6 行高；44px 操作目标与清晰键盘焦点。
- 唯一主操作为启动 Survey；研究问题通过渐进展开提供。
- 文件选择支持键盘；错误保留输入并聚焦错误提示；上传最多 10 MB、200 篇论文。
- 任务状态来自后端日志和产物，不提供模拟进度百分比。
- 完成生成与核验支持率分开展示；dry-run 明确标记无正文、无真实核验。
- 历史任务与结果页使用 hash 深链接；浏览器返回保留表单草稿（仅会话内存）。
- 引用编号可跳到论文及证据；不把缺失核验视为通过。
- 减少动态效果偏好受尊重；不使用持续装饰动画。

## 实现

FastAPI + 原生 HTML / CSS / JavaScript，无 Node 构建链。Web 契约位于
app/web/schemas.py；复用原 Pipeline 与原运行产物。详情、安全边界和启动方式见 docs/Web 工作台.md。
