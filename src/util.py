import os

import time

COURIER_TEMP_DIR = '/tmp/courier-temp'


def create_temp_directory():
    unique_dir_name = '{0:.6f}'.format(time.time())
    local_path = os.path.join(COURIER_TEMP_DIR, unique_dir_name, '')
    return local_path
