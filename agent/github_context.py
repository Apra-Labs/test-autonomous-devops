"""
GitHub Context Fetcher

Fetches GitHub workflow run details, job annotations, and workflow files
to provide rich context for LLM analysis.
"""
import logging
import os
import subprocess
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Workflow file mapping: determines which workflow files to fetch based on the main workflow
WORKFLOW_FILE_MAP = {
    'CI-Win-NoCUDA': ['CI-Win-NoCUDA.yml', 'build-test-win.yml'],
    'CI-Win-CUDA': ['CI-Win-CUDA.yml', 'build-test-win.yml'],
    'CI-Linux-NoCUDA': ['CI-Linux-NoCUDA.yml', 'build-test-lin.yml'],
    'CI-Linux-CUDA': ['CI-Linux-CUDA.yml', 'build-test-lin.yml'],
    'CI-Linux-CUDA-Docker': ['CI-Linux-CUDA-Docker.yml', 'build-test-lin-container.yml'],
    'CI-Linux-ARM64': ['CI-Linux-ARM64.yml', 'build-test-lin.yml'],
    'CI-Jetson': ['CI-Jetson.yml', 'build-test-lin.yml'],
}


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
        Fetch raw logs from failed job using gh CLI

        Args:
            build_flavor: Build flavor to identify which job failed

        Returns:
            Dict with job logs and error annotations
        """
        if not self.run_id:
            return {
                'status': 'unavailable',
                'reason': 'No run_id provided',
                'logs': '',
                'error_annotations': [],
                'error_count': 0
            }

        try:
            # Use gh CLI to get job logs - simpler and already authenticated
            # Get the list of jobs for this run
            list_cmd = ['gh', 'run', 'view', self.run_id, '--json', 'jobs', '--jq', '.jobs[] | select(.conclusion=="failure") | .name + "|" + (.databaseId|tostring)']

            result = subprocess.run(
                list_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                logger.warning(f"gh CLI failed: {result.stderr}")
                return {
                    'status': 'error',
                    'error': f'gh CLI failed: {result.stderr}',
                    'logs': '',
                    'error_annotations': [],
                    'error_count': 0
                }

            # Parse job list - format: "job-name|job-id"
            failed_jobs = result.stdout.strip().split('\n') if result.stdout.strip() else []

            if not failed_jobs:
                return {
                    'status': 'no_failed_job',
                    'reason': f'No failed jobs found for run {self.run_id}',
                    'logs': '',
                    'error_annotations': [],
                    'error_count': 0
                }

            # Find job matching build_flavor
            target_job_id = None
            target_job_name = None

            for job_line in failed_jobs:
                if '|' not in job_line:
                    continue
                job_name, job_id = job_line.split('|', 1)

                # Match by build flavor in job name
                if build_flavor and build_flavor.lower() in job_name.lower():
                    target_job_id = job_id
                    target_job_name = job_name
                    break
                # If no flavor specified, pick first failed job
                elif not build_flavor and not target_job_id:
                    target_job_id = job_id
                    target_job_name = job_name

            if not target_job_id:
                return {
                    'status': 'no_matching_job',
                    'reason': f'No failed job found matching flavor: {build_flavor}',
                    'all_failed_jobs': [j.split('|')[0] for j in failed_jobs if '|' in j],
                    'logs': '',
                    'error_annotations': [],
                    'error_count': 0
                }

            # Fetch logs for this job using gh CLI
            log_cmd = ['gh', 'run', 'view', '--job', target_job_id, '--log']

            log_result = subprocess.run(
                log_cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if log_result.returncode != 0:
                return {
                    'status': 'error',
                    'error': f'Failed to fetch logs: {log_result.stderr}',
                    'logs': '',
                    'error_annotations': [],
                    'error_count': 0
                }

            logs = log_result.stdout

            # Extract error annotations from logs with step names
            # Track current step using ##[debug]Starting: step-name markers
            error_lines = []
            current_step = "UNKNOWN STEP"

            for line in logs.split('\n'):
                # Track step transitions
                if '##[debug]Starting:' in line:
                    # Extract step name from "##[debug]Starting: Step Name"
                    parts = line.split('##[debug]Starting:', 1)
                    if len(parts) == 2:
                        current_step = parts[1].strip()

                # Capture errors/warnings with current step name
                if '##[error]' in line or '##[warning]' in line:
                    # Replace "UNKNOWN STEP" in the line with actual step name
                    if '\tUNKNOWN STEP\t' in line and current_step != "UNKNOWN STEP":
                        line = line.replace('\tUNKNOWN STEP\t', f'\t{current_step}\t', 1)
                    error_lines.append(line.strip())

            return {
                'status': 'success',
                'job_name': target_job_name,
                'job_id': target_job_id,
                'logs_size': len(logs),
                'error_annotations': error_lines,
                'error_count': len(error_lines),
                'full_logs': logs  # Include full logs for context
            }

        except subprocess.TimeoutExpired:
            return {
                'status': 'error',
                'error': 'Timeout fetching job logs',
                'logs': '',
                'error_annotations': [],
                'error_count': 0
            }
        except Exception as e:
            logger.error(f"Error fetching job logs: {e}", exc_info=True)
            return {
                'status': 'error',
                'error': str(e),
                'logs': '',
                'error_annotations': [],
                'error_count': 0
            }

    def fetch_job_logs_old(self, build_flavor: str = None) -> Dict:
        """
        OLD METHOD: Fetch raw logs from failed job using PyGithub
        Keeping for reference, but prefer gh CLI method above

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
        Fetch ONLY relevant workflow YAML files for context using workflow map

        Args:
            workflow_name: Name of the workflow (e.g., "CI-Win-NoCUDA")

        Returns:
            Dict with workflow file contents (only relevant files)
        """
        # Use workflow map to determine which files to fetch
        files_to_fetch = WORKFLOW_FILE_MAP.get(workflow_name, [workflow_name + '.yml'])

        logger.info(f"Fetching workflow files for {workflow_name}: {files_to_fetch}")

        if not self.github:
            # Fall back to local file reading
            return self._fetch_workflow_files_local_mapped(workflow_name, files_to_fetch)

        try:
            # Fetch from GitHub repository
            workflow_files = {}

            for filename in files_to_fetch:
                workflow_path = f".github/workflows/{filename}"
                try:
                    workflow_file = self.repo.get_contents(workflow_path)
                    workflow_files[filename.replace('.yml', '')] = {
                        'path': workflow_path,
                        'content': workflow_file.decoded_content.decode('utf-8')
                    }
                    logger.info(f"Fetched {workflow_path}")
                except Exception as e:
                    logger.warning(f"Could not fetch {workflow_path}: {e}")

            return {
                'status': 'success' if workflow_files else 'not_found',
                'workflow_files': workflow_files,
                'file_count': len(workflow_files)
            }

        except Exception as e:
            logger.error(f"Error fetching workflow files: {e}", exc_info=True)
            # Fall back to local
            return self._fetch_workflow_files_local_mapped(workflow_name, files_to_fetch)

    def _fetch_workflow_files_local_mapped(self, workflow_name: str, files_to_fetch: List[str]) -> Dict:
        """
        Fetch workflow files from local filesystem using workflow map

        Args:
            workflow_name: Name of the workflow
            files_to_fetch: List of filenames to fetch

        Returns:
            Dict with workflow file contents (only requested files)
        """
        workflow_files = {}
        workflows_dir = Path('.github/workflows')

        if not workflows_dir.exists():
            return {
                'status': 'not_found',
                'reason': 'Workflows directory not found',
                'workflow_files': {}
            }

        for filename in files_to_fetch:
            workflow_path = workflows_dir / filename
            if workflow_path.exists():
                workflow_files[filename.replace('.yml', '')] = {
                    'path': str(workflow_path),
                    'content': workflow_path.read_text()
                }
                logger.info(f"Loaded {filename} from local filesystem")
            else:
                logger.warning(f"Workflow file not found: {filename}")

        return {
            'status': 'success' if workflow_files else 'not_found',
            'workflow_files': workflow_files,
            'file_count': len(workflow_files)
        }

    def _fetch_workflow_files_local(self, workflow_name: str) -> Dict:
        """
        OLD METHOD: Fetch workflow files from local filesystem
        Keeping for backward compatibility

        Args:
            workflow_name: Name of the workflow

        Returns:
            Dict with workflow file contents
        """
        files_to_fetch = WORKFLOW_FILE_MAP.get(workflow_name, [workflow_name + '.yml'])
        return self._fetch_workflow_files_local_mapped(workflow_name, files_to_fetch)

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
