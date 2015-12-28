from __future__ import print_function
import logging
import os
import json
import traceback
import sys

import requests

import hermes
from courier_common import get_ssh_key_path
import remote

sys.path.append('/opt/microservice/src')
import common.consul


class DestinationException(Exception):
    pass


def _get_remote_hermes_address(service_address, override_host_in_header=None):
    headers = None
    if override_host_in_header is not None:
        headers = {'Host': override_host_in_header}
    url = 'http://{}/hermes_address'.format(service_address)
    response = requests.get(url, headers=headers)
    if response.status_code == requests.codes.ok:
        return json.loads(response.text)
    raise DestinationException('Could not get ssh address from: {url}. '
                               'HTTP code: {response.status_code}\n'
                               'Response:\n{response.text}'.format(**locals()))


def get_destinations_for_alias(destination_alias):
    destination_dicts = hermes.get_config('destinations.json')
    if destination_dicts is None:
        raise DestinationException('Could not find destinations.json.')
    if destination_alias not in destination_dicts:
        logging.error('Destination alias {0} is not defined in destinations.json.'.format(destination_alias))
        return []
    destination_config_dir = os.path.dirname(hermes.get_config_file_path('destinations.json'))
    if isinstance(destination_dicts[destination_alias], dict):
        return [Destination(destination_dicts[destination_alias], destination_config_dir)]
    elif isinstance(destination_dicts[destination_alias], list):
        result = []
        for destination_dict in destination_dicts[destination_alias]:
            result.append(Destination(destination_dict, destination_config_dir))
        return result
    else:
        logging.error('Destination definition for alias {0} is neither list nor dict.'.format(destination_alias))
    return []


class Destination(object):
    DEFAULT_COURIER_SSH_CONFIG = {
        'user': 'docker',
        'key': 'keys/docker@armada.key',
        'sudo': True,
    }

    def __init__(self, destination_dict, destination_config_dir=''):
        self.destination_dict = dict(destination_dict)
        if self.destination_dict['type'] in ('armada-local', 'courier-remote', 'ssh'):
            temp = dict(self.DEFAULT_COURIER_SSH_CONFIG)
            temp.update(self.destination_dict.get('ssh') or {})
            self.destination_dict['ssh'] = temp
        self.destination_config_dir = destination_config_dir
        self.were_errors = False

    def __set_ssh_key_path(self, remote_address):
        remote_address['ssh_key_path'] = get_ssh_key_path(remote_address['key'], self.destination_config_dir)

    def __get_ssh_tunnel(self):
        if 'ssh-tunnel' not in self.destination_dict:
            return None
        result = dict(self.destination_dict['ssh-tunnel'])
        self.__set_ssh_key_path(result)
        return result

    def __get_hermes_address_from_remote_courier(self):
        remote_connection = remote.create_remote_connection_to_http(
            self.destination_dict['address'],
            self.__get_ssh_tunnel(),
            health_check_url='/health',
        )
        try:
            remote_connection.start()
            courier_address = remote_connection.get_address()
            return _get_remote_hermes_address(courier_address, override_host_in_header=self.destination_dict['address'])
        finally:
            remote_connection.terminate()

    @staticmethod
    def __get_armada_addresses():
        ship_ip = common.consul._get_ship_ip()
        url = 'http://{}:8900/list?microservice_name=armada'.format(ship_ip)
        armada_services = requests.get(url, timeout=7).json()
        addresses = [service['address'] for service in armada_services['result']]
        return addresses

    def __get_destination_addresses(self):
        destination_type = self.destination_dict['type']
        if destination_type == 'armada-local':
            service_addresses = self.__get_armada_addresses()
            for service_address in service_addresses:
                try:
                    hermes_address = _get_remote_hermes_address(service_address)
                    yield hermes_address
                except:
                    traceback.print_exc()
                    self.were_errors = True
        elif destination_type == 'courier-remote':
            try:
                yield self.__get_hermes_address_from_remote_courier()
            except:
                traceback.print_exc()
                self.were_errors = True
        elif destination_type == 'ssh':
            yield {'ssh': self.destination_dict['address'], 'path': self.destination_dict['path']}
        else:
            raise DestinationException('Unsupported destination type: {destination_type}'.format(**locals()))

    def __push_to_one_hermes_address(self, local_path, hermes_address):
        self.destination_dict['ssh']['path'] = hermes_address['path']
        logging.info('Rsyncing path: {} to: {}.'.format(local_path, self.destination_dict))
        rsync_ssh_dict = dict(self.destination_dict['ssh'])
        self.__set_ssh_key_path(rsync_ssh_dict)
        remote_connection = remote.create_remote_connection_to_ssh(
            hermes_address['ssh'],
            self.__get_ssh_tunnel(),
            target_ssh_connection_dict=rsync_ssh_dict,
        )
        return_code = None
        try:
            remote_connection.start()
            rsync_address = remote_connection.get_address()
            rsync_host, rsync_port = rsync_address.split(':', 1)
            rsync_ssh_dict['host'] = rsync_host
            rsync_ssh_dict['port'] = rsync_port
            return_code, return_out, return_err = remote.push_local_path_to_remote(
                local_path,
                rsync_ssh_dict,
            )
            logging.info(
                'Rsync result:\n'
                'exit_code={return_code}\n'
                'stdout:\n{return_out}\n'
                'stderr:\n{return_err}\n'.format(**locals()))
        finally:
            remote_connection.terminate()

        if return_code == 0:
            logging.info('Rsync successful.')
        else:
            logging.error('Rsync failed.')
            self.were_errors = True

    def __update_remote_courier(self):
        remote_connection = remote.create_remote_connection_to_http(
            self.destination_dict['address'],
            self.__get_ssh_tunnel(),
            health_check_url='/health',
        )
        try:
            remote_connection.start()
            courier_address = remote_connection.get_address()
            logging.info('Remote Courier address for update: {}'.format(courier_address))
            url = 'http://{}/update_all'.format(courier_address)
            headers = {'Host': self.destination_dict['address']}
            response = requests.post(url, headers=headers)
            if response.status_code != requests.codes.ok:
                logging.error('Could not execute /update_all on remote Courier: {url}.\n'
                              'HTTP code: {response.status_code}\n'
                              'Response:\n{response.text}'.format(**locals()))
                self.were_errors = True
        finally:
            remote_connection.terminate()

    def push(self, local_path):
        try:
            for hermes_address in self.__get_destination_addresses():
                try:
                    self.__push_to_one_hermes_address(local_path, hermes_address)
                except:
                    traceback.print_exc()
                    self.were_errors = True
            if self.destination_dict['type'] == 'courier-remote':
                self.__update_remote_courier()
        except:
            traceback.print_exc()
            self.were_errors = True
