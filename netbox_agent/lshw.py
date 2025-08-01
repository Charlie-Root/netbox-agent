from netbox_agent.misc import is_tool
import subprocess
import logging
import json
import sys


class LSHW:
    def __init__(self):
        if not is_tool("lshw"):
            logging.error("lshw does not seem to be installed")
            sys.exit(1)

        data = subprocess.getoutput(
            'lshw -quiet -json'
        )
        # lshw version 02.18.85-0.7 has a bug that causes it to return wrong JSON
        try:
            json_data = json.loads(data)
        except Exception as e:
            logging.error("Error while trying to parse lshw output: %s", e)
            sys.exit(1)

        # Starting from version 02.18, `lshw -json` wraps its result in a list
        # rather than returning directly a dictionary
        if isinstance(json_data, list):
            self.hw_info = json_data[0]
        else:
            self.hw_info = json_data
        self.info = {}
        self.memories = []
        self.interfaces = []
        self.cpus = []
        self.power = []
        self.disks = []
        self.gpus = []
        self.vendor = self.hw_info["vendor"]
        self.product = self.hw_info["product"]
        self.chassis_serial = self.hw_info["serial"]
        self.motherboard_serial = self.hw_info["children"][0].get("serial", "No S/N")
        self.motherboard = self.hw_info["children"][0].get("product", "Motherboard")

        for k in self.hw_info["children"]:
            if k["class"] == "power":
                # self.power[k["id"]] = k
                self.power.append(k)

            if "children" in k:
                for j in k["children"]:
                    if j["class"] == "generic":
                        continue

                    if j["class"] == "storage":
                        self.find_storage(j)

                    if j["class"] == "memory":
                        self.find_memories(j)

                    if j["class"] == "processor":
                        self.find_cpus(j)

                    if j["class"] == "bridge":
                        self.walk_bridge(j)

    def get_hw_linux(self, hwclass):
        if hwclass == "cpu":
            return self.cpus
        if hwclass == "gpu":
            return self.gpus
        if hwclass == "network":
            return self.interfaces
        if hwclass == "storage":
            return self.disks
        if hwclass == "memory":
            return self.memories

    def find_network(self, obj):
        # Some interfaces do not have device (logical) name (eth0, for
        # instance), such as not connected network mezzanine cards in blade
        # servers. In such situations, the card will be named `unknown[0-9]`.
        unkn_intfs = []
        for i in self.interfaces:
            # newer versions of lshw can return a list of names, see issue #227
            if not isinstance(i["name"], list):
                if i["name"].startswith("unknown"):
                    unkn_intfs.append(i)
            else:
                for j in i["name"]:
                    if j.startswith("unknown"):
                        unkn_intfs.append(j)

        unkn_name = "unknown{}".format(len(unkn_intfs))
        self.interfaces.append(
            {
                "name": obj.get("logicalname", unkn_name),
                "macaddress": obj.get("serial", ""),
                "serial": obj.get("serial", ""),
                "product": obj.get("product", "Unknown NIC"),
                "vendor": obj.get("vendor", "Unknown"),
                "description": obj.get("description", ""),
            }
        )

    def find_storage(self, obj):
        if "children" in obj:
            for device in obj["children"]:
                self.disks.append({
                    "logicalname": device.get("logicalname"),
                    "product": device.get("product"),
                    "serial": device.get("serial"),
                    "version": device.get("version"),
                    "size": device.get("size"),
                    "description": device.get("description"),
                    "type": device.get("description"),
                })
        
        if not is_tool('nvme'):
            logging.error('nvme-cli >= 1.0 does not seem to be installed')
            return
        try:
            logging.info("Trying to find NVME devices")
            nvme = json.loads(
                subprocess.check_output(
                    ["nvme", '-list', '-o', 'json'],
                    encoding='utf8')
            )
            num_devices = len(nvme["Devices"])
            logging.info("Found %d NVME devices", num_devices)

            for device in nvme["Devices"]:
                logging.info("Found NVME device %s with serial %s and size %s", device["DevicePath"], device["SerialNumber"], device["PhysicalSize"])


                d = {
                    'logicalname': device["DevicePath"],
                    'product': device["ModelNumber"],
                    'serial': device["SerialNumber"],
                    "version": device["Firmware"],
                    'description': "NVME",
                    'type': "NVME",
                    'size': device["PhysicalSize"]
                }
                
                self.disks.append(d)
        except Exception as e:
            logging.error("Error while trying to find NVME devices: %s", e)
            pass

    def find_cpus(self, obj):
        if "product" in obj:
            self.cpus.append(
                {
                    "product": obj.get("product", "Unknown CPU"),
                    "vendor": obj.get("vendor", "Unknown vendor"),
                    "description": obj.get("description", ""),
                    "location": obj.get("slot", ""),
                }
            )

    def find_memories(self, obj):
        if "children" not in obj:
            # print("not a DIMM memory.")
            return

        for dimm in obj["children"]:
            if "empty" in dimm["description"]:
                continue

            self.memories.append(
                {
                    "slot": dimm.get("slot"),
                    "description": dimm.get("description"),
                    "id": dimm.get("id"),
                    "serial": dimm.get("serial", "N/A"),
                    "vendor": dimm.get("vendor", "N/A"),
                    "product": dimm.get("product", "N/A"),
                    "size": dimm.get("size", 0) / 2**20 / 1024,
                }
            )

    def find_gpus(self, obj):
        if "product" in obj:
            infos = {
                "product": obj.get("product", "Unknown GPU"),
                "vendor": obj.get("vendor", "Unknown"),
                "description": obj.get("description", ""),
            }
            self.gpus.append(infos)

    def walk_bridge(self, obj):
        if "children" not in obj:
            return

        for bus in obj["children"]:
            if bus["class"] == "storage":
                self.find_storage(bus)
            if bus["class"] == "display":
                self.find_gpus(bus)

            if "children" in bus:
                for b in bus["children"]:
                    if b["class"] == "storage":
                        logging.info("found storage")
                        self.find_storage(b)

                    if b["class"] == "network":
                        self.find_network(b)
                    if b["class"] == "display":
                        self.find_gpus(b)


if __name__ == "__main__":
    pass
