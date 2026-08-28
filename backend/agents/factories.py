"""factory_boy factories for the agents app."""

import factory

from accounts.factories import UserFactory
from agents.models import Agent, Device, DeviceGroup


class AgentFactory(factory.django.DjangoModelFactory):
    """Factory for generating test agents."""

    class Meta:
        model = Agent
        django_get_or_create = ("agent_id",)
        skip_postgeneration_save = True

    agent_id = factory.Sequence(lambda n: f"agent-{n}")
    hostname = factory.Sequence(lambda n: f"host-{n}")
    ip_address = factory.Faker("ipv4")
    os_info = "Windows 11"
    status = Agent.Status.ONLINE
    capabilities = factory.LazyFunction(dict)
    is_local = False


class DeviceFactory(factory.django.DjangoModelFactory):
    """Factory for generating test devices."""

    class Meta:
        model = Device
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"device-{n}")
    device_type = Device.DeviceType.EMULATOR
    status = Device.Status.ONLINE
    agent = factory.SubFactory(AgentFactory)
    resolution_width = 1920
    resolution_height = 1080
    screenshot_fps = 30.0
    extra_info = factory.LazyFunction(dict)
    adb_serial = factory.Sequence(lambda n: f"emulator-{5554 + n}")
    emulator = "ldplayer"


class WindowsDeviceFactory(DeviceFactory):
    """Convenience factory for Windows devices."""

    device_type = Device.DeviceType.WINDOWS
    adb_serial = ""
    emulator = ""
    window_handle = factory.Sequence(lambda n: f"{n:08x}")


class DeviceGroupFactory(factory.django.DjangoModelFactory):
    """Factory for generating test device groups."""

    class Meta:
        model = DeviceGroup
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"group-{n}")
    user = factory.SubFactory(UserFactory)
