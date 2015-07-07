from __future__ import print_function
import json

import requests

from common import print_err


SHIP_IP = '172.17.42.1'


def do_query(query):
    url = 'http://{hostname}:8500/v1/{query}'.format(hostname=SHIP_IP, query=query)
    return json.loads(requests.get(url).text)


def _create_dict_from_tags(tags):
    if not tags:
        return {}
    return dict((tag.split(':', 1) + [None])[:2] for tag in tags)


def discover(service_name=None, env=None):
    service_to_addresses = {}
    if service_name:
        service_names = [service_name]
    else:
        service_names = list(do_query('catalog/services').keys())
    for service_name in service_names:
        try:
            query = 'health/service/{service_name}'.format(service_name=service_name)
            instances = do_query(query)
        except (TypeError, ValueError) as exception:
            exception_class = type(exception).__name__
            print_err("Query to consul failed health/service/{service_name}. "
                      "Error: {exception_class} - {exception}".format(**locals()))
            continue
        for instance in instances:
            service_checks_statuses = (check['Status'] for check in instance['Checks'])
            if any(status == 'critical' for status in service_checks_statuses):
                continue

            service_tags = instance['Service']['Tags']
            service_tags_dict = _create_dict_from_tags(service_tags)

            service_ip = instance['Node']['Address']
            service_port = instance['Service']['Port']
            service_address = '{service_ip}:{service_port}'.format(
                service_ip=service_ip, service_port=service_port)

            service_env = service_tags_dict.get('env') or None
            if env and env != service_env:
                continue
            service_app_id = service_tags_dict.get('app_id') or None
            service_index = (service_name, service_env, service_app_id)
            if service_index not in service_to_addresses:
                service_to_addresses[service_index] = []
            service_to_addresses[service_index].append(service_address)
    return service_to_addresses
