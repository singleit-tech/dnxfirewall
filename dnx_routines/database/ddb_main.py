#!/usr/bin/env python3

from __future__ import annotations

import os
import traceback

from socket import socket, AF_UNIX, SOCK_DGRAM, SOL_SOCKET, SO_PASSCRED
from json import loads

from dnx_gentools.def_namedtuples import IPP_EVENT_LOG, DNS_REQUEST_LOG, IPS_EVENT_LOG, GEOLOCATION_LOG, INF_EVENT_LOG

from dnx_gentools.def_typing import *
from dnx_gentools.def_constants import *
from dnx_gentools.standard_tools import dnx_queue, looper

from dnx_iptools.protocol_tools import authenticate_sender

from dnx_routines.logging.log_client import Log
from dnx_routines.database.ddb_connector_sqlite import DBConnector

# NOTE: dynamic reference to namedtuples
NT_LOOKUP = {
    nt.__name__: nt for nt in [IPP_EVENT_LOG, DNS_REQUEST_LOG, IPS_EVENT_LOG, GEOLOCATION_LOG, INF_EVENT_LOG]
}.get

# ====================================================
# SERVICE SOCKET - Initialization
# ====================================================
if os.path.exists(DATABASE_SOCKET):
    os.remove(DATABASE_SOCKET)

_db_service = socket(AF_UNIX, SOCK_DGRAM)
_db_service.setsockopt(SOL_SOCKET, SO_PASSCRED, 1)

_db_service.bind(DATABASE_SOCKET.encode())

# NOTE: direct reference to the recvmsg method for perf
_db_service_recvmsg = _db_service.recvmsg

# =======================================
# PRIMARY FUNCTIONS - REDUCED FROM CLASS
# =======================================
# the main service loop to remove the recursive callback of queue handler.
def run() -> NoReturn:
    Log.notice('Database log entry processing queue ready.')

    fail_count = 0
    fail_time = fast_time()
    while True:
        # NOTE: this is blocking inside dnx_queue loop decorator on _write_to_database function.
        with DBConnector(Log) as database:
            _request_handler(database)

        fail_count += 1
        if (not fail_count % 5):
            new_time = fast_time()

            Log.critical(f'Database write failure count reached 5. {new_time-fail_time} seconds since last entry.')

            fail_time = new_time

        fast_sleep(ONE_SEC)

@dnx_queue(Log, name='Database')
def _request_handler(database: DBConnector, job: list) -> None:

    database.execute(*job)

    # NOTE: this might be wasteful
    database.commit_entries()

@looper(NO_DELAY, queue_for_db=_request_handler.add)
def receive_requests(queue_for_db: Callable[[tuple[str, str, str]], None]) -> None:
    '''receives databases messages plus ancillary authentication data from dnxfirewall mods.
    '''
    try:
        data, anc_data, *_ = _db_service_recvmsg(2048, 256)
    except OSError:
        traceback.print_exc()

    else:
        authorized = authenticate_sender(anc_data)

        # dropping message due to failed auth
        if (not authorized):
            return

        # not validating input because we don't accept unsolicited comms, enforced by unix socket authentication.
        # if there is malformed data from other dnx module, then it will be unrecoverable until a patch can be loaded.
        data = loads(data.decode())

        name = data['method']

        # NOTE: instead of pickle, using json then converting to a py object manually
        log_tuple = NT_LOOKUP(f'{name}_log'.upper())

        Log.debug(f'tuple reference retrieved: name->{name}, log_tuple->{log_tuple}')

        try:
            log_entry = log_tuple(*data['log'])
        except:
            Log.critical(f'routine lookup failure -> ({name})')

        else:
            queue_for_db((name, data['timestamp'], log_entry))
