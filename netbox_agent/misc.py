from contextlib import suppress
from netbox_agent.config import netbox_instance as nb
from slugify import slugify
from shutil import which
import distro
import subprocess
import socket
import re


def is_tool(name):
    """Check whether `name` is on PATH and marked as executable."""
    return which(name) is not None


def get_device_role(role):
    device_role = nb.dcim.device_roles.get(name=role)
    if device_role is None:
        raise Exception('DeviceRole "{}" does not exist, please create it'.format(role))
    return device_role


def get_device_type(type):
    device_type = nb.dcim.device_types.get(model=type)
    if device_type is None:
        raise Exception('DeviceType "{}" does not exist, please create it'.format(type))
    return device_type


def get_device_platform(device_platform):
    if device_platform is None:
        try:
            linux_distribution = "{name} {version_id} {release_codename}".format(**distro.os_release_info())

            if not linux_distribution:
                return None
        except (ModuleNotFoundError, NameError, AttributeError):
            return None
    else:
        linux_distribution = device_platform

    device_platform = nb.dcim.platforms.get(name=linux_distribution)
    if device_platform is None:
        device_platform = nb.dcim.platforms.create(
            name=linux_distribution, slug=slugify(linux_distribution)
        )
    return device_platform


def get_vendor(name):
    vendors = {
        "PERC": "Dell",
        "SANDISK": "SanDisk",
        "DELL": "Dell",
        "ST": "Seagate",
        "CRUCIAL": "Crucial",
        "MICRON": "Micron",
        "INTEL": "Intel",
        "SAMSUNG": "Samsung",
        "EH0": "HP",
        "HGST": "HGST",
        "HUH": "HGST",
        "MB": "Toshiba",
        "MC": "Toshiba",
        "MD": "Toshiba",
        "MG": "Toshiba",
        "WD": "WDC",
    }
    for key, value in vendors.items():
        if name.upper().startswith(key):
            return value
    return name


def get_hostname(config):
    if config.hostname_cmd is None:
        return "{}".format(socket.gethostname())
    return subprocess.getoutput(config.hostname_cmd)

def verify_serial(serial: str):
    
    serial_number_pattern = r'^(?=.*\d)[A-Za-z0-9]{1,12}$'

    if re.match(serial_number_pattern, serial):
        return True
    
    return False

def create_netbox_tags(tags):
    ret = []
    for tag in tags:
        nb_tag = nb.extras.tags.get(name=tag)
        if not nb_tag:
            nb_tag = nb.extras.tags.create(
                name=tag,
                slug=slugify(tag),
            )
        ret.append(nb_tag)
    return ret


def get_mount_points():
    mount_points = {}
    output = subprocess.getoutput("mount")
    for r in output.split("\n"):
        if not r.startswith("/dev/"):
            continue
        mount_info = r.split()
        device = mount_info[0]
        device = re.sub(r"\d+$", "", device)
        mp = mount_info[2]
        mount_points.setdefault(device, []).append(mp)
    return mount_points
