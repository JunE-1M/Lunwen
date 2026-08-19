#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 论文学术档案库 —— 周更自动生成脚本（云端累积版）

作用：
  1. 拉取 aihot 最近 7 天全量论文（mode=all，新鲜到当天）
  2. 与仓库内 archive.json（历史全量，按 id 去重）合并，实现云端累积存档
  3. 仅保留最近 KEEP_DAYS(30) 天，过滤后重新生成单文件页面
  4. 对 arXiv 条目抓取完整英文摘要 + PDF 直链
  5. 注入模板输出 www/index.html，并把合并后历史写回 archive.json

用法：
  python3 update.py
  python3 update.py --window 7d --take 100 --keep-days 30
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
AIHOT_URL = "https://aihot.virxact.com/api/v1/items?mode=all&window={window}&category=paper&limit={limit}"
UA = "aihot-skill/1.2.1 (+https://aihot.virxact.com/aihot-skill/)"
TEMPLATE = "www/index.template.html"
OUTPUT = "www/index.html"
ARCHIVE_PATH = "archive.json"   # 历史全量库（云端累积），与脚本同目录
WINDOW = "7d"
LIMIT = 100
KEEP_DAYS = 30
BEIJING = timezone(timedelta(hours=8))


def log(*a):
    print("[update]", *a, file=sys.stderr)


# ---------------------------------------------------------------------------
# 网络
# ---------------------------------------------------------------------------
def http_get(url, timeout=30, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8")
        except Exception as e:  # noqa
            last = e
            log(f"  请求失败({i+1}/{retries}): {url[:80]} -> {e}")
            time.sleep(2 * (i + 1))
    raise last


# ---------------------------------------------------------------------------
# 时间
# ---------------------------------------------------------------------------
def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def eff_iso(it):
    """返回『用于排序/展示的有效时间』与是否为原文发布时间。"""
    pub = it.get("publishedAt")
    disc = it["discoveredAt"]
    if not pub:
        return disc, False
    p = parse_iso(pub)
    dc = parse_iso(disc)
    if (dc - p).total_seconds() > 72 * 3600:
        return pub, True
    return disc, (pub is not None)


# ---------------------------------------------------------------------------
# 来源归一化
# ---------------------------------------------------------------------------
def classify(src_name):
    n = src_name
    if "HuggingFace" in n:
        return "hf"
    if n.startswith("X") or "：" in n:
        return "x"
    if any(k in n for k in ("arXiv", "Apple Machine Learning", "DeepMind", "Research", "Google")):
        return "research"
    if any(k in n for k in ("公众号", "IT之家", "Ars Technica", "MarkTechPost", "Hacker News", "TechPost", "机器之心", "量子位")):
        return "media"
    return "default"


def make_badge(src_name):
    n = re.sub(r"（[^）]*）", "", src_name).strip()
    if "HuggingFace" in n:
        return "HuggingFace Daily"
    if "Apple Machine Learning" in n:
        return "Apple ML Research"
    if "Hacker News" in n:
        return "Hacker News"
    if "：" in n:
        plat, rest = n.split("：", 1)
        plat = plat.strip()
        rest = re.sub(r"\([^)]*\)", "", rest).strip()
        if plat == "X":
            return ("X · " + rest) if rest else "X"
        if plat == "公众号":
            return rest if rest else "公众号"
        return plat
    n = re.sub(r"\([^)]*\)", "", n).strip()
    return n


def classify_cat(title):
    """按标题关键词把论文归入主题类（用于『可下载 PDF』弹窗分组）。"""
    t = (title or "").lower()
    rules = [
        ("智能体", ["智能体", "agent", "agentic", "多智能体", "workflow"]),
        ("大语言模型", ["语言模型", "llm", "大模型", "gpt", "transformer", "预训练", "token"]),
        ("多模态/视觉", ["视觉", "图像", "vision", "image", "视频", "多模态", "multimodal", "speech"]),
        ("强化学习", ["强化学习", "reinforcement", "reward", "奖励", "rlhf"]),
        ("检索/RAG", ["检索", "retrieval", "rag", "embedding", "向量", "search"]),
        ("推理与训练", ["推理", "训练", "training", "inference", "蒸馏", "微调", "fine-tun", "量化"]),
    ]
    for cat, kws in rules:
        if any(k in t for k in kws):
            return cat
    return "其他"


# ---------------------------------------------------------------------------
# arXiv 完整摘要抓取（生成阶段联网；国内用户无需再访问 arXiv）
# ---------------------------------------------------------------------------
_arxiv_id_re = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?", re.I)


def arxiv_id_from(link):
    if not link:
        return None
    m = _arxiv_id_re.search(link)
    return m.group(1) if m else None


def fetch_arxiv_abstract(arxiv_id):
    """返回 (abstract_en, pdf_url) 或 (None, None)。"""
    try:
        api = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
        xml = http_get(api, timeout=12)
        root = ET.fromstring(xml)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entry = root.find("a:entry", ns)
        if entry is None:
            return None, None
        summ = entry.find("a:summary", ns)
        abstract = summ.text.strip() if summ is not None and summ.text else None
        pdf_url = None
        for link in entry.findall("a:link", ns):
            if link.get("title") == "pdf":
                pdf_url = link.get("href")
        if not pdf_url:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        return abstract, pdf_url
    except Exception as e:  # noqa
        log(f"  arXiv 摘要抓取失败 {arxiv_id}: {e}")
        return None, f"https://arxiv.org/pdf/{arxiv_id}"


def download_pdf(arxiv_id, dest_dir):
    """下载 arXiv PDF 到 dest_dir/<id>.pdf；成功返回相对路径 'pdfs/<id>.pdf'，失败返回 None。
    仅在云端（--download-pdf）调用，本地不执行，故绝不占用本地磁盘。"""
    try:
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, arxiv_id + ".pdf")
        # 已存在且体积正常则直接复用，避免重复下载
        if os.path.exists(dest) and os.path.getsize(dest) > 5000:
            return "pdfs/" + arxiv_id + ".pdf"
        url = f"https://arxiv.org/pdf/{arxiv_id}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if len(data) < 5000:
            log(f"  PDF 疑似非文件({len(data)}B)，跳过 {arxiv_id}")
            return None
        with open(dest, "wb") as f:
            f.write(data)
        return "pdfs/" + arxiv_id + ".pdf"
    except Exception as e:  # noqa
        log(f"  PDF 下载失败 {arxiv_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# 历史存档（云端累积核心）
# ---------------------------------------------------------------------------
def load_archive():
    """读历史全量库（按 id 去重）。不存在/损坏则返回空。"""
    try:
        with open(ARCHIVE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return {p["id"]: p for p in d.get("papers", []) if p.get("id")}
    except FileNotFoundError:
        return {}
    except Exception as e:
        log("读取 archive 失败，从空开始:", e)
        return {}


def save_archive(m):
    arr = sorted(m.values(), key=lambda p: parse_iso(p["ts"]), reverse=True)
    with open(ARCHIVE_PATH, "w", encoding="utf-8") as f:
        json.dump({"papers": arr}, f, ensure_ascii=False, indent=1)


def _max_item_date(items):
    ds = []
    for it in items:
        t = (it.get("publishedAt") or it.get("discoveredAt") or "")[:10]
        if len(t) == 10:
            ds.append(t)
    return max(ds) if ds else ""


def fetch_aihot_items(url, fresh_days=4):
    """拉取 aihot 列表，并对『数据新鲜度』做校验。

    aihot 源偶发返回陈旧数据（最新日期远早于今天），故若最新日期
    比 (今天-fresh_days) 还旧，则重试最多 3 次；仍失败则采用最后一次结果。
    """
    cutoff = (datetime.now(BEIJING) - timedelta(days=fresh_days)).strftime("%Y-%m-%d")
    last_items = []
    for i in range(3):
        try:
            data = json.loads(http_get(url))
            items = data.get("items", []) or []
        except Exception as e:  # noqa
            log(f"  aihot 解析失败({i + 1}/3): {e}")
            items = []
        if items:
            md = _max_item_date(items)
            if md >= cutoff:
                log(f"  aihot 数据新鲜(最新 {md})，采用")
                return items
            log(f"  aihot 数据偏旧(最新 {md} < 期望 {cutoff})，重试({i + 1}/3)…")
        else:
            log(f"  aihot 返回空，重试({i + 1}/3)…")
        last_items = items
        time.sleep(15)
    log("  达到重试上限，采用最后一次抓取结果")
    return last_items


def make_rec(it, skip_arxiv=False):
    """把单条 aihot 条目转为卡片记录（含 id 以便去重累积）。"""
    iso, is_pub = eff_iso(it)
    title = it.get("title") or it.get("originalTitle") or "无标题"
    summary = (it.get("summary") or "").strip() or "（暂无摘要）"
    src = it["source"]["name"]
    link = (it.get("links", {}) or {}).get("original") or (it.get("links", {}) or {}).get("aihot")
    src_type = classify(src)
    rec = {
        "id": it.get("id"),
        "seq": 0,
        "title": title,
        "badge": make_badge(src),
        "srcType": src_type,
        "ts": iso,
        "isPub": is_pub,
        "summary": summary,
        "link": link,
        "pdf": None,
        "abstractEn": None,
        "cat": classify_cat(title),
    }
    aid = arxiv_id_from(link)
    if aid:
        # 即使不抓摘要，也可直接构造 arXiv PDF 直链
        rec["pdf"] = f"https://arxiv.org/pdf/{aid}"
        if not skip_arxiv:
            try:
                abstract, _ = fetch_arxiv_abstract(aid)
                if abstract:
                    rec["abstractEn"] = re.sub(r"\s+", " ", abstract).strip()
            except Exception as e:
                log(f"  arXiv 摘要跳过 {aid}: {e}")
        time.sleep(0.2)  # 礼貌限速
    return rec


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def build(window=WINDOW, take=LIMIT, out=OUTPUT, keep_days=KEEP_DAYS, skip_arxiv=False, download_pdf=False):
    limit = max(take, 60)
    url = AIHOT_URL.format(window=window, limit=limit)
    log("拉取 aihot:", url)
    items = fetch_aihot_items(url)
    log(f"原始条目 {len(items)}，取前 {take} 合并入历史")

    def keyf(it):
        return parse_iso(eff_iso(it)[0])

    items = sorted(items, key=keyf, reverse=True)[:take]

    # 合并进历史（按 id 去重，新抓覆盖旧）
    existing = load_archive()
    new_map = {}
    for it in items:
        rid = it.get("id")
        if not rid:
            continue
        new_map[rid] = make_rec(it, skip_arxiv)
    merged = {**existing, **new_map}
    log(f"合并后历史 {len(merged)} 篇（本次新增/更新 {len(new_map)}）")

    # 仅保留最近 keep_days 天
    cutoff = datetime.now(BEIJING) - timedelta(days=keep_days)
    merged = {k: v for k, v in merged.items() if parse_iso(v["ts"]).astimezone(BEIJING) >= cutoff}
    log(f"保留最近 {keep_days} 天：{len(merged)} 篇")

    save_archive(merged)

    # 云端下载 PDF 到 www/pdfs（仅 --download-pdf 时；本地不执行，故不占用本地磁盘）
    if download_pdf:
        pdf_dir = os.path.join(os.path.dirname(os.path.abspath(out)), "pdfs")
        cached = 0
        for p in merged.values():
            aid = arxiv_id_from(p.get("link"))
            if not aid:
                continue
            local = download_pdf(aid, pdf_dir)
            if local:
                p["pdf"] = local
                cached += 1
            time.sleep(0.3)  # 礼貌限速，避免对 arXiv 造成压力
        log(f"PDF 同源化完成：本次 {cached} 篇")

    # 排序 + 重新编号 seq
    papers = sorted(merged.values(), key=lambda p: parse_iso(p["ts"]), reverse=True)
    for i, p in enumerate(papers, 1):
        p["seq"] = i

    pdf_count = sum(1 for p in papers if p.get("pdf"))
    x_count = sum(1 for p in papers if p.get("srcType") == "x")
    bj = [parse_iso(p["ts"]).astimezone(BEIJING) for p in papers]
    meta = {
        "total": len(papers),
        "earliest": min(bj).strftime("%Y-%m-%d"),
        "latest": max(bj).strftime("%Y-%m-%d"),
        "generatedAt": datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M"),
        "pdfCount": pdf_count,
        "xCount": x_count,
        "keepDays": keep_days,
    }

    # 读模板、注入
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    blob = json.dumps({
        "meta": {
            "total": meta["total"], "earliest": meta["earliest"], "latest": meta["latest"],
            "generatedAt": meta["generatedAt"], "pdfCount": pdf_count, "xCount": x_count,
            "keepDays": keep_days,
        },
        "papers": papers,
    }, ensure_ascii=False)
    blob = blob.replace("</", "<\\/")  # 防 </script> 截断
    html = tpl.replace("__ARCHIVE_JSON__", blob)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    log(f"已生成 {out}：{meta['total']} 篇 | 可下载PDF {pdf_count} | X/需代理 {x_count}")
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", default=WINDOW)
    ap.add_argument("--take", type=int, default=LIMIT)
    ap.add_argument("--out", default=OUTPUT)
    ap.add_argument("--keep-days", type=int, default=KEEP_DAYS)
    ap.add_argument("--no-arxiv", action="store_true", help="跳过 arXiv 摘要抓取（仅构造 PDF 直链，本地快速验证用）")
    ap.add_argument("--download-pdf", action="store_true", help="云端将 arXiv PDF 下载到 www/pdfs 实现同源直下（本地请勿使用，避免占用磁盘）")
    args = ap.parse_args()
    build(args.window, args.take, args.out, args.keep_days, args.no_arxiv, args.download_pdf)
