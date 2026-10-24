"""Drive the real pydiagral against the fake cloud, method by method.

Run it after changing server.py or bumping pydiagral, with a Python that has
the pinned pydiagral installed:

    python smoke.py [http://127.0.0.1:8099]

Every method hass-diagral calls is exercised, in the order the integration
uses them. A failure means the fake cloud and pydiagral disagree.
"""

from __future__ import annotations

import asyncio
import sys

from pydiagral import DiagralAPI
import pydiagral.api
from pydiagral.exceptions import AuthenticationError, DiagralAPIError

SERIAL = "FAKECENTRAL01"
ACCOUNT = {"username": "fake@example.com", "password": "fake-password"}
PIN = "1234"


async def main(base_url: str) -> None:
    pydiagral.api.BASE_URL = base_url

    async with DiagralAPI(
        username="nobody@example.com",
        password="x",
        serial_id=SERIAL,
        pincode=PIN,
    ) as api:
        try:
            await api.try_connection(ephemeral=True)
        except AuthenticationError:
            print("ok  bad credentials rejected")
        else:
            raise AssertionError("bad credentials were accepted")

    async with DiagralAPI(**ACCOUNT, serial_id=SERIAL, pincode=PIN) as api:
        result = await api.try_connection(ephemeral=True)
        assert result.result and result.keys is None
        print("ok  try_connection(ephemeral=True)")

    async with DiagralAPI(**ACCOUNT, serial_id=SERIAL, pincode=PIN) as api:
        result = await api.try_connection(ephemeral=False)
        keys = result.keys
        assert keys.api_key and keys.secret_key
        name = await api.get_alarm_name()
        print(f"ok  try_connection(ephemeral=False) + get_alarm_name -> {name!r}")

    async with DiagralAPI(
        **ACCOUNT,
        serial_id=SERIAL,
        pincode=PIN,
        apikey=keys.api_key,
        secret_key=keys.secret_key,
    ) as api:
        config = await api.get_configuration()
        assert config.alarm.central.serial == SERIAL
        assert [g.index for g in config.groups] == [1, 2, 3]
        devices = await api.get_devices_info()
        assert devices.sensors[0].label == "Front door"
        print("ok  get_configuration + get_devices_info")

        status = await api.get_system_status()
        assert status.status == "OFF"
        anomalies = await api.get_anomalies()
        assert not anomalies
        print("ok  get_system_status + get_anomalies (none)")

        assert (await api.start_system()).status == "GROUP"
        assert (await api.presence()).status == "PRESENCE"
        assert (await api.stop_system()).status == "OFF"
        assert (await api.activate_group([1, 3])).activated_groups == [1, 3]
        assert (await api.disable_group([1])).activated_groups == [3]
        assert (await api.disable_group([3])).status == "OFF"
        print("ok  start / presence / stop / activate_group / disable_group")

        try:
            await api.get_webhook()
        except DiagralAPIError as err:
            assert "No subscription found for" in str(err), err
            print("ok  get_webhook without subscription -> expected error")
        url = "https://ha.example.com/api/webhook/fakeid"
        flags = {
            "subscribe_to_anomaly": True,
            "subscribe_to_alert": True,
            "subscribe_to_state": True,
        }
        await api.register_webhook(webhook_url=url, **flags)
        assert (await api.get_webhook()).webhook_url == url
        await api.update_webhook(webhook_url=url + "2", **flags)
        assert (await api.get_webhook()).webhook_url == url + "2"
        await api.delete_webhook()
        print("ok  register / get / update / delete webhook")

    async with DiagralAPI(**ACCOUNT, serial_id=SERIAL) as api:
        await api.login()
        await api.delete_apikey(apikey=keys.api_key)
        print("ok  login + delete_apikey")

    print("smoke test passed")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"))
