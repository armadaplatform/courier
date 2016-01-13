import os

import courier
import source
from courier_common import HERMES_DIRECTORY


class HermesDirectorySource(source.Source):
    def __init__(self, source_dict):
        super(HermesDirectorySource, self).__init__(source_dict)
        if self.destination_path and not self.subdirectory:
            raise courier.CourierException('Field "destination_path" cannot be set if "subdirectory" is not set.')
        if not self.destination_path:
            self.destination_path = self.subdirectory

    def _pull(self):
        return os.path.join(HERMES_DIRECTORY, '.')
