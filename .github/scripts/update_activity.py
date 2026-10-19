#!/usr/bin/env python3
"""Rewrite the activity section of README.md from the public events API.

Runs inside GitHub Actions, but works locally too:
    GITHUB_REPOSITORY_OWNER=intfai GITHUB_TOKEN=... python update_activity.py
"""
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER") or os.environ.get("GH_OWNER") or "intfai"
TOKEN = os.environ.get("GITHUB_TOKEN")
README = os.environ.get("README_PATH", "README.md")
START = "<!--START_SECTION:activity-->"
END = "<!--END_SECTION:activity-->"
MAX_ITEMS = 8


def api(url):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "intfai-profile-activity",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read())


def ago(stamp):
    try:
        then = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return ""
    delta = datetime.datetime.now(datetime.timezone.utc) - then
    secs = int(delta.total_seconds())
    if secs < 60:
        return "刚刚"
    if secs < 3600:
        return f"{secs // 60} 分钟前"
    if secs < 86400:
        return f"{secs // 3600} 小时前"
    if secs < 86400 * 30:
        return f"{secs // 86400} 天前"
    return then.strftime("%Y-%m-%d")


def describe(event):
    kind = event.get("type", "")
    payload = event.get("payload") or {}
    repo = (event.get("repo") or {}).get("name", "")
    repo_md = f"[{repo}](https://github.com/{repo})" if repo else "unknown repo"

    if kind == "PushEvent":
        n = len(payload.get("commits") or []) or payload.get("size") or 0
        ref = (payload.get("ref") or "").replace("refs/heads/", "")
        tail = f" → `{ref}`" if ref else ""
        what = f"推送了 {n} 个提交" if n > 0 else "推送了代码"
        return "🔨", f"向 {repo_md} {what}{tail}"

    if kind == "PullRequestEvent":
        pr = payload.get("pull_request") or {}
        num = payload.get("number")
        action = payload.get("action")
        merged = bool(pr.get("merged"))
        verb = "合并" if merged else {"opened": "发起", "closed": "关闭", "reopened": "重开"}.get(action, action)
        title = pr.get("title") or ""
        return "🎉", f"{verb} PR #{num} · {title} ({repo_md})"

    if kind == "PullRequestReviewEvent":
        pr = payload.get("pull_request") or {}
        return "👀", f"评审 PR #{payload.get('number')} ({repo_md})"

    if kind == "IssuesEvent":
        issue = payload.get("issue") or {}
        action = payload.get("action")
        verb = {"opened": "新建", "closed": "关闭", "reopened": "重开"}.get(action, action)
        return "📋", f"{verb} Issue #{payload.get('number')} · {issue.get('title', '')} ({repo_md})"

    if kind == "IssueCommentEvent":
        return "💬", f"评论 Issue #{payload.get('issue', {}).get('number')} ({repo_md})"

    if kind == "CreateEvent":
        ref_type = payload.get("ref_type")
        ref = payload.get("ref")
        emoji = {"repository": "📦", "branch": "🌿", "tag": "🏷️"}.get(ref_type, "✨")
        if ref_type == "repository":
            return emoji, f"创建了仓库 {repo_md}"
        label = {"branch": "分支", "tag": "标签"}.get(ref_type, ref_type)
        return emoji, f"创建{label} `{ref}` ({repo_md})"

    if kind == "DeleteEvent":
        return "🧹", f"删除 {payload.get('ref_type')} `{payload.get('ref')}` ({repo_md})"

    if kind == "WatchEvent":
        return "⭐", f"收藏（Star）了 {repo_md}"

    if kind == "ForkEvent":
        return "🍴", f"Fork 了 {repo_md}"

    if kind == "ReleaseEvent":
        return "🚀", f"发布 {payload.get('release', {}).get('tag_name', '')} ({repo_md})"

    if kind == "PublicEvent":
        return "🔓", f"将 {repo_md} 设为公开"

    return "•", f"{kind} · {repo_md}"


def build_section():
    try:
        events = api(f"https://api.github.com/users/{OWNER}/events/public?per_page=50")
    except urllib.error.HTTPError as exc:
        return [f"- ⚠️ 动态获取失败：HTTP {exc.code}（工作流下次运行时会重试）"]
    except Exception as exc:  # noqa: BLE001
        return [f"- ⚠️ 动态获取失败：{type(exc).__name__}"]

    if not events:
        return ["- 暂无公开动态 —— 提交代码、开 Issue 或 Star 仓库后会出现在这里。"]

    lines, seen = [], set()
    for event in events:
        emoji, text = describe(event)
        key = (event.get("type"), text)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- {emoji} {text} · <sub>{ago(event.get('created_at', ''))}</sub>")
        if len(lines) >= MAX_ITEMS:
            break
    return lines


def main():
    with open(README, "r", encoding="utf-8") as fh:
        content = fh.read()

    if START not in content or END not in content:
        print(f"markers missing: {START} / {END}", file=sys.stderr)
        return 1

    block = "\n".join(
        [START, "<!-- 本区块由 .github/workflows/activity.yml 自动生成，请勿手动编辑 -->"]
        + build_section()
        + [END]
    )
    updated = re.sub(
        re.escape(START) + r".*?" + re.escape(END),
        block,
        content,
        flags=re.S,
    )

    if updated == content:
        print("no change")
        return 0
    with open(README, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(updated)
    print("activity section updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
