# AI 论文档案库（内容直读版）

最近 7 天 AI 论文的学术档案库，每日自动更新。**中文标题与摘要直接呈现在卡片里**，你无需打开被墙的 X 链接即可阅读；arXiv 论文额外抓取完整英文摘要并附 PDF 直链。

## 核心特性
- **内容直读**：每篇卡片正文就是中文摘要，X / 境外媒体类链接降为角落灰色小字（注明"国内需代理"），不再是大按钮
- **arXiv 增强**：生成阶段联网抓取 arXiv 官方完整英文摘要，卡片内可"展开原文摘要"；附官方 PDF 下载
- **数据来源**：AI HOT 聚合（精选 + 全量公开，排除未审 / 爆文榜），约 50 篇 / 7 天
- **零依赖**：纯单文件 HTML，样式脚本全内联，无外部资源；生成时已剔除所有 API 端点 / 参数
- **响应式 + 滚动渐入**，手机可直接看

## 目录结构
```
ai-paper-archive-app/
├── update.py                 # 每日生成脚本（拉 aihot + arXiv 摘要 → 注入模板）
├── www/
│   ├── index.template.html   # 页面模板（__ARCHIVE_JSON__ 占位）
│   └── index.html            # 生成产物（每日覆盖）
├── .github/workflows/update.yml  # GitHub Actions 每日北京时间08:00 自动更新
├── DEPLOY_LOG.md             # 每次部署的分享链接记录
├── GITHUB_DEPLOY.md          # 固定网址（GitHub Pages）部署指南
└── README.md
```

## 本地运行 / 手动更新
```bash
cd ai-paper-archive-app
python3 update.py                         # 默认 7 天 / 50 篇
python3 update.py --window 3d --take 30   # 自定义窗口与数量
```
生成结果写入 `www/index.html`，浏览器直接打开即可。

## 两种长期托管方式
| 方式 | 网址 | 自动更新 | 门槛 |
|------|------|----------|------|
| **CloudStudio（当前）** | 公网沙箱链接（见 DEPLOY_LOG.md） | WorkBuddy 每日自动化触发 | 无需 Mac / 无费用；网址每次部署会变 |
| **GitHub Pages（推荐长期）** | `https://<用户名>.github.io/ai-paper-archive/` | GitHub Actions 服务端 cron | 需 GitHub 账号 + PAT；网址固定、真正无人值守 |

详细步骤见 **GITHUB_DEPLOY.md**。本机已生成 SSH 公钥 `~/.ssh/id_ed25519.pub`，但未绑定 GitHub 账号；推送最顺的方式是用 PAT（发我 `ghp_...` 我可代建仓库并推送）。

## 移动端 App（可选）
若想进应用商店，可在此基础上用 Capacitor 打包（需 Mac + Xcode + 开发者账号）。当前环境无完整 Xcode，iOS 工程需在本地生成。
