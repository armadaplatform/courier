import logging
import os

import source
from courier_common import HERMES_DIRECTORY


class HermesDirectorySource(source.Source):
    def __init__(self, source_dict):
        super(HermesDirectorySource, self).__init__(source_dict)
        if not self.destination_path:
            self.destination_path = self.subdirectory

    def _pull(self):
        subdirectory = '.'
        path = os.path.join(HERMES_DIRECTORY, subdirectory)
        logging.debug('HermesDirectorySource path: {}'.format(path))
        return path
