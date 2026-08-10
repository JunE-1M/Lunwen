#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 论文学术档案库 —— 每日自动生成脚本（内容直读版）

作用：
  1. 联网拉取 aihot 最近窗口内的「精选 + 全量公开」论文（约 50 篇，排除未审/爆文榜）
  2. 对 arXiv 条目，用 arXiv 官方 API 抓取完整英文摘要（生成阶段服务器联网，国内用户无需再访问）
  3. 处理：有效时间 / 来源徽章 / 摘要（作为卡片内联正文）/ 链接 / PDF 直链
  4. 注入 HTML 模板，输出 www/index.html（纯单文件、零外部资源、零端点泄漏）

用法：
  python3 update.py                  # 默认 7 天窗口 / 取 50 篇
  python3 update.py --window 3d --take 30
  python3 update.py --out www/index.html
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
AIHOT_URL = "https://aihot.virxact.com/api/v1/items?mode=all&window={window}&category=paper&limit={limit}"
UA = "aihot-skill/1.2.1 (+https://aihot.virxact.com/aihot-skill/)"
TEMPLATE = "www/index.template.html"
OUTPUT = "www/index.html"
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
    # 若收录远晚于发布（如历史长文被翻出），用发布时间更合理
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
        xml = http_get(api, timeout=25)
        root = ET.fromstring(xml)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entry = root.find("a:entry", ns)
        if entry is None:
            return None, None
        summ = entry.find("a:summary", ns)
        abstract = summ.text.strip() if summ is not None and summ.text else None
        # PDF 直链
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


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def build(window="7d", take=50, out=OUTPUT):
    url = AIHOT_URL.format(window=window, limit=max(take, 60))
    log("拉取 aihot:", url)
    data = json.loads(http_get(url))
    items = data.get("items", [])
    log(f"原始条目 {len(items)}，取前 {take}")

    # 有效时间排序（倒序）
    def keyf(it):
        return parse_iso(eff_iso(it)[0])

    items = sorted(items, key=keyf, reverse=True)[:take]

    papers = []
    pdf_count = 0
    x_count = 0
    for i, it in enumerate(items, 1):
        iso, is_pub = eff_iso(it)
        title = it.get("title") or it.get("originalTitle") or "无标题"
        summary = (it.get("summary") or "").strip()
        if not summary:
            summary = "（暂无摘要）"
        src = it["source"]["name"]
        link = (it.get("links", {}) or {}).get("original") or (it.get("links", {}) or {}).get("aihot")
        src_type = classify(src)
        if src_type == "x":
            x_count += 1

        rec = {
            "seq": i,
            "title": title,
            "badge": make_badge(src),
            "srcType": src_type,
            "ts": iso,
            "isPub": is_pub,
            "summary": summary,        # 卡片内联正文（中文）
            "link": link,              # 原文链接（X 类国内需代理）
            "pdf": None,
            "abstractEn": None,        # arXiv 完整英文摘要（内联展开）
        }

        # arXiv：抓完整摘要 + PDF 直链
        aid = arxiv_id_from(link)
        if aid:
            abstract, pdf = fetch_arxiv_abstract(aid)
            if abstract:
                rec["abstractEn"] = re.sub(r"\s+", " ", abstract).strip()
            if pdf:
                rec["pdf"] = pdf
                pdf_count += 1
            time.sleep(0.4)  # 礼貌限速

        papers.append(rec)

    bj = [parse_iso(p["ts"]).astimezone(BEIJING) for p in papers]
    meta = {
        "total": len(papers),
        "earliest": min(bj).strftime("%Y-%m-%d"),
        "latest": max(bj).strftime("%Y-%m-%d"),
        "generatedAt": datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M"),
        "pdfCount": pdf_count,
        "xCount": x_count,
    }

    # 读模板、注入
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    blob = json.dumps({"meta": meta, "papers": papers}, ensure_ascii=False)
    blob = blob.replace("</", "<\\/")  # 防 </script> 截断
    html = tpl.replace("__ARCHIVE_JSON__", blob)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    log(f"已生成 {out}：{meta['total']} 篇 | 可下载PDF {pdf_count} | X/需代理 {x_count}")
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", default="7d")
    ap.add_argument("--take", type=int, default=50)
    ap.add_argument("--out", default=OUTPUT)
    args = ap.parse_args()
    build(args.window, args.take, args.out)
