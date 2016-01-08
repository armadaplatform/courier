import logging
import os

import source
from courier_common import HERMES_DIRECTORY


class HermesDirectorySource(source.Source):
    def __init__(self, source_dict):
        super(HermesDirectorySource, self).__init__(source_dict)

    def _pull(self):
        # subdirectory = self.subdirectory or '.'  # TODO
        subdirectory = '.'
        path = os.path.join(HERMES_DIRECTORY, subdirectory)
        logging.debug('HermesDirectorySource path: {}'.format(path))
        return path
