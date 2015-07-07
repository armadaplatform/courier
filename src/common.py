from __future__ import print_function
import os
import sys

import hermes


HERMES_DIRECTORY = '/tmp/hermes-directory'


def print_err(*objs):
    print(*objs, file=sys.stderr)


def get_ssh_key_path(filename, config_dir):
    if config_dir:
        ssh_key_path = os.path.join(config_dir, filename)
    else:
        ssh_key_path = hermes.get_config_file_path(filename)
    os.chmod(ssh_key_path, 0o600)
    return ssh_key_path
