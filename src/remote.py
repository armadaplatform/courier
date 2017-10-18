import logging
import os
import random
import signal
import subprocess
import time
import traceback

import requests


class RemoteException(Exception):
    pass


class RemoteConnection(object):
    def get_address(self):
        raise NotImplementedError()

    def start(self):
        pass

    def terminate(self):
        pass


class DirectConnection(RemoteConnection):
    def __init__(self, address):
        self.address = address

    def get_address(self):
        return self.address


class SSHTunnelConnection(RemoteConnection):
    def __init__(self, address, ssh_tunnel):
        self.address = address
        self.ssh_tunnel = ssh_tunnel
        self.process = None
        self.pid = None
        self.host = None
        self.port = None

    def get_address(self):
        if self.host is None or self.port is None:
            raise RemoteException('SSH tunnel has not been initialized.')
        return '{}:{}'.format(self.host, self.port)

    def __address_to_host_and_port(self):
        return (self.address.split(':', 1) + [80])[:2]

    def _check_tunnel(self):
        pass

    def start(self):
        remote_host, remote_port = self.__address_to_host_and_port()
        self.process = self.__create_ssh_tunnel(
            self.ssh_tunnel['host'],
            self.ssh_tunnel['port'],
            self.ssh_tunnel['user'],
            self.ssh_tunnel['ssh_key_path'],
            remote_host,
            remote_port,
        )
        self.pid = self.process.pid
        try:
            self._check_tunnel()
        except Exception as e:
            logging.exception('Failed checking SSH tunnel')
            self.terminate()
            raise e

    def terminate(self):
        try:
            os.killpg(self.pid, signal.SIGTERM)
        except:
            logging.exception('Failed while terminating SSH tunnel')

    def __create_ssh_tunnel(self, host, port, user, ssh_key_path, remote_host, remote_port):
        bind_port = random.randrange(10000, 65535)
        self.host = '127.0.0.1'
        self.port = bind_port
        tunnel_command = ('ssh -i {ssh_key_path} -p {port} {user}@{host} -N -o StrictHostKeyChecking=no '
                          '-L *:{bind_port}:{remote_host}:{remote_port}').format(**locals())
        logging.debug('tunnel_command: {}'.format(tunnel_command))
        return _async_execute_local_command(tunnel_command)


class SSHOverSSHTunnelConnection(SSHTunnelConnection):
    TUNNEL_CHECK_RETRIES = 7
    TUNNEL_CHECK_TIMEOUT = 3
    SLEEP_BETWEEN_RETRIES = 1

    def __init__(self, address, ssh_tunnel, target_ssh_connection_dict):
        super(SSHOverSSHTunnelConnection, self).__init__(address, ssh_tunnel)
        self.target_ssh_connection_dict = target_ssh_connection_dict

    def _check_tunnel(self):
        check_tunnel_params = dict(self.target_ssh_connection_dict)
        check_tunnel_params['host'] = self.host
        check_tunnel_params['port'] = self.port
        check_tunnel_params['tunnel_check_timeout'] = self.TUNNEL_CHECK_TIMEOUT
        check_tunnel_command = ('ssh -o StrictHostKeyChecking=no -o ConnectTimeout={tunnel_check_timeout} '
                                '-p {port} -i {ssh_key_path} {user}@{host} true').format(**check_tunnel_params)
        logging.debug('check_tunnel_command: {}'.format(check_tunnel_command))
        for i in range(self.TUNNEL_CHECK_RETRIES + 1):
            check_tunnel_result = execute_local_command(check_tunnel_command)
            if check_tunnel_result[0] == 0:
                return
            time.sleep(self.SLEEP_BETWEEN_RETRIES)
        raise RemoteException(
            'Could not set up a SSHOverSSHTunnel to {}, all retries failed.'.format(self.address))


class HTTPOverSSHTunnelConnection(SSHTunnelConnection):
    TUNNEL_CHECK_RETRIES = 7
    TUNNEL_CHECK_TIMEOUT = 3
    SLEEP_BETWEEN_RETRIES = 1

    def __init__(self, address, ssh_tunnel, health_check_url=''):
        super(HTTPOverSSHTunnelConnection, self).__init__(address, ssh_tunnel)
        self.health_check_url = health_check_url

    def _check_tunnel(self):
        for i in range(self.TUNNEL_CHECK_RETRIES + 1):
            try:
                headers = {'Host': self.address}
                url = 'http://{}:{}{}'.format(self.host, self.port, self.health_check_url)
                response = requests.get(url, headers=headers, timeout=self.TUNNEL_CHECK_TIMEOUT)
                if response.status_code == requests.codes.ok:
                    return
            except:
                pass
            time.sleep(self.SLEEP_BETWEEN_RETRIES)
        raise RemoteException(
            'Could not set up an HTTPOverSSHTunnel to {}, all retries failed.'.format(self.address))


def create_remote_connection_to_http(address, ssh_tunnel=None, health_check_url=''):
    if ssh_tunnel:
        return HTTPOverSSHTunnelConnection(address, ssh_tunnel, health_check_url)
    return DirectConnection(address)


def create_remote_connection_to_ssh(address, ssh_tunnel, target_ssh_connection_dict):
    if ssh_tunnel:
        return SSHOverSSHTunnelConnection(address, ssh_tunnel, target_ssh_connection_dict)
    return DirectConnection(address)


def _async_execute_local_command(command):
    p = subprocess.Popen(
        command,
        shell=True,
        preexec_fn=os.setsid
    )
    return p


def execute_local_command(command):
    p = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True
    )
    out, err = p.communicate()
    return p.returncode, out, err


def push_local_path_to_remote(local_path, rsync_ssh_dict):
    rsync_ssh_dict['local_path'] = local_path
    if rsync_ssh_dict.get('sudo'):
        rsync_ssh_dict['sudo'] = "--rsync-path='sudo rsync'"
    else:
        rsync_ssh_dict['sudo'] = ''
    rsync_command = ('rsync -cvrz --delete --exclude=".git*" '
                     '--rsh="ssh -o StrictHostKeyChecking=no -p {port} -i {ssh_key_path}" '
                     '{sudo} {local_path} {user}@{host}:{path} ').format(**rsync_ssh_dict)
    result = execute_local_command(rsync_command)
    return result
