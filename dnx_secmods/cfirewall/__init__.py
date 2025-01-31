#!/usr/bin/env python3

from __future__ import annotations

from dnx_gentools.def_constants import hardout, INITIALIZE_MODULE

LOG_NAME = 'cfirewall'

def print_help():
    print('<[ CFIREWALL ARGUMENT LIST ]>')
    print('h, help               print argument list to the terminal')
    print('v, verbose            print operational messages to the terminal')
    print('vv, verbose2          print near excessive amounts of debug messages to the terminal')
    print('fw                    enables fw module specific output to terminal (use with v or vv)')
    print('nat                   enables nat module specific output to terminal (use with v or vv)')


if INITIALIZE_MODULE(LOG_NAME):
    import os

    from threading import Thread
    from dataclasses import dataclass

    from dnx_gentools.def_constants import MSB, LSB
    from dnx_gentools.def_enums import Queue, QueueType
    from dnx_gentools.signature_operations import generate_geolocation

    from dnx_routines.logging.log_client import Log

    from fw_main import CFirewall, initialize_geolocation
    from fw_automate import FirewallAutomate


    @dataclass
    class Args:
        h:  int = 0
        v:  int = 0
        vv: int = 0

        help:     int = 0
        verbose:  int = 0
        verbose2: int = 0

        fw:  int = 0
        nat: int = 0

        @property
        def help_set(self):
            return self.h or self.help

        @property
        def verbose_set(self):
            return self.v or self.verbose

        @property
        def verbose2_set(self):
            return self.vv or self.verbose2

        @property
        def fw_set(self):
            return (self.v or self.vv) and self.fw

        @property
        def nat_set(self):
            return (self.v or self.vv) and self.nat

    try:
        args = Args(**{a: 1 for a in os.environ['PASSTHROUGH_ARGS'].split(',') if a})
    except Exception as E:
        hardout(f'DNXFIREWALL arg parse failure => {E}')

    else:
        if (args.help_set):
            print_help()

            hardout()

    Log.run(name=LOG_NAME)

def run():
    # ===============
    # GEOLOCATION
    # ===============
    # generating py_trie for geolocation signatures, cfirewall will initialize the extension natively
    geo_trie = generate_geolocation(Log)

    initialize_geolocation(geo_trie, MSB, LSB)

    dnx_threads = []
    # ===============
    # FIREWALL QUEUE
    # ===============
    dnxfirewall = CFirewall()

    # NOTE: bypass tells the process to invoke rule action (DROP or ACCEPT) without forwarding to security modules.
    dnxfirewall.set_options(args.verbose_set, args.verbose2_set, args.fw_set, args.nat_set)

    error = dnxfirewall.nf_set(QueueType.FIREWALL, Queue.CFIREWALL)
    if (error):
        Log.error(f'failed to set nl socket options for queue {Queue.CFIREWALL}')
        hardout()

    dnx_threads.append(Thread(target=dnxfirewall.nf_run))

    # ===============
    # NAT QUEUE
    # ===============
    # TODO: TSHOOT AND FULLY IMPLEMENT NAT MODULE TO REPLACE IPTABLES
    # dnxnat = CFirewall()
    # dnxnat.set_options(0, args.verbose_set, args.verbose2_set)

    # error = dnxnat.nf_set(QueueType.NAT, Queue.CNAT)
    # if (error):
    #     Log.error(f'failed to set nl socket options for queue {Queue.CNAT}')
    #     hardout()

    # dnx_threads.append(Thread(target=dnxnat.nf_run))

    # initializing python processes for detecting configuration changes to zone or firewall rule sets and also handles
    # necessary calls into Cython via cfirewall reference for making the actual config change.
    # these will run in Python threads with a potential calling into Cython.
    # these functions should be explicitly identified since they will require the gil to be acquired on the Cython side
    # or else the Python interpreter will crash.
    fw_rule_monitor = FirewallAutomate(Log, cfirewall=dnxfirewall)
    try:
        fw_rule_monitor.run()
    except Exception as E:
        hardout(f'DNXFIREWALL control run failure => {E}')

    if (args.verbose2_set):
        fw_rule_monitor.print_active_rules()

    # this is running in pure C. the GIL is released before running the low-level system operations and will never
    # reacquire the gil.
    for t in dnx_threads:
        t.start()

    try:
        for t in dnx_threads:
            t.join()
    except Exception as E:
        # dnxfirewall.nf_break() TODO: why did we remove the teardown? was it unnecessary?
        hardout(f'DNXFIREWALL cfirewall/nfqueue failure => {E}')
