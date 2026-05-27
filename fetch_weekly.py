#!/usr/bin/env python3
"""Fetch weekly GitHub trends data for 4 sections."""
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests

UA = "weekly-github-trends/1.0 (GitHub Actions)"
GITHUB_API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"User-Agent": UA, "Accept": "application/vnd.github.v3+json"}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"


def gh_search(query: str, sort: str = "stars", per_page: int = 15) -> list[dict]:
    """Search GitHub repos API."""
    url = f"{GITHUB_API}/search/repositories"
    params = {"q": query, "sort": sort, "order": "desc", "per_page": per_page}
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("items", [])


def gh_trending_weekly() -> list[dict]:
    """Scrape GitHub Trending page (weekly). HTML parsing fallback."""
    url = "https://github.com/trending?since=weekly"
    headers = {"User-Agent": UA, "Accept": "text/html"}
    r = requests.get(url, headers=headers, timeout=30)
    html = r.text

    # Parse trending repos from HTML
    pattern = re.compile(
        r'<h2 class="h3 lh-condensed">\s*<a href="/([^/]+/[^"]+)"[^>]*>.*?</a>\s*</h2>',
        re.DOTALL,
    )
    matches = pattern.findall(html)
    repos = []
    seen = set()
    for full_name in matches:
        if full_name not in seen:
            seen.add(full_name)
            repos.append({"full_name": full_name.strip()})
    return repos


def get_repo_details(full_name: str) -> dict:
    """Get repo metadata via API."""
    url = f"{GITHUB_API}/repos/{full_name}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return {}
    d = r.json()
    return {
        "full_name": d.get("full_name", ""),
        "name": d.get("name", ""),
        "description": (d.get("description") or "")[:200],
        "stars": d.get("stargazers_count", 0),
        "language": d.get("language", ""),
        "html_url": d.get("html_url", ""),
        "topics": d.get("topics", []),
        "pushed_at": d.get("pushed_at", ""),
    }


def check_skill_file(full_name: str) -> tuple:
    """Check if repo has SKILL.md and return raw URL + install commands."""
    raw_url = f"https://raw.githubusercontent.com/{full_name}/main/SKILL.md"
    alt_url = f"https://raw.githubusercontent.com/{full_name}/master/SKILL.md"
    headers = {"User-Agent": UA}
    # Try main branch first
    r = requests.head(raw_url, headers=headers, timeout=10)
    actual_url = raw_url
    if r.status_code != 200:
        r = requests.head(alt_url, headers=headers, timeout=10)
        if r.status_code == 200:
            actual_url = alt_url
        else:
            return "", []

    repo_name = full_name.split("/")[-1]
    install_cmds = [
        f"mkdir -p ~/.claude/skills/{repo_name}",
        f"curl -o ~/.claude/skills/{repo_name}/SKILL.md {actual_url}",
    ]

    # Try to find pip dependencies in SKILL.md content
    r = requests.get(actual_url, headers=headers, timeout=10)
    if r.status_code == 200:
        content = r.text[:5000]
        pip_match = re.search(r"pip install (.+?)(?:\n|$)", content)
        if pip_match:
            install_cmds.append(f"pip install {pip_match.group(1)}")

    return actual_url, install_cmds


def build_entry(repo: dict, rank: int, stars_weekly: int = 0) -> dict:
    """Build a standardized entry dict from repo data."""
    full_name = repo.get("full_name", "")
    raw_url, install_cmds = "", []
    if full_name:
        raw_url, install_cmds = check_skill_file(full_name)

    return {
        "rank": rank,
        "name": repo.get("name", ""),
        "full_name": full_name,
        "description": (repo.get("description") or "")[:200],
        "stars": repo.get("stars", 0),
        "stars_weekly": stars_weekly,
        "language": repo.get("language", ""),
        "html_url": repo.get("html_url", ""),
        "raw_skill_url": raw_url,
        "install_commands": install_cmds,
    }


def section_skills() -> list[dict]:
    """Section 1: Skill trending list."""
    queries = [
        "claude-code+skill+SKILL.md",
        "codex+skill+SKILL.md",
        "openclaw+skill",
    ]
    all_repos = {}
    for q in queries:
        items = gh_search(q, sort="stars", per_page=10)
        for item in items:
            fn = item["full_name"]
            if fn not in all_repos:
                all_repos[fn] = item
        time.sleep(1)  # rate limit courtesy

    results = []
    for fn, item in list(all_repos.items())[:10]:
        details = get_repo_details(fn)
        merged = {**item, **details}
        entry = build_entry(merged, len(results) + 1)
        results.append(entry)
        time.sleep(0.3)

    return results


def section_quant() -> list[dict]:
    """Section 2: Quant/algo trading projects."""
    queries = [
        "quantitative-trading+topic:quantitative-trading",
        "stock-prediction+topic:stock-prediction",
        "algo-trading+topic:algo-trading",
        "chatgpt+trading+finance",
        "fintech+llm+topic:llm",
    ]
    all_repos = {}
    for q in queries:
        items = gh_search(q, sort="updated", per_page=8)
        for item in items:
            fn = item["full_name"]
            if fn not in all_repos:
                all_repos[fn] = item
        time.sleep(1)

    filtered = {k: v for k, v in all_repos.items()
                if (v.get("stargazers_count") or 0) >= 10}
    sorted_repos = sorted(filtered.values(),
                          key=lambda x: x.get("stargazers_count", 0), reverse=True)[:8]

    results = []
    for item in sorted_repos:
        details = get_repo_details(item["full_name"])
        entry = build_entry({**item, **details}, len(results) + 1)
        results.append(entry)
        time.sleep(0.3)

    return results


def section_simulation3d() -> list[dict]:
    """Section 3: AI in 3D modeling and simulation."""
    queries = [
        "3d-reconstruction+topic:3d-reconstruction",
        "nerf+language:python",
        "gaussian-splatting+topic:gaussian-splatting",
        "mesh-generation+topic:mesh-generation",
        "ai+cfd+topic:cfd",
        "ai+cad+language:python",
    ]
    all_repos = {}
    for q in queries:
        items = gh_search(q, sort="stars", per_page=8)
        for item in items:
            fn = item["full_name"]
            if (item.get("stargazers_count") or 0) >= 50 and fn not in all_repos:
                all_repos[fn] = item
        time.sleep(1)

    sorted_repos = sorted(all_repos.values(),
                          key=lambda x: x.get("stargazers_count", 0), reverse=True)[:8]

    results = []
    for item in sorted_repos:
        details = get_repo_details(item["full_name"])
        entry = build_entry({**item, **details}, len(results) + 1)
        results.append(entry)
        time.sleep(0.3)

    return results


def section_ai_hot() -> list[dict]:
    """Section 4: AI/ML trending repos."""
    # GitHub Trending + AI topic search
    trending = gh_trending_weekly()

    results = []
    ai_keywords = {"ai", "llm", "gpt", "transformer", "diffusion", "gan",
                   "nlp", "computer-vision", "reinforcement-learning",
                   "deep-learning", "machine-learning", "agent", "langchain",
                   "rag", "embedding", "vector-db", "generative-ai", "openai"}

    for repo in trending:
        details = get_repo_details(repo["full_name"])
        if not details:
            continue
        topics = set(t.lower() for t in details.get("topics", []))
        desc_lower = (details.get("description") or "").lower()
        name_lower = details.get("name", "").lower()

        is_ai = bool(ai_keywords & topics)
        is_ai = is_ai or any(kw in desc_lower for kw in ai_keywords)
        is_ai = is_ai or any(kw in name_lower for kw in ai_keywords)
        is_ai = is_ai or details.get("language", "") in {"Python", "Jupyter Notebook", "Rust"}

        if is_ai and len(results) < 10:
            entry = build_entry({**repo, **details}, len(results) + 1)
            results.append(entry)
        time.sleep(0.2)

    # Fallback: AI topic search
    if len(results) < 8:
        items = gh_search("topic:ai+topic:llm", sort="stars", per_page=10)
        for item in items:
            fn = item["full_name"]
            if fn not in {r["full_name"] for r in results}:
                entry = build_entry(item, len(results) + 1)
                results.append(entry)
            if len(results) >= 10:
                break

    return results[:10]


def main():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    print(f"[{today}] Fetching weekly GitHub trends...")

    data = {
        "date": today,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sections": {},
    }

    print("  Section 1/4: Skills...")
    data["sections"]["skills"] = section_skills()
    print(f"    Got {len(data['sections']['skills'])} entries")

    print("  Section 2/4: Quant...")
    data["sections"]["quant"] = section_quant()
    print(f"    Got {len(data['sections']['quant'])} entries")

    print("  Section 3/4: 3D Simulation...")
    data["sections"]["simulation3d"] = section_simulation3d()
    print(f"    Got {len(data['sections']['simulation3d'])} entries")

    print("  Section 4/4: AI Hot...")
    data["sections"]["ai_hot"] = section_ai_hot()
    print(f"    Got {len(data['sections']['ai_hot'])} entries")

    # Write outputs
    base = Path("data")
    base.mkdir(parents=True, exist_ok=True)
    (base / "history").mkdir(exist_ok=True)

    # Latest
    latest_path = base / "weekly-latest.json"
    latest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Wrote {latest_path}")

    # History
    hist_path = base / "history" / f"{today}.json"
    hist_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Wrote {hist_path}")

    print("Done!")


if __name__ == "__main__":
    main()
