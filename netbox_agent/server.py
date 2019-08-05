from pprint import pprint
import socket

from netbox_agent.config import netbox_instance as nb
from netbox_agent.location import Datacenter
import netbox_agent.dmidecode as dmidecode
from netbox_agent.network import Network


class ServerBase():
    def __init__(self, dmi=None):
        if dmi:
            self.dmi = dmi
        else:
            self.dmi = dmidecode.parse()
        self.system = self.dmi.get_by_type('System')
        self.bios = self.dmi.get_by_type('BIOS')

        self.network = Network(server=self)

    def get_datacenter(self):
        dc = Datacenter()
        return dc.get()

    def get_netbox_datacenter(self):
        datacenter = nb.dcim.sites.get(
            slug=self.get_datacenter()
        )
        return datacenter

    def get_product_name(self):
        """
        Return the Chassis Name from dmidecode info
        """
        return self.system[0]['Product Name']

    def get_service_tag(self):
        """
        Return the Service Tag from dmidecode info
        """
        return self.system[0]['Serial Number']

    def get_hostname(self):
        return '{}'.format(socket.gethostname())

    def is_blade(self):
        raise NotImplementedError

    def get_blade_slot(self):
        raise NotImplementedError

    def get_chassis(self):
        raise NotImplementedError

    def get_chassis_service_tag(self):
        raise NotImplementedError

    def get_bios_version(self):
        raise NotImplementedError

    def get_bios_version_attr(self):
        raise NotImplementedError

    def get_bios_release_date(self):
        raise NotImplementedError

    def _netbox_create_blade_chassis(self, datacenter):
        device_type = nb.dcim.device_types.get(
            model=self.get_chassis(),
        )
        if not device_type:
            raise Exception('Chassis "{}" doesn\'t exist'.format(self.get_chassis()))
        device_role = nb.dcim.device_roles.get(
            name='Server Chassis',
        )
        new_chassis = nb.dcim.devices.create(
            name=''.format(),
            device_type=device_type.id,
            serial=self.get_chassis_service_tag(),
            device_role=device_role.id,
            site=datacenter.id if datacenter else None,
        )
        return new_chassis

    def _netbox_create_blade(self, chassis, datacenter):
        device_role = nb.dcim.device_roles.get(
            name='Blade',
        )
        device_type = nb.dcim.device_types.get(
            model=self.get_product_name(),
        )
        new_blade = nb.dcim.devices.create(
            name=self.get_hostname(),
            serial=self.get_service_tag(),
            device_role=device_role.id,
            device_type=device_type.id,
            parent_device=chassis.id,
            site=datacenter.id if datacenter else None,
        )
        return new_blade

    def _netbox_create_server(self, datacenter):
        device_role = nb.dcim.device_roles.get(
            name='Server',
        )
        device_type = nb.dcim.device_types.get(
            model=self.get_product_name(),
        )
        if not device_type:
            raise Exception('Chassis "{}" doesn\'t exist'.format(self.get_chassis()))
        new_server = nb.dcim.devices.create(
            name=self.get_hostname(),
            serial=self.get_service_tag(),
            device_role=device_role.id,
            device_type=device_type.id,
            site=datacenter.id if datacenter else None,
        )
        return new_server

    def get_netbox_server(self):
        return nb.dcim.devices.get(serial=self.get_service_tag())

    def netbox_create(self):
        datacenter = self.get_netbox_datacenter()
        if self.is_blade():
            # let's find the blade
            blade = nb.dcim.devices.get(serial=self.get_service_tag())
            chassis = nb.dcim.devices.get(serial=self.get_chassis_service_tag())
            # if it doesn't exist, create it
            if not blade:
                # check if the chassis exist before
                # if it doesn't exist, create it
                chassis = nb.dcim.devices.get(
                    serial=self.get_chassis_service_tag()
                    )
                if not chassis:
                    chassis = self._netbox_create_blade_chassis(datacenter)

                blade = self._netbox_create_blade(chassis, datacenter)

            # Find the slot and update it with our blade
            device_bays = nb.dcim.device_bays.filter(
                device_id=chassis.id,
                name='Blade {}'.format(self.get_blade_slot()),
                )
            if len(device_bays) > 0:
                device_bay = device_bays[0]
                device_bay.installed_device = blade
                device_bay.save()
        else:
            server = nb.dcim.devices.get(serial=self.get_service_tag())
            if not server:
                self._netbox_create_server()

        self.network.update_netbox_network_cards()

    def netbox_update(self):
        """
        Netbox method to update info about our server/blade

        Handle:
        * new chasis for a blade
        * new slot for a bblade
        * hostname update
        * new network infos
        """
        server = nb.dcim.devices.get(serial=self.get_service_tag())
        if not server:
            raise Exception("The server (Serial: {}) isn't yet registered in Netbox, register"
                            "it before updating it".format(self.get_service_tag()))
        update = False
        if self.is_blade():
            # get current chassis device bay
            device_bay = nb.dcim.device_bays.get(
                server.parent_device.device_bay.id
                )
            netbox_chassis_serial = server.parent_device.device_bay.device.serial
            chassis = server.parent_device.device_bay.device
            move_device_bay = False

            # check chassis serial with dmidecode
            if netbox_chassis_serial != self.get_chassis_service_tag():
                move_device_bay = True
                # try to find the new netbox chassis
                chassis = nb.dcim.devices.get(
                    serial=self.get_chassis_service_tag()
                )
                # create the new chassis if it doesn't exist
                if not chassis:
                    chassis = self._netbox_create_blade_chassis(datacenter)

            if move_device_bay or device_bay.name != 'Blade {}'.format(self.get_blade_slot()):
                device_bay.installed_device = None
                device_bay.save()

                # Find the slot and update it with our blade
                device_bays = nb.dcim.device_bays.filter(
                    device_id=chassis.id,
                    name='Blade {}'.format(self.get_blade_slot()),
                )
                if len(device_bays) > 0:
                    device_bay = device_bays[0]
                    device_bay.installed_device = server
                    device_bay.save()

        # for every other specs
        # check hostname
        if server.name != self.get_hostname():
            update = True
            server.hostname = self.get_hostname()
        # check network cards
        #self.network.update_netbox_network_cards()
        if update:
            server.save()

    def print_debug(self):
        # FIXME: do something more generic by looping on every get_* methods
        print('Datacenter:', self.get_datacenter())
        print('Netbox Datacenter:', self.get_netbox_datacenter())
        print('Is blade:', self.is_blade())
        print('Product Name:', self.get_product_name())
        print('Chassis:', self.get_chassis())
        print('Chassis service tag:', self.get_chassis_service_tag())
        print('Service tag:', self.get_service_tag())
        print('NIC:',)
        pprint(self.network.get_network_cards())
        pass
