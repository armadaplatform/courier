import re

BRANCH_PATTERN = re.compile(r'^refs/heads/(.+)$')


class GitlabException(Exception):
    pass


def get_repo(hook_json):
    repo_url = hook_json['repository']['url']
    repo_ref = hook_json['ref']
    match = re.search(BRANCH_PATTERN, repo_ref)
    if not match:
        raise GitlabException('Unable to extract branch from: {repo_ref}.'.format(**locals()))
    repo_branch = match.group(1)
    return repo_url, repo_branch
