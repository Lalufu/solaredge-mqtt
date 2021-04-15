"""
This file contains the CLI script entry points
"""

import argparse
import codecs
import configparser
import logging
import multiprocessing
import time
from typing import Any, Dict, List

from .mqtt import mqtt_main
from .solaredge import solaredge_main

logging.basicConfig(
    format="%(asctime)-15s %(levelname)s: %(message)s", level=logging.INFO
)
LOGGER = logging.getLogger(__name__)

# Default values for command line args
DEFAULTS: Dict[str, Any] = {
    "mqtt_port": 1883,
    "buffer_size": 100000,
    "mqtt_topic": "solaredge-mqtt/tele/%(serial)s/SENSOR",
    "mqtt_client_id": "se-mqtt-gateway",
    "solaredge_port": 1502,
    "read_every": 5,
    "time_offset": 0,
}


def load_config_file(filename: str) -> Dict[str, Any]:
    """
    Load the ini style config file given by `filename`
    """

    config: Dict[str, Any] = {}
    ini = configparser.ConfigParser()
    try:
        with codecs.open(filename, encoding="utf-8") as configfile:
            ini.read_file(configfile)
    except Exception as exc:
        LOGGER.error("Could not read config file %s: %s", filename, exc)
        raise SystemExit(1)

    if ini.has_option("general", "solaredge-host"):
        config["solaredge_host"] = ini.get("general", "solaredge-host")

    try:
        if ini.has_option("general", "solaredge-port"):
            config["solaredge_port"] = ini.getint("general", "solaredge-port")
    except ValueError:
        LOGGER.error(
            "%s: %s is not a valid value for solaredge-port",
            filename,
            ini.get("general", "solaredge-port"),
        )
        raise SystemExit(1)

    if ini.has_option("general", "read-every"):
        config["read_every"] = ini.get("general", "read-every")

    if ini.has_option("general", "time-offset"):
        config["time_offset"] = ini.get("general", "time-offset")

    if ini.has_option("general", "mqtt-host"):
        config["mqtt_host"] = ini.get("general", "mqtt-host")

    try:
        if ini.has_option("general", "mqtt-port"):
            config["mqtt_port"] = ini.getint("general", "mqtt-port")
    except ValueError:
        LOGGER.error(
            "%s: %s is not a valid value for mqtt-port",
            filename,
            ini.get("general", "mqtt-port"),
        )
        raise SystemExit(1)

    if ini.has_option("general", "mqtt-client-id"):
        config["mqtt_client_id"] = ini.get("general", "mqtt-client-id")

    try:
        if ini.has_option("general", "buffer-size"):
            config["buffer_size"] = ini.getint("general", "buffer-size")
    except ValueError:
        LOGGER.error(
            "%s: %s is not a valid value for buffer-size",
            filename,
            ini.get("general", "buffer-size"),
        )
        raise SystemExit(1)

    return config


def solaredge_mqtt() -> None:
    """
    Main function for the solaredge-mqtt script
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, help="Configuration file to load")
    parser.add_argument(
        "--mqtt-topic",
        type=str,
        default=None,
        help="MQTT topic to publish to. May contain python format string "
        "references to variables `serial` (containing the serial number "
        "of the device generating the data) and `channel` (containing the "
        "channel of the device generating the data). "
        + ("(Default: %(mqtt_topic)s)" % DEFAULTS).replace("%", "%%"),
    )
    parser.add_argument(
        "--solaredge-host", type=str, help="Solaredge host to connect to"
    )
    parser.add_argument(
        "--solaredge-port",
        type=int,
        default=None,
        help="Solaredge port to connect to. "
        + ("(Default: %(solaredge_port)s)" % DEFAULTS),
    )
    parser.add_argument(
        "--read-every",
        type=float,
        help="Read information from the inverter "
        "every N seconds. The time stamp sent to MQTT will also be aligned "
        "to a multiple of this number (see also --time-offset)",
        default=None,
    )
    parser.add_argument(
        "--time-offset",
        type=float,
        help="The values read from the inverter are not current, "
        "but represent a state a few seconds in the past. Use this "
        "to offset the timestamps of the data sent to MQTT. "
        "This mainly important to sync the read with data from a "
        "different device, like a smart energy meter, which may use "
        "internal time stamps. Using this will affect the alignment of "
        "time stamps sent to MQTT (see --read-every). Positive values "
        "will shift the time stamps into the past",
        default=None,
    )
    parser.add_argument("--mqtt-host", type=str, help="MQTT server to connect to")
    parser.add_argument(
        "--mqtt-port", type=int, default=None, help="MQTT port to connect to"
    )
    parser.add_argument(
        "--mqtt-client-id",
        type=str,
        default=None,
        help="MQTT client ID. Needs to be unique between all clients connecting "
        "to the same broker",
    )
    parser.add_argument(
        "--buffer-size",
        type=int,
        default=None,
        help="How many measurements to buffer if the MQTT "
        "server should be unavailable. This buffer is not "
        "persistent across program restarts.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.config:
        config = load_config_file(args.config)
    else:
        config = {}

    LOGGER.debug("Config after loading config file: %s", config)

    if args.solaredge_host:
        config["solaredge_host"] = args.solaredge_host

    if args.solaredge_port:
        config["solaredge_port"] = args.solaredge_port
    elif "solaredge_port" not in config:
        # Not set through config file, not set through CLI, use default
        config["solaredge_port"] = DEFAULTS["solaredge_port"]

    if args.read_every:
        config["read_every"] = args.read_every
    elif "read_every" not in config:
        # Not set through config file, not set through CLI, use default
        config["read_every"] = DEFAULTS["read_every"]

    if args.time_offset:
        config["time_offset"] = args.time_offset
    elif "time_offset" not in config:
        # Not set through config file, not set through CLI, use default
        config["time_offset"] = DEFAULTS["time_offset"]

    if args.mqtt_topic:
        config["mqtt_topic"] = args.mqtt_topic
    elif "mqtt_topic" not in config:
        # Not set through config file, not set through CLI, use default
        config["mqtt_topic"] = DEFAULTS["mqtt_topic"]

    if args.mqtt_host:
        config["mqtt_host"] = args.mqtt_host

    if args.mqtt_port:
        config["mqtt_port"] = args.mqtt_port
    elif "mqtt_port" not in config:
        # Not set through config file, not set through CLI, use default
        config["mqtt_port"] = DEFAULTS["mqtt_port"]

    if args.mqtt_client_id:
        config["mqtt_client_id"] = args.mqtt_client_id
    elif "mqtt_client_id" not in config:
        # Not set through config file, not set through CLI, use default
        config["mqtt_client_id"] = DEFAULTS["mqtt_client_id"]

    if args.buffer_size:
        config["buffer_size"] = args.buffer_size
    elif "buffer_size" not in config:
        # Not set through config file, not set through CLI, use default
        config["buffer_size"] = DEFAULTS["buffer_size"]

    LOGGER.debug("Completed config: %s", config)

    if "solaredge_host" not in config:
        LOGGER.error("No solaredge host given")
        raise SystemExit(1)

    if "mqtt_host" not in config:
        LOGGER.error("No MQTT host given")
        raise SystemExit(1)

    solaredge_mqtt_queue: multiprocessing.Queue = multiprocessing.Queue(
        maxsize=config["buffer_size"]
    )

    procs: List[multiprocessing.Process] = []
    solaredge_proc = multiprocessing.Process(
        target=solaredge_main, name="solaredge", args=(solaredge_mqtt_queue, config)
    )
    solaredge_proc.start()
    procs.append(solaredge_proc)

    mqtt_proc = multiprocessing.Process(
        target=mqtt_main, name="mqtt", args=(solaredge_mqtt_queue, config)
    )
    mqtt_proc.start()
    procs.append(mqtt_proc)

    # Wait forever for one of the processes to die. If that happens,
    # kill the whole program.
    run = True
    while run:
        try:
            for proc in procs:
                if not proc.is_alive():
                    LOGGER.error("Child process died, terminating program")
                    run = False

            time.sleep(1)
        except KeyboardInterrupt:
            LOGGER.info("Caught keyboard interrupt, exiting")
            run = False

    for proc in procs:
        proc.terminate()
    raise SystemExit(1)
