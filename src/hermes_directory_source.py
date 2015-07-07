import os

import source
import common


class HermesDirectorySource(source.Source):
    def __init__(self, source_dict):
        super(HermesDirectorySource, self).__init__(source_dict)

    def _pull(self):
        return os.path.join(common.HERMES_DIRECTORY, '.')

