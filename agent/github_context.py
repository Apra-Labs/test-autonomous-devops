"""
GitHub Context Fetcher

Fetches GitHub workflow run details, job annotations, and workflow files
to provide rich context for LLM analysis.
"""
import logging
import os
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class GitHubContextFetcher:
    """
    Fetches GitHub-specific context: job annotations, workflow files, run details
    """

    def __init__(self, github_token: str, github_repo: str, run_id: str = None):
        """
        Initialize GitHub context fetcher

        Args:
            github_token: GitHub API token
            github_repo: Repository in format "owner/repo"
            run_id: Workflow run ID
        """
        self.github_token = github_token
        self.github_repo = github_repo
        self.run_id = run_id
        self.github = None

        # Initialize PyGithub if we have credentials
        if github_token and github_repo:
            try:
                from github import Github
                self.github = Github(github_token)
                self.repo = self.github.get_repo(github_repo)
                logger.info(f"GitHub context fetcher initialized for {github_repo}")
            except Exception as e:
                logger.warning(f"Could not initialize GitHub API: {e}")

    def fetch_job_annotations(self, build_flavor: str = None) -> Dict:
        """
        Fetch job annotations (errors, warnings) from GitHub Actions

        Args:
            build_flavor: Build flavor to identify which job failed

        Returns:
            Dict with annotations and job details
        """
        if not self.github or not self.run_id:
            return {
                'status': 'unavailable',
                'reason': 'GitHub API not initialized or no run_id provided',
                'annotations': []
            }

        try:
            # Get workflow run
            run = self.repo.get_workflow_run(int(self.run_id))

            # Get all jobs in the run
            jobs = run.jobs()

            # Find the job that matches build_flavor (if provided)
            target_job = None
            all_jobs_info = []

            for job in jobs:
                job_info = {
                    'name': job.name,
                    'status': job.status,
                    'conclusion': job.conclusion,
                    'id': job.id
                }
                all_jobs_info.append(job_info)

                # Match by build flavor in job name
                if build_flavor and build_flavor.lower() in job.name.lower():
                    target_job = job
                # If no flavor specified, pick first failed job
                elif not build_flavor and job.conclusion == 'failure' and not target_job:
                    target_job = job

            if not target_job:
                return {
                    'status': 'no_failed_job',
                    'reason': f'No failed job found for flavor: {build_flavor}',
                    'all_jobs': all_jobs_info,
                    'annotations': []
                }

            # Fetch annotations using GitHub API
            # Note: PyGithub doesn't have direct annotation support, use REST API
            import requests

            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }

            # Get check runs for this job
            # GitHub uses check runs to store annotations
            check_runs_url = f"https://api.github.com/repos/{self.github_repo}/commits/{run.head_sha}/check-runs"
            response = requests.get(check_runs_url, headers=headers)
            response.raise_for_status()

            check_runs_data = response.json()

            # Find check run matching our job
            annotations = []
            for check_run in check_runs_data.get('check_runs', []):
                if check_run['name'] == target_job.name:
                    # Get annotations for this check run
                    annotations_url = check_run['url'] + '/annotations'
                    ann_response = requests.get(annotations_url, headers=headers)
                    ann_response.raise_for_status()
                    annotations = ann_response.json()
                    break

            return {
                'status': 'success',
                'job_name': target_job.name,
                'job_conclusion': target_job.conclusion,
                'job_id': target_job.id,
                'annotations': annotations,
                'annotation_count': len(annotations),
                'all_jobs': all_jobs_info
            }

        except Exception as e:
            logger.error(f"Error fetching job annotations: {e}", exc_info=True)
            return {
                'status': 'error',
                'error': str(e),
                'annotations': []
            }

    def fetch_job_logs(self, build_flavor: str = None) -> Dict:
        """
        Fetch raw logs from failed job

        Args:
            build_flavor: Build flavor to identify which job failed

        Returns:
            Dict with job logs
        """
        if not self.github or not self.run_id:
            return {
                'status': 'unavailable',
                'reason': 'GitHub API not initialized or no run_id provided',
                'logs': ''
            }

        try:
            # Get workflow run
            run = self.repo.get_workflow_run(int(self.run_id))

            # Get all jobs in the run
            jobs = run.jobs()

            # Find the job that matches build_flavor
            target_job = None
            for job in jobs:
                if build_flavor and build_flavor.lower() in job.name.lower():
                    target_job = job
                    break
                elif not build_flavor and job.conclusion == 'failure':
                    target_job = job
                    break

            if not target_job:
                return {
                    'status': 'no_failed_job',
                    'reason': f'No failed job found for flavor: {build_flavor}',
                    'logs': ''
                }

            # Fetch logs using GitHub API
            import requests

            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }

            logs_url = f"https://api.github.com/repos/{self.github_repo}/actions/jobs/{target_job.id}/logs"
            response = requests.get(logs_url, headers=headers, allow_redirects=True)
            response.raise_for_status()

            logs = response.text

            # Extract error annotations from logs (lines with ##[error])
            error_lines = []
            for line in logs.split('\n'):
                if '##[error]' in line or '##[warning]' in line:
                    error_lines.append(line)

            return {
                'status': 'success',
                'job_name': target_job.name,
                'job_id': target_job.id,
                'logs_size': len(logs),
                'error_annotations': error_lines,
                'error_count': len(error_lines),
                'full_logs': logs  # Include full logs for context
            }

        except Exception as e:
            logger.error(f"Error fetching job logs: {e}", exc_info=True)
            return {
                'status': 'error',
                'error': str(e),
                'logs': ''
            }

    def fetch_workflow_files(self, workflow_name: str) -> Dict:
        """
        Fetch workflow YAML files for context

        Args:
            workflow_name: Name of the workflow (e.g., "CI-Win-NoCUDA")

        Returns:
            Dict with workflow file contents
        """
        if not self.github:
            # Fall back to local file reading
            return self._fetch_workflow_files_local(workflow_name)

        try:
            # Fetch from GitHub repository
            workflow_files = {}

            # Try to find the main CI workflow file
            ci_workflow_path = f".github/workflows/{workflow_name}.yml"
            try:
                ci_file = self.repo.get_contents(ci_workflow_path)
                workflow_files['ci_workflow'] = {
                    'path': ci_workflow_path,
                    'content': ci_file.decoded_content.decode('utf-8')
                }
            except Exception as e:
                logger.warning(f"Could not fetch {ci_workflow_path}: {e}")

            # Try to find reusable workflow files (common patterns)
            # Look for build-test-*.yml files
            reusable_patterns = [
                'build-test-win.yml',
                'build-test-lin.yml',
                'build-test-linux.yml',
                'autonomous-autofix.yml'
            ]

            for pattern in reusable_patterns:
                workflow_path = f".github/workflows/{pattern}"
                try:
                    workflow_file = self.repo.get_contents(workflow_path)
                    workflow_files[pattern.replace('.yml', '')] = {
                        'path': workflow_path,
                        'content': workflow_file.decoded_content.decode('utf-8')
                    }
                except:
                    pass  # File doesn't exist, skip

            return {
                'status': 'success' if workflow_files else 'not_found',
                'workflow_files': workflow_files,
                'file_count': len(workflow_files)
            }

        except Exception as e:
            logger.error(f"Error fetching workflow files: {e}", exc_info=True)
            # Fall back to local
            return self._fetch_workflow_files_local(workflow_name)

    def _fetch_workflow_files_local(self, workflow_name: str) -> Dict:
        """
        Fetch workflow files from local filesystem

        Args:
            workflow_name: Name of the workflow

        Returns:
            Dict with workflow file contents
        """
        workflow_files = {}
        workflows_dir = Path('.github/workflows')

        if not workflows_dir.exists():
            return {
                'status': 'not_found',
                'reason': 'Workflows directory not found',
                'workflow_files': {}
            }

        # Try to find the main CI workflow file
        ci_workflow_path = workflows_dir / f"{workflow_name}.yml"
        if ci_workflow_path.exists():
            workflow_files['ci_workflow'] = {
                'path': str(ci_workflow_path),
                'content': ci_workflow_path.read_text()
            }

        # Try to find reusable workflow files
        reusable_patterns = [
            'build-test-win.yml',
            'build-test-lin.yml',
            'build-test-linux.yml',
            'autonomous-autofix.yml'
        ]

        for pattern in reusable_patterns:
            workflow_path = workflows_dir / pattern
            if workflow_path.exists():
                workflow_files[pattern.replace('.yml', '')] = {
                    'path': str(workflow_path),
                    'content': workflow_path.read_text()
                }

        return {
            'status': 'success' if workflow_files else 'not_found',
            'workflow_files': workflow_files,
            'file_count': len(workflow_files)
        }

    def format_annotations_for_prompt(self, annotations_data: Dict) -> str:
        """
        Format annotations into human-readable text for LLM prompt

        Args:
            annotations_data: Result from fetch_job_annotations()

        Returns:
            Formatted string
        """
        if annotations_data['status'] != 'success':
            return f"*Annotations unavailable: {annotations_data.get('reason', 'unknown')}*"

        output = f"**Job:** {annotations_data['job_name']}\n"
        output += f"**Conclusion:** {annotations_data['job_conclusion']}\n"
        output += f"**Annotation Count:** {annotations_data['annotation_count']}\n\n"

        if not annotations_data['annotations']:
            output += "*No annotations found*\n"
            return output

        output += "**Annotations:**\n\n"
        for i, ann in enumerate(annotations_data['annotations'], 1):
            output += f"{i}. **{ann.get('annotation_level', 'unknown').upper()}**"
            if 'path' in ann:
                output += f" in `{ann['path']}`"
                if 'start_line' in ann:
                    output += f":{ann['start_line']}"
            output += f"\n   {ann.get('message', 'No message')}\n\n"

        return output

    def format_error_lines_for_prompt(self, logs_data: Dict) -> str:
        """
        Format error lines from logs for LLM prompt

        Args:
            logs_data: Result from fetch_job_logs()

        Returns:
            Formatted string with GitHub error annotations
        """
        if logs_data['status'] != 'success':
            return f"*Job logs unavailable: {logs_data.get('reason', 'unknown')}*"

        if not logs_data.get('error_annotations'):
            return "*No error annotations found in logs*"

        output = f"**Job:** {logs_data['job_name']}\n"
        output += f"**Error Count:** {logs_data['error_count']}\n\n"
        output += "**GitHub Annotations (Errors/Warnings):**\n\n```\n"

        # Show first 20 error lines
        for line in logs_data['error_annotations'][:20]:
            output += line + "\n"

        if logs_data['error_count'] > 20:
            output += f"\n... ({logs_data['error_count'] - 20} more errors)\n"

        output += "```\n"

        return output

    def format_workflow_files_for_prompt(self, workflow_data: Dict) -> str:
        """
        Format workflow files for LLM prompt

        Args:
            workflow_data: Result from fetch_workflow_files()

        Returns:
            Formatted string
        """
        if workflow_data['status'] != 'success':
            return f"*Workflow files unavailable: {workflow_data.get('reason', 'unknown')}*"

        output = f"**Workflow Files ({workflow_data['file_count']} files):**\n\n"

        for name, file_info in workflow_data['workflow_files'].items():
            output += f"### {name}\n"
            output += f"**Path:** `{file_info['path']}`\n\n"
            output += "```yaml\n"
            output += file_info['content']
            output += "\n```\n\n"

        return output
