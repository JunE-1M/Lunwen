# 部署到 GitHub Pages（固定网址 + 真正无人值守）

目标：固定网址 `https://<你的用户名>.github.io/ai-paper-archive/`，由 GitHub 服务器每天北京时间 08:00 自动重抓论文并发布，完全不依赖你本机或 WorkBuddy 常开。

## 你只需做一次的事

### 1. 生成 GitHub Personal Access Token（PAT）
- GitHub → 右上角头像 → **Settings → Developer settings → Personal access tokens → Tokens (classic)**
- **Generate new token (classic)**，Note 随便写，Expiration 选 30/90 天
- 勾选 **`repo`**（包含 public_repo 即可）
- 生成后复制 `ghp_xxxxxxxx`

### 2. 把仓库推上去（两种任选）
**方式 A：用 PAT 直推（推荐，不用配 SSH）**
```bash
cd ai-paper-archive-app
git init -q
git remote add origin https://<你的用户名>:<你的PAT>@github.com/<你的用户名>/ai-paper-archive.git
git add -A
git -c user.name="你的名" -c user.email="你的邮箱" commit -m "init"
git branch -M main
git push -u origin main
```
> 也可以直接把 `ghp_` 发给我，我帮你自动建仓库并推送（token 仅用于本次，不写进任何文件）。

**方式 B：用本机 SSH 公钥**
1. 把公钥 `~/.ssh/id_ed25519.pub` 内容加到 GitHub → Settings → SSH and GPG keys
2. 网页建一个 **public** 空仓库 `ai-paper-archive`
3. `git remote add origin git@github.com:<用户名>/ai-paper-archive.git` 后 push

### 3. 开启 Pages（仅需手动点一次）
仓库 → **Settings → Pages → Build and deployment → Source 选 "GitHub Actions"**。
之后每天自动发布，固定网址永久不变。

## 之后每天发生什么
- GitHub Actions 在 UTC 00:00（北京时间 08:00）触发
- 运行 `update.py` 联网拉取 aihot + arXiv 摘要，重新生成 `www/index.html`
- 自动 commit & push，Pages 重新发布
- 你打开固定网址看到的就是当天最新内容

## 想立刻手动更新一次？
仓库页面 → **Actions → 每日更新 AI 论文档案库 → Run workflow**。

## 注意
- 本仓库只含 `update.py` / `www/` / `.github/`，不含 `node_modules`、`android/`、`ios/`（已 gitignore）
- X 类条目只有 aihot 提供的中文摘要，无原始推文正文；arXiv 类会附完整英文摘要与 PDF 直链
