#!/usr/bin/env python3
"""
Cleanup script for E2E test artifacts.

Removes:
- Branches matching e2e-test-* pattern
- PRs with titles starting with "E2E"
- Stale lock branches (*-branch-deploy-lock)

Usage:
    python scripts/cleanup-e2e.py                    # Dry run (shows what would be deleted)
    python scripts/cleanup-e2e.py --execute         # Actually delete
    python scripts/cleanup-e2e.py --execute --all   # Delete ALL e2e artifacts (including closed PRs)
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx


def get_github_client() -> httpx.Client:
    """Create authenticated GitHub API client."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("❌ GITHUB_TOKEN environment variable required")
        sys.exit(1)
    
    return httpx.Client(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30.0,
    )


def get_repo() -> str:
    """Get repo from environment or git config."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo:
        return repo
    
    # Try to get from git remote
    try:
        import subprocess
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Handle ssh and https URLs
            if url.startswith("git@"):
                # git@github.com:owner/repo.git
                return url.split(":")[1].replace(".git", "")
            elif "github.com" in url:
                # https://github.com/owner/repo.git
                parts = url.split("/")
                return f"{parts[-2]}/{parts[-1].replace('.git', '')}"
    except Exception:
        pass
    
    print("❌ Could not determine repository. Set GITHUB_REPOSITORY env var.")
    sys.exit(1)


def list_branches(client: httpx.Client, repo: str, pattern: str) -> list[str]:
    """List branches matching pattern."""
    branches = []
    page = 1
    
    while True:
        resp = client.get(f"/repos/{repo}/branches", params={"per_page": 100, "page": page})
        resp.raise_for_status()
        data = resp.json()
        
        if not data:
            break
        
        for branch in data:
            name = branch["name"]
            if pattern in name:
                branches.append(name)
        
        page += 1
    
    return branches


def list_prs(client: httpx.Client, repo: str, state: str = "open") -> list[dict]:
    """List PRs with E2E in title."""
    prs = []
    page = 1
    
    while True:
        resp = client.get(
            f"/repos/{repo}/pulls",
            params={"state": state, "per_page": 100, "page": page},
        )
        resp.raise_for_status()
        data = resp.json()
        
        if not data:
            break
        
        for pr in data:
            title = pr["title"]
            if title.startswith("E2E") or "e2e-test-" in pr["head"]["ref"]:
                prs.append({
                    "number": pr["number"],
                    "title": title,
                    "state": pr["state"],
                    "branch": pr["head"]["ref"],
                })
        
        page += 1
    
    return prs


def delete_branch(client: httpx.Client, repo: str, branch: str) -> bool:
    """Delete a branch."""
    resp = client.delete(f"/repos/{repo}/git/refs/heads/{branch}")
    return resp.status_code == 204


def close_pr(client: httpx.Client, repo: str, pr_number: int) -> bool:
    """Close a PR."""
    resp = client.patch(
        f"/repos/{repo}/pulls/{pr_number}",
        json={"state": "closed"},
    )
    return resp.status_code == 200


def main():
    parser = argparse.ArgumentParser(description="Cleanup E2E test artifacts")
    parser.add_argument("--execute", action="store_true", help="Actually delete (default is dry run)")
    parser.add_argument("--all", action="store_true", help="Include closed PRs/merged branches")
    args = parser.parse_args()
    
    client = get_github_client()
    repo = get_repo()
    
    print(f"🔍 Scanning repository: {repo}")
    print(f"📋 Mode: {'EXECUTE' if args.execute else 'DRY RUN'}\n")
    
    # Find e2e test branches
    e2e_branches = list_branches(client, repo, "e2e-test-")
    lock_branches = list_branches(client, repo, "-branch-deploy-lock")
    
    # Find e2e PRs
    open_prs = list_prs(client, repo, "open")
    closed_prs = list_prs(client, repo, "closed") if args.all else []
    
    # Summary
    print("=" * 60)
    print("ARTIFACTS FOUND")
    print("=" * 60)
    
    print(f"\n📌 E2E Test Branches ({len(e2e_branches)}):")
    for b in e2e_branches[:10]:
        print(f"   - {b}")
    if len(e2e_branches) > 10:
        print(f"   ... and {len(e2e_branches) - 10} more")
    
    print(f"\n🔒 Lock Branches ({len(lock_branches)}):")
    for b in lock_branches[:10]:
        print(f"   - {b}")
    if len(lock_branches) > 10:
        print(f"   ... and {len(lock_branches) - 10} more")
    
    print(f"\n📝 Open E2E PRs ({len(open_prs)}):")
    for pr in open_prs[:10]:
        print(f"   - #{pr['number']}: {pr['title'][:50]}")
    if len(open_prs) > 10:
        print(f"   ... and {len(open_prs) - 10} more")
    
    if args.all and closed_prs:
        print(f"\n📦 Closed E2E PRs ({len(closed_prs)}):")
        for pr in closed_prs[:5]:
            print(f"   - #{pr['number']}: {pr['title'][:50]}")
        if len(closed_prs) > 5:
            print(f"   ... and {len(closed_prs) - 5} more")
    
    total = len(e2e_branches) + len(lock_branches) + len(open_prs) + len(closed_prs)
    print(f"\n📊 Total artifacts: {total}")
    
    if not args.execute:
        print("\n⚠️  DRY RUN - No changes made")
        print("   Run with --execute to actually delete artifacts")
        return
    
    # Execute cleanup
    print("\n" + "=" * 60)
    print("EXECUTING CLEANUP")
    print("=" * 60)
    
    # Close open PRs first
    for pr in open_prs:
        print(f"   Closing PR #{pr['number']}...", end=" ")
        if close_pr(client, repo, pr["number"]):
            print("✅")
        else:
            print("❌")
    
    # Delete branches
    all_branches = e2e_branches + lock_branches
    for branch in all_branches:
        print(f"   Deleting branch {branch}...", end=" ")
        if delete_branch(client, repo, branch):
            print("✅")
        else:
            print("❌ (may already be deleted)")
    
    print(f"\n✨ Cleanup complete!")


if __name__ == "__main__":
    main()
