from __future__ import print_function

import json
import logging
import os
import socket
import sys
import threading

import web
from armada import hermes

from raven.contrib.webpy import SentryApplication
from raven import Client, setup_logging
from raven.handlers.logging import SentryHandler


import git_source
import gitlab
import hermes_directory_source
from courier_common import get_ssh_key_path, HERMES_DIRECTORY

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
        logging.warning('sources_configs_keys is empty')
        return result, were_errors

    for source_config_key in sources_configs_keys:
        logging.debug('source_config_key: {}'.format(source_config_key))
        try:
            sources_dict = hermes.get_config(source_config_key)
            logging.debug('sources_dict: {}'.format(sources_dict))
            assert isinstance(sources_dict, list)
        except Exception as e:
            logging.exception(
                'Config {source_config_key} does not contain json with list of sources.'.format(**locals()))
            were_errors = True
            continue

        for source_dict in sources_dict:
            try:
                sources = list(_create_sources_from_dict(source_dict, sources_config_dir))
                logging.debug('adding sources: {}'.format(sources))
                result.extend(sources)
            except Exception as e:
                logging.exception('Invalid source configuration:\n{}'.format(source_dict))
                were_errors = True
    return result, were_errors


def _create_sources_from_git_repo(repo_url, repo_branch):
    result = []
    sources, were_errors = _create_all_sources()
    for source_instance in sources:
        logging.debug('source_instance: {}'.format(source_instance))
        if isinstance(source_instance, git_source.GitSource):
            logging.debug('recognized GitSource ({} {})'.format(source_instance.repo_url, source_instance.branch))
            if source_instance.repo_url == repo_url and source_instance.branch == repo_branch:
                result.append(source_instance)
    return result, were_errors


def _create_sources_from_hermes_directory(subdirectory=None):
    result = []
    sources, were_errors = _create_all_sources()
    for source_instance in sources:
        logging.debug('source_instance: {}'.format(source_instance))
        if isinstance(source_instance, hermes_directory_source.HermesDirectorySource):
            logging.debug('recognized HermesDirectorySource (subdirectory={})'.format(source_instance.subdirectory))
            if source_instance.subdirectory == subdirectory:
                result.append(source_instance)
    return result, were_errors


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
        except Exception as e:
            logging.exception('Update of source {source_instance} failed.'.format(**locals()))
            were_errors = True
        were_errors |= source_instance.were_errors
    return were_errors


def _update_list_of_sources(sources):
    were_errors = False
    for source_instance in sources:
        try:
            source_instance.update()
        except Exception as e:
            logging.exception('Update of source {source_instance} failed.'.format(**locals()))
            were_errors = True
        were_errors |= source_instance.were_errors
    return were_errors


def _update_all():
    sources, were_errors = _create_all_sources()
    were_errors |= _update_list_of_sources(sources)
    return were_errors


def _handle_errors(were_errors):
    if were_errors:
        web.ctx.status = '500 Internal Server Error'
        return 'There were errors. Check logs for details.'
    return 'ok'


class GitLabWebHook(object):
    def POST(self):
        were_errors = False
        json_data = json.loads(web.data())
        try:
            repo_url, repo_branch = gitlab.get_repo(json_data)
            logging.info('Gitlab web hook has triggered. Repository: {}. Branch: {}.'.format(repo_url, repo_branch))
            sources, were_errors = _create_sources_from_git_repo(repo_url, repo_branch)
            logging.info('sources: {sources}'.format(**locals()))
            were_errors |= _update_list_of_sources(sources)
        except gitlab.GitlabException as e:
            logging.exception('Unable to update from gitlab: {e}'.format(**locals()))
            were_errors = True
        return _handle_errors(were_errors)


class Health(object):
    def GET(self):
        return 'ok'


class UpdateFromGit(object):
    def POST(self):
        json_data = json.loads(web.data())
        url = json_data['url']
        branch = json_data['branch']
        logging.info('Update from git. Repository: {}. Branch: {}.'.format(url, branch))
        sources, were_errors = _create_sources_from_git_repo(url, branch)
        logging.info('sources: {sources}'.format(**locals()))
        were_errors |= _update_list_of_sources(sources)
        return _handle_errors(were_errors)


class UpdateFromHermesDirectory(object):
    def POST(self):
        json_data = json.loads(web.data() or '{}')
        subdirectory = json_data.get('subdirectory')
        logging.info('Update from hermes-directory. Subdirectory: {}'.format(subdirectory))
        sources, were_errors = _create_sources_from_hermes_directory(subdirectory)
        logging.info('sources: {sources}'.format(**locals()))
        were_errors |= _update_list_of_sources(sources)
        return _handle_errors(were_errors)


class UpdateAll(object):
    def POST(self):
        logging.info('Update all.')
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
            logging.info('Update hermes client: ssh={} path={}.'.format(hermes_ssh, hermes_path))
            were_errors |= _update_hermes_client(hermes_ssh, hermes_path)
        except Exception as e:
            logging.exception('Unable to update hermes')

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


def _set_up_logger(sentry_client):
    config = hermes.get_config('config.json', {})
    log_level_from_config = str(config.get('log_level')).upper()
    log_level = getattr(logging, log_level_from_config, logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s %(name)s [%(levelname)s] - %(message)s')

    handler = SentryHandler(sentry_client, level=logging.WARNING)
    setup_logging(handler)


web.config.debug = False


def main():
    tags = {
        "environment": os.environ.get('MICROSERVICE_ENV')
    }
    client = Client(hermes.get_config('config.json', {}).get('sentry-url', ''), auto_log_stacks=True, tags=tags)
    _set_up_logger(client)

    thread = threading.Thread(target=_update_all)
    thread.start()

    urls = (
        '/gitlab_web_hook', GitLabWebHook.__name__,
        '/health', Health.__name__,
        '/update_from_git', UpdateFromGit.__name__,
        '/update_from_hermes_directory', UpdateFromHermesDirectory.__name__,
        '/update_all', UpdateAll.__name__,
        '/hermes_address', HermesAddress.__name__,
        '/update_hermes', UpdateHermes.__name__,
        '/', Index.__name__,
    )
    app = SentryApplication(client, logging=True, mapping=urls, fvars=globals())

    app.run()


if __name__ == '__main__':
    main()
