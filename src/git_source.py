from __future__ import print_function

import os
import re
import shutil
import urllib

import remote
import source
from util import create_temp_directory


class GitException(Exception):
    pass


GIT_SSH_SCRIPTS_DIR = '/tmp/courier-git-ssh-scripts'
REPO_NAME_PATTERN = re.compile(r'/([\w.\-]+)\.git$')


class GitSource(source.Source):
    def __init__(self, source_dict, repo_url, ssh_key_path, branch='master'):
        super(GitSource, self).__init__(source_dict)
        self.repo_url = repo_url
        self.repo_name = REPO_NAME_PATTERN.search(self.repo_url).group(1)
        self.ssh_key_path = ssh_key_path
        self.branch = branch

    def update(self, override_destinations=None):
        super(GitSource, self).update(override_destinations)
        shutil.rmtree(self.local_path)

    def _pull(self):
        git_ssh_script_name = urllib.quote(self.ssh_key_path, '') + '.sh'  # Create unique filename.
        git_ssh_script_path = os.path.join(GIT_SSH_SCRIPTS_DIR, git_ssh_script_name)
        if not os.path.exists(git_ssh_script_path):
            if not os.path.exists(GIT_SSH_SCRIPTS_DIR):
                os.makedirs(GIT_SSH_SCRIPTS_DIR)
            git_ssh_command = 'ssh -i {self.ssh_key_path} -o StrictHostKeyChecking=no $@ '.format(**locals())
            with open(git_ssh_script_path, 'w') as git_ssh_script_file:
                git_ssh_script_file.write(git_ssh_command)
            os.chmod(git_ssh_script_path, 0o755)

        local_path = create_temp_directory()
        clone_command = ('mkdir -p {local_path} && cd {local_path} && '
                         'GIT_SSH={git_ssh_script_path} '
                         'git clone -b {self.branch} --depth=1 {self.repo_url}').format(**locals())
        return_code, return_out, return_err = remote.execute_local_command(clone_command)
        if return_code != 0:
            raise GitException('Error on fetching from git: {return_err}'.format(**locals()))
        return os.path.join(local_path, self.repo_name)
