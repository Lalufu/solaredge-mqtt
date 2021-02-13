"""
Solaredge to MQTT gateway

This contains the solaredge/modbus specific parts
"""

import logging
import multiprocessing
import time
from typing import Any, Dict

import solaredge_modbus  # type: ignore
from pymodbus.exceptions import ConnectionException  # type: ignore

LOGGER = logging.getLogger(__name__)

# A dictionary matching scale factors to the values they
# apply to
SCALEFACTORS = {
    "current_scale": ("current", "p1_current", "p2_current", "p3_current"),
    "voltage_scale": (
        "p1_voltage",
        "p2_voltage",
        "p3_voltage",
        "p1n_voltage",
        "p2n_voltage",
        "p3n_voltage",
    ),
    "power_ac_scale": ("power_ac",),
    "frequency_scale": ("frequency",),
    "power_apparent_scale": ("power_apparent",),
    "power_reactive_scale": ("power_reactive",),
    "power_factor_scale": ("power_factor",),
    "energy_total_scale": ("energy_total",),
    "current_dc_scale": ("current_dc",),
    "voltage_dc_scale": ("voltage_dc",),
    "power_dc_scale": ("power_dc",),
    "temperature_scale": ("temperature",),
}


def solaredge_main(mqtt_queue: multiprocessing.Queue, config: Dict[str, Any]) -> None:
    """
    Main function for the solaredge process

    Read messages from modbus, process them and send them to the queue
    """

    LOGGER.info("solaredge process starting")

    inverter = solaredge_modbus.Inverter(
        host=config["solaredge_host"], port=config["solaredge_port"], timeout=5
    )

    while True:
        try:
            data = inverter.read_all()
        except ConnectionException as exc:
            LOGGER.error("Error reading from inverter: %s", exc)
            LOGGER.error("Sleeping for 5 seconds")
            time.sleep(5)
            continue

        LOGGER.debug("Received values from inverter: %s", data)

        # The values, as read from the inverter, need to be scaled
        # according to a scale factor that's also present in the data.
        for scalefactor, fields in SCALEFACTORS.items():
            for field in fields:
                data[field] = data[field] * (10 ** data[scalefactor])

            del data[scalefactor]

        LOGGER.debug("Processed data: %s", data)

        # Add a time stamp. This is an integer, in milliseconds
        # since epoch
        data["solaredge_mqtt_timestamp"] = int(time.time() * 1000)

        try:
            mqtt_queue.put(data, block=False)
        except Exception:
            # Ignore this
            pass

        time.sleep(5)
