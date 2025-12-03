"""
Context Fetcher for Iterative Investigation

Fetches files, log excerpts, and git history as requested by LLM.
"""
import logging
import os
import subprocess
import urllib.request
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ContextFetcher:
    """
    Fetches requested context (files, logs, git history) for LLM investigation
    """

    def __init__(self, repo_root: str, max_file_size: int = 100000,
                 github_repo: Optional[str] = None, commit_sha: Optional[str] = None):
        """
        Initialize context fetcher

        Args:
            repo_root: Root directory of git repository
            max_file_size: Maximum file size in bytes to fetch
            github_repo: GitHub repository (e.g., "Apra-Labs/ApraPipes")
            commit_sha: Current commit SHA for fetching from GitHub
        """
        self.repo_root = Path(repo_root)
        self.max_file_size = max_file_size
        self.github_repo = github_repo
        self.commit_sha = commit_sha

    def fetch_requests(self, requests: List[Dict]) -> List[Dict]:
        """
        Fetch all requested context items

        Args:
            requests: List of request dicts from LLM

        Returns:
            List of fulfilled requests with content
        """
        results = []

        for req in requests:
            req_type = req.get('type')
            target = req.get('target')
            reason = req.get('reason', '')

            logger.info(f"Fetching {req_type}: {target} (reason: {reason})")

            if req_type == 'file':
                result = self._fetch_file(target, reason)
            elif req_type == 'github_raw':
                result = self._fetch_github_raw(target, reason)
            elif req_type == 'log_excerpt':
                result = self._fetch_log_excerpt(target, reason)
            elif req_type == 'git_log':
                result = self._fetch_git_log(target, reason)
            else:
                result = {
                    'type': req_type,
                    'target': target,
                    'reason': reason,
                    'status': 'error',
                    'content': f"Unknown request type: {req_type}"
                }

            results.append(result)

        return results

    def _fetch_file(self, filepath: str, reason: str) -> Dict:
        """
        Fetch file content from repository

        Args:
            filepath: Relative path to file
            reason: Why LLM needs this file

        Returns:
            Dict with file content or error
        """
        full_path = self.repo_root / filepath

        # Security check - prevent path traversal
        try:
            full_path = full_path.resolve()
            if not str(full_path).startswith(str(self.repo_root.resolve())):
                return {
                    'type': 'file',
                    'target': filepath,
                    'reason': reason,
                    'status': 'error',
                    'content': f"Security error: Path outside repository"
                }
        except Exception as e:
            return {
                'type': 'file',
                'target': filepath,
                'reason': reason,
                'status': 'error',
                'content': f"Path resolution error: {e}"
            }

        # Check if file exists
        if not full_path.exists():
            return {
                'type': 'file',
                'target': filepath,
                'reason': reason,
                'status': 'not_found',
                'content': f"File not found: {filepath}"
            }

        # Check file size
        file_size = full_path.stat().st_size
        if file_size > self.max_file_size:
            return {
                'type': 'file',
                'target': filepath,
                'reason': reason,
                'status': 'too_large',
                'content': f"File too large: {file_size} bytes (max: {self.max_file_size})\n" +
                          f"Consider requesting specific line ranges or excerpts."
            }

        # Read file
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            return {
                'type': 'file',
                'target': filepath,
                'reason': reason,
                'status': 'success',
                'content': content,
                'metadata': {
                    'size_bytes': file_size,
                    'lines': len(content.splitlines())
                }
            }
        except Exception as e:
            return {
                'type': 'file',
                'target': filepath,
                'reason': reason,
                'status': 'error',
                'content': f"Error reading file: {e}"
            }

    def _fetch_github_raw(self, url_or_path: str, reason: str) -> Dict:
        """
        Fetch file from GitHub raw URL

        Args:
            url_or_path: Full GitHub raw URL or just the file path
            reason: Why LLM needs this file

        Returns:
            Dict with file content or error
        """
        # If it's just a path, construct the full URL
        if not url_or_path.startswith('http'):
            if not self.github_repo or not self.commit_sha:
                return {
                    'type': 'github_raw',
                    'target': url_or_path,
                    'reason': reason,
                    'status': 'error',
                    'content': 'GitHub repo or commit SHA not configured'
                }
            url = f"https://raw.githubusercontent.com/{self.github_repo}/{self.commit_sha}/{url_or_path}"
        else:
            url = url_or_path

        try:
            logger.info(f"Fetching from GitHub: {url}")

            # Fetch with timeout
            with urllib.request.urlopen(url, timeout=10) as response:
                content = response.read().decode('utf-8')

            return {
                'type': 'github_raw',
                'target': url_or_path,
                'reason': reason,
                'status': 'success',
                'content': content,
                'metadata': {
                    'url': url,
                    'size_bytes': len(content),
                    'lines': len(content.splitlines())
                }
            }
        except urllib.error.HTTPError as e:
            return {
                'type': 'github_raw',
                'target': url_or_path,
                'reason': reason,
                'status': 'not_found' if e.code == 404 else 'error',
                'content': f"HTTP {e.code}: {e.reason}"
            }
        except Exception as e:
            return {
                'type': 'github_raw',
                'target': url_or_path,
                'reason': reason,
                'status': 'error',
                'content': f"Error fetching from GitHub: {e}"
            }

    def _fetch_log_excerpt(self, search_term: str, reason: str) -> Dict:
        """
        Fetch excerpt from build log based on search term

        Args:
            search_term: Keyword to search for in log
            reason: Why LLM needs this excerpt

        Returns:
            Dict with log excerpt or error
        """
        # For now, return placeholder
        # In real implementation, this would search the full build log
        return {
            'type': 'log_excerpt',
            'target': search_term,
            'reason': reason,
            'status': 'not_implemented',
            'content': f"Log excerpt search not yet implemented. Search term: {search_term}"
        }

    def _fetch_git_log(self, target: str, reason: str) -> Dict:
        """
        Fetch git commit history

        Args:
            target: 'all' or specific file path
            reason: Why LLM needs this history

        Returns:
            Dict with git log or error
        """
        try:
            if target == 'all':
                # Get last 10 commits
                cmd = ['git', 'log', '--oneline', '-10']
            else:
                # Get last 5 commits for specific file
                cmd = ['git', 'log', '--oneline', '-5', '--', target]

            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                return {
                    'type': 'git_log',
                    'target': target,
                    'reason': reason,
                    'status': 'success',
                    'content': result.stdout
                }
            else:
                return {
                    'type': 'git_log',
                    'target': target,
                    'reason': reason,
                    'status': 'error',
                    'content': f"Git command failed: {result.stderr}"
                }

        except Exception as e:
            return {
                'type': 'git_log',
                'target': target,
                'reason': reason,
                'status': 'error',
                'content': f"Error fetching git log: {e}"
            }

    def format_fulfilled_requests(self, fulfilled_requests: List[Dict]) -> str:
        """
        Format fulfilled requests for LLM prompt

        Args:
            fulfilled_requests: List of fulfilled request dicts

        Returns:
            Formatted string for prompt
        """
        if not fulfilled_requests:
            return "*(No previous requests)*"

        sections = []

        for i, req in enumerate(fulfilled_requests, 1):
            req_type = req['type']
            target = req['target']
            status = req['status']
            content = req['content']

            section = f"### Request {i}: {req_type.title()} - `{target}`\n\n"
            section += f"**Reason:** {req.get('reason', 'N/A')}\n"
            section += f"**Status:** {status}\n\n"

            if status == 'success':
                # Add metadata if available
                if 'metadata' in req:
                    meta = req['metadata']
                    section += f"**Metadata:** {meta}\n\n"

                section += f"**Content:**\n```\n{content}\n```\n"
            else:
                section += f"**Error:** {content}\n"

            sections.append(section)

        return "\n".join(sections)
