import logging
import os

import destination


class Source(object):
    def __init__(self, source_dict):
        self.source_type = source_dict.get('type')
        self.subdirectory = source_dict.get('subdirectory')
        self.destinations = source_dict.get('destinations')
        self.destination_path = source_dict.get('destination_path')
        self.local_path = None
        self.were_errors = False

    def _pull(self):
        raise NotImplementedError()

    def __get_destination_instances(self):
        for destination_alias in self.destinations:
            destination_instances = destination.get_destinations_for_alias(destination_alias)
            for destination_instance in destination_instances:
                yield destination_instance

    def __rename_directory_if_different_from_destination_directory(self, local_path):
        """This is used to make local path match destination_directory to simplify rsync usage."""
        if self.subdirectory:
            pushed_path = os.path.join(local_path, self.subdirectory.strip('/'))
        else:
            pushed_path = local_path
        if not self.destination_path:
            self.destination_path = os.path.basename(local_path.rstrip(os.path.sep))
        dirname, basename = os.path.split(pushed_path)
        new_pushed_path = os.path.join(dirname, self.destination_path)
        logging.debug('pushed_path: {}  new_pushed_path: {}'.format(pushed_path, new_pushed_path))
        if pushed_path != new_pushed_path:
            os.rename(pushed_path, new_pushed_path)
        return new_pushed_path

    def update(self, override_destinations=None):
        self.local_path = self._pull()
        pushed_path = self.__rename_directory_if_different_from_destination_directory(self.local_path)
        destination_instances = override_destinations or self.__get_destination_instances()
        for destination_instance in destination_instances:
            destination_instance.push(pushed_path)
            self.were_errors |= destination_instance.were_errors

    def update_by_ssh(self, ssh_address, hermes_path):
        destination_dict = {
            'type': 'ssh',
            'address': ssh_address,
            'path': hermes_path
        }
        destination_instance = destination.Destination(destination_dict)
        self.update(override_destinations=[destination_instance])
