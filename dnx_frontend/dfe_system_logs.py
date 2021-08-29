#!/usr/bin/python3

import os, sys

HOME_DIR = os.environ['HOME_DIR']
sys.path.insert(0, HOME_DIR)

from dnx_configure.dnx_file_operations import tail_file
from dnx_configure.dnx_system_info import System

def load_page(uri_query):
    file_path = f'{HOME_DIR}/dnx_system/log/combined'

    log_files = [f'{file_path}/{file}' for file in reversed(os.listdir(file_path)[-7:])]

    return get_log_entries(log_files), 'combined', None

def update_page(form):
    log_type = form.get('table', 'combined')

    # ternary to handle initial page load.
    # TODO: this should be done better, but i am waitint until reports page gets converted to ajax to support both
    log_type = 'combined' if log_type == 'default' else log_type

    if (log_type in ['combined', 'dhcp_server', 'dns_proxy', 'ip_proxy', 'ips', 'syslog', 'system', 'web_app', 'logins']):
        file_path = f'{HOME_DIR}/dnx_system/log/{log_type}'

        log_files = [f'{file_path}/{file}' for file in reversed(os.listdir(file_path)[-7:])]

    # returning none to fill the table_args var on the calling funtion to allow for reusablity with the reports page method
    # TODO: this should potentially be wrapped in error handling at main.
        # error will raise if table key is in form, but type is not in allowed list.
    return get_log_entries(log_files), log_type, None

# TODO: make front end logging 4 fields. date/time, service, level, entry. this will make the presentation nicer
# and will still allow for service identification on the combined system log.
    # NOTE: it looks like not all long entries, especially debug have the service identified in the log currently.
    # would probably be a good idea to just use the log/service name defined in module so each entry does not need
    # to worry about it.
def get_log_entries(log_files):
    combined_log = []
    total_lines, line_limit = 0, 100
    for file in log_files:
        if (file.endswith('temp')): continue

        log_entries = tail_file(file, line_count=100)
        for line in log_entries:

            # skipping over empty lines.
            if not line.strip('\n'): continue

            total_lines += 1
            if total_lines >= line_limit: break

            epoch, *log_entry = line.split('|', 3)
            date_time = System.calculate_time_offset(int(epoch))
            date_time = System.format_log_time(date_time)

            combined_log.append((date_time, *log_entry))

    return combined_log
