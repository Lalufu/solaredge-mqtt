"""
Solaredge to MQTT gateway

This contains the solaredge/modbus specific parts
"""

import logging
import math
import multiprocessing
import threading
import time
from typing import Any, Dict, Tuple

import solaredge_modbus  # type: ignore
from pymodbus.exceptions import ConnectionException  # type: ignore

LOGGER = logging.getLogger(__name__)

# A dictionary matching scale factors to the values they
# apply to
SCALEFACTORS: Dict[str, Tuple] = {
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

    This tries to sync reads from the inverter to the
    "read_every" config setting.

    The sync happens before the read from the inverter. This
    is not ideal, since we don't know how long the read will
    take. This is a concious tradeoff.
    """

    LOGGER.info("solaredge process starting")

    inverter = solaredge_modbus.Inverter(
        host=config["solaredge_host"], port=config["solaredge_port"], timeout=5
    )

    # This is a correction term that is used to adjust for the fact
    # that waking up from sleep takes a while.
    epsilon = 0

    # We want to run execution on seconds that are divisible by this
    synctime = config["read_every"]

    # If the scheduled start time and the actual start time is
    # off by more than this, skip the run
    maxdelta = 0.05

    # This object is purely used to sleep on
    event = threading.Event()

    while True:
        # Time where the next execution is supposed to happen
        now = time.time()
        nextrun = math.ceil(now / synctime) * synctime
        sleep = nextrun - now - epsilon

        if sleep < 0:
            # This can happen if we're very close to nextrun, and
            # epsilon is negative. In this case restart the loop,
            # which should push us into the next interval
            LOGGER.error(
                "Skipping loop due to negative sleep interval. If "
                "this keeps happening, increase --read-every"
            )
            continue

        # This is a lot more accurate than time.sleep()
        event.wait(timeout=sleep)

        start = time.time()
        delta = start - nextrun

        # These are the various times involved here:
        #
        #    T_1            T_2  T_3   T_4
        #     |              |    |     |
        #     V              V    V     V
        # -----------------------------------------------------
        #
        # T_1 is the time where we went to sleep
        # T_2 is the time were the sleep should have ended. T_2 - T_1 is
        #   the duration we pass to the event.wait() call.
        # T_3 is the time where we wanted to come out of sleep. T_3 - T_2
        #   is `epsilon`, and in an ideal world it would be 0.
        # T_4 is the time where we actually came out of the sleep, this
        #   is the time in `start`. T_4 - T_3 is `delta`
        #
        # We want to adjust `epsilon` so that T_3 == T_4.

        # Calculate the adjustment to the sleep duration. This takes the
        # existing offset, and corrects it by a fraction of the measured
        # difference.
        #
        # This uses a running average over the last N values,
        # without actually having to store them.
        #
        # Assume epsilon contains the average of the last N
        # values, and we want to adjust for the current delta.
        # The amount of time we should have slept is (epsilon + delta).
        #
        # The new average is
        # ( (N - 1) * epsilon ) + epsilon + delta ) / N
        #
        # which is the same as
        #
        # ( N * epsilon + delta ) / N
        #
        # or
        #
        # epsilon + ( delta / N )
        #
        # Take the average over the last 10
        epsilon = epsilon + (0.1 * delta)

        LOGGER.debug(
            "Starting loop at %f, desired was %f, delta %f, new epsilon %f",
            start,
            nextrun,
            delta,
            epsilon,
        )

        if abs(delta) > maxdelta:
            LOGGER.error("Skipping run, offset too large")
            continue

        try:
            data = inverter.read_all()
            if data == {}:
                raise ValueError("No data from inverter")
        except (ValueError, ConnectionException) as exc:
            LOGGER.error("Error reading from inverter: %s", exc)
            LOGGER.error("Sleeping for 5 seconds")
            event.wait(timeout=5)
            continue

        LOGGER.debug("Received values from inverter: %s", data)

        # The values, as read from the inverter, need to be scaled
        # according to a scale factor that's also present in the data.
        for scalefactor, fields in SCALEFACTORS.items():
            for field in fields:
                if field in data:
                    data[field] = data[field] * (10 ** data[scalefactor])

            del data[scalefactor]

        LOGGER.debug("Processed data: %s", data)

        # Add a time stamp. This is an integer, in milliseconds
        # since epoch
        data["solaredge_mqtt_timestamp"] = int((nextrun - config["time_offset"]) * 1000)

        try:
            mqtt_queue.put(data, block=False)
        except Exception:
            # Ignore this
            pass
