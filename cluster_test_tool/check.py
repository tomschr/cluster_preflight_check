
import re
from . import utils


def check_environment():
    print("============Checking environment============")
    check_my_hostname_resolves()
    check_time_service()
    check_watchdog()
    print()
    #check_firewall()


def check_my_hostname_resolves():
    task = utils.TaskInfo("Checking hostname resolvable")

    hostname = utils.this_node()
    try:
        import socket
        socket.gethostbyname(hostname)
    except socket.error:
        task.error_append('''Hostname "{}" is unresolvable.
         {}'''.format(hostname, "Please add an entry to /etc/hosts or configure DNS."))
    finally:
        task.print_result()


def check_time_service():
    task = utils.TaskInfo("Checking time service")

    timekeepers = ('chronyd.service', 'ntp.service', 'ntpd.service')
    timekeeper = None
    for tk in timekeepers:
        if utils.service_is_available(tk):
            timekeeper = tk
            break

    if timekeeper is None:
        task.warn_append("No NTP service found.")
    else:
        task.info_append("{} is available".format(timekeeper))
        if utils.service_is_enabled(timekeeper):
            task.info_append("{} is enabled".format(timekeeper))
        else:
            task.warn_append("{} is disabled".format(timekeeper))

        if utils.service_is_active(timekeeper):
            task.info_append("{} is active".format(timekeeper))
        else:
            task.warn_append("{} is not active".format(timekeeper))

    task.print_result()


def check_watchdog():
    """
    Verify watchdog device. Fall back to /dev/watchdog.
    """
    task = utils.TaskInfo("Checking watchdog")

    watchdog_dev = utils.detect_watchdog_device()
    rc, _, _ = utils.run_cmd('lsmod | egrep "(wd|dog)"')
    if rc != 0:
        task.warn_append("Watchdog device must be configured if want to use SBD!")
    task.print_result()


def check_cluster():
    print("============Checking cluster state============")
    check_cluster_service()
    check_fencing()
    check_nodes()
    check_resources()
    print()


def check_cluster_service():
    task = utils.TaskInfo("Checking cluster service")
    for s in ("corosync", "pacemaker"):
        if utils.service_is_active(s):
            task.info_append("{} service is running".format(s))
        else:
            task.error_append("{} service is not running!".format(s))
    task.print_result()


def check_fencing():
    task = utils.TaskInfo("Checking Stonith/Fence")

    if utils.is_fence_enabled():
        task.info_append("stonith-enabled is \"true\"")
    else:
        task.warn_append("stonith is disabled")

    use_sbd = False
    rc, outp, _ = utils.run_cmd("crm_mon -r1 | grep '(stonith:.*):'")
    if rc == 0:
        res = re.search(r'([^\s]+)\s+\(stonith:(.*)\):\s+(.*)\s', outp)
        res_name, res_agent, res_state = res.groups()
        common_msg = "stonith resource {}({})".format(res_name, res_agent)
        state_msg = "{} is {}".format(common_msg, res_state)

        task.info_append("{} is configured".format(common_msg))
        if res_state == "Started":
            task.info_append(state_msg)
        else:
            task.warn_append(state_msg)

        if re.search(r'sbd$', res_agent):
            use_sbd = True
    else:
        task.warn_append("No stonith resource configured!")

    if use_sbd:
        if utils.service_is_active("sbd"):
            task.info_append("sbd service is running")
        else:
            task.warn_append("sbd service is not running!")

    task.print_result()


def check_nodes():
    task = utils.TaskInfo("Checking nodes")

    cmd_awk = """awk '$1=="Current"||$1=="Online:"||$1=="OFFLINE:"||$3=="UNCLEAN"{print $0}'"""
    cmd = r'crm_mon -r1 | {}'.format(cmd_awk)
    rc, outp, errp = utils.run_cmd(cmd)
    if rc == 0:
        # check DC
        res = re.search(r'Current DC: (.*) \(', outp)
        task.info_append("DC node: {}".format(res.group(1)))

        # check quorum
        if re.search(r'partition with quorum', outp):
            task.info_append("Cluster have quorum")
        else:
            task.warn_append("Cluster lost quorum!")

        # check Online nodes
        res = re.search(r'Online:\s+(\[.*\])', outp)
        task.info_append("Online nodes: {}".format(res.group(1)))

        # check OFFLINE nodes
        res = re.search(r'OFFLINE:\s+(\[.*\])', outp)
        if res:
            task.warn_append("OFFLINE nodes: {}".format(res.group(1)))

        # check UNCLEAN nodes
        for line in outp.split('\n'):
            res = re.search(r'Node (.*): UNCLEAN', line)
            if res:
                task.warn_append('Node {} is UNCLEAN!'.format(res.group(1)))
    else:
        task.error_append("run \"{}\" error: {}".format(cmd, errp))

    task.print_result()


def check_resources():
    task = utils.TaskInfo("Checking resources")

    awk_stop = """awk '$3=="Stopped"||$0~/FAILED/{print $0}' | wc -l"""
    awk_start = """awk '$3=="Started"{print $0}' | wc -l"""
    cmd_stop = "crm_mon -r1 | {}".format(awk_stop)
    cmd_start = "crm_mon -r1 | {}".format(awk_start)

    rc, outp, errp = utils.run_cmd(cmd_stop)
    if rc == 0:
        task.info_append("Stopped/FAILED resources: {}".format(outp))
    else:
        task.error_append("run \"{}\" error: {}".format(cmd_stop, errp))

    rc, outp, errp = utils.run_cmd(cmd_start)
    if rc == 0:
        task.info_append("Started resources: {}".format(outp))
    else:
        task.error_append("run \"{}\" error: {}".format(cmd_start, errp))

    task.print_result()
