from __future__ import print_function
import json
import os
import socket
import threading
import traceback
import sys

import web

from courier_common import get_ssh_key_path, print_err, HERMES_DIRECTORY
import gitlab
import git_source
import hermes_directory_source
import hermes

sys.path.append('/opt/microservice/src')
import common.consul
import common.docker_client


class CourierException(Exception):
    pass


def _create_sources_from_dict(source_dict, sources_config_dir):
    source_type = source_dict.get('type')
    if source_type == 'git':
        repositories = source_dict['repositories']
        if len(repositories) > 1 and 'destination_path' in source_dict:
            raise CourierException('You cannot set the same destination_path for more than 1 '
                                   'repository.')
        ssh_key_path = get_ssh_key_path(source_dict['ssh_key'], sources_config_dir)
        branch = source_dict.get('branch', 'master')
        del source_dict['repositories']
        for repo_url in repositories:
            source_dict['repository'] = repo_url
            yield git_source.GitSource(source_dict, repo_url, ssh_key_path, branch)
    elif source_type == 'hermes-directory':
        yield hermes_directory_source.HermesDirectorySource(source_dict)
    else:
        raise CourierException('Unknown source type: {source_type}'.format(**locals()))


def _create_all_sources():
    sources_config_dir = hermes.get_config_file_path('sources')
    sources_configs_keys = hermes.get_configs_keys('sources')
    result = []
    were_errors = False
    if not sources_configs_keys:
        return result, were_errors

    for source_config_key in sources_configs_keys:
        try:
            sources_dict = hermes.get_config(source_config_key)
            assert isinstance(sources_dict, list)
        except:
            print_err(
                'Config {source_config_key} does not contain json with list of sources.'.format(**locals()))
            traceback.print_exc()
            were_errors = True
            continue

        for source_dict in sources_dict:
            try:
                result.extend(_create_sources_from_dict(source_dict, sources_config_dir))
            except:
                traceback.print_exc()
                were_errors = True
    return result, were_errors


def _create_sources_from_git_repo(repo_url, repo_branch):
    for source_instance in _create_all_sources():
        if isinstance(source_instance, git_source.GitSource):
            if source_instance.repo_url == repo_url and source_instance.branch == repo_branch:
                yield source_instance


def _get_local_ssh_address():
    docker_inspect = common.docker_client.get_docker_inspect(socket.gethostname())
    ssh_port = docker_inspect['NetworkSettings']['Ports']['22/tcp'][0]['HostPort']
    agent_self_dict = common.consul.consul_query('agent/self')
    ip = agent_self_dict['Config']['AdvertiseAddr']
    return '{ip}:{ssh_port}'.format(**locals())


def _update_hermes_client(ssh_address, hermes_path):
    sources, were_errors = _create_all_sources()
    for source_instance in sources:
        try:
            source_instance.update_by_ssh(ssh_address, hermes_path)
        except:
            print_err('Update of source {source_instance} failed.'.format(**locals()))
            traceback.print_exc()
            were_errors = True
    return were_errors


def _update_list_of_sources(sources):
    were_errors = False
    for source_instance in sources:
        try:
            source_instance.update()
        except:
            print_err('Update of source {source_instance} failed.'.format(**locals()))
            traceback.print_exc()
            were_errors = True
    return were_errors


def _update_all():
    sources, were_errors = _create_all_sources()
    if _update_list_of_sources(sources):
        were_errors = True
    return were_errors


def _handle_errors(were_errors):
    if were_errors:
        web.ctx.status = 500
        return 'There were errors. Check logs for details.'
    return 'ok'


class GitLabWebHook(object):
    def POST(self):

        json_data = json.loads(web.data())
        try:
            repo_url, repo_branch = gitlab.get_repo(json_data)
            print_err('Gitlab web hook has triggered. Repository: {}. Branch: {}.'.format(repo_url, repo_branch))
            sources = list(_create_sources_from_git_repo(repo_url, repo_branch))
            print_err('sources: {sources}'.format(**locals()))
            _update_list_of_sources(sources)
        except gitlab.GitlabException as e:
            print_err('Unable to update from gitlab: {e}'.format(**locals()))


class Health(object):
    def GET(self):
        return 'ok'


class UpdateFromGit(object):
    def POST(self):
        json_data = json.loads(web.data())
        url = json_data['url']
        branch = json_data['branch']
        print_err('Update from git. Repository: {}. Branch: {}.'.format(url, branch))
        sources = list(_create_sources_from_git_repo(url, branch))
        print_err('sources: {sources}'.format(**locals()))
        were_errors = _update_list_of_sources(sources)
        return _handle_errors(were_errors)


class UpdateAll(object):
    def POST(self):
        print_err('Update all.')
        were_errors = _update_all()
        return _handle_errors(were_errors)


class HermesAddress(object):
    def GET(self):
        hermes_address = {'ssh': _get_local_ssh_address(), 'path': HERMES_DIRECTORY}
        return json.dumps(hermes_address)


class UpdateHermes(object):
    def POST(self):
        were_errors = False
        try:
            post_data = json.loads(web.data())
            hermes_ssh = post_data.get('ssh')
            hermes_path = post_data.get('path')
            print_err('Update hermes client: ssh={} path={}.'.format(hermes_ssh, hermes_path))
            if _update_hermes_client(hermes_ssh, hermes_path):
                were_errors = True
        except:
            were_errors = True
        return _handle_errors(were_errors)


class Index(object):
    def GET(self):
        return ('Welcome to courier.\n'
                'env={}\n'
                'app_id={}\n').format(
            os.environ.get('MICROSERVICE_ENV'),
            os.environ.get('MICROSERVICE_APP_ID')
        )


def main():
    thread = threading.Thread(target=_update_all)
    thread.start()

    urls = (
        '/gitlab_web_hook', GitLabWebHook.__name__,
        '/health', Health.__name__,
        '/update_from_git', UpdateFromGit.__name__,
        '/update_all', UpdateAll.__name__,
        '/hermes_address', HermesAddress.__name__,
        '/update_hermes', UpdateHermes.__name__,
        '/', Index.__name__,
    )
    app = web.application(urls, globals())
    app.run()


if __name__ == '__main__':
    main()
