import os

from courier_common import HERMES_DIRECTORY
import source


class HermesDirectorySource(source.Source):
    def __init__(self, source_dict):
        super(HermesDirectorySource, self).__init__(source_dict)

    def _pull(self):
        return os.path.join(HERMES_DIRECTORY, '.')
