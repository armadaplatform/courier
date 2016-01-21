import os
import shutil

import courier
import source
from courier_common import HERMES_DIRECTORY
from util import create_temp_directory


class HermesDirectorySource(source.Source):
    def __init__(self, source_dict):
        super(HermesDirectorySource, self).__init__(source_dict)
        if self.destination_path and not self.subdirectory:
            raise courier.CourierException('Field "destination_path" cannot be set if "subdirectory" is not set.')
        if not self.destination_path:
            self.destination_path = self.subdirectory

    def _pull(self):
        if self.subdirectory and self.destination_path:
            local_path = create_temp_directory()
            shutil.copytree(os.path.join(HERMES_DIRECTORY, self.subdirectory),
                            os.path.join(local_path, self.subdirectory))
        else:
            local_path = os.path.join(HERMES_DIRECTORY, '.')
        return local_path
