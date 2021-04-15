# Solaredge-MQTT gateway

This is a simple application that reads information from Solaredge
inverters via Modbus TCP and sends them to an MQTT gateway.

This project uses
[solaredge-modbus](https://pypi.org/project/solaredge-modbus/) to communicate
with the inverter, and [paho-mqtt](https://pypi.org/project/paho-mqtt/) for
talking to MQTT.

## Installation

This project uses [Poetry](https://python-poetry.org/) for dependency
management, and it's probably easiest to use this, Executing `poetry install 
--no-dev` followed by `poetry run solaredge-mqtt` from the git checkout root should
set up a venv, install the required dependencies into a venv and run
the main program.

Installation via pip into a venv is also possible with `pip install .` from
the git checkout root. This will also create the executable scripts in the
`bin` dir of the checkout.

In case you want to do things manually, the main entry point into
the program is `solaredge_mqtt/cli.py:solaredge_mqtt()`.

## Running

`--config`
: Specify a configuration file to load. See the section `Configuration file`
  for details on the syntax. Command line options given in addition to the
  config file override settings in the config file.

`--solaredge-host`
: The IP address or hostname of the Solaredge inverter to connect to. This is a
  required parameter.

  Config file: Section `general`, `solaredge-host`

`--solaredge-port`
: The modbus port number to connect to. Defaults to 1502.

  Config file: Section `general`, `solaredge-port`

`--read-every N`
: Read information from the inverter "every N seconds. The time stamp sent to
MQTT will also be aligned to a multiple of this number (see also --time-offset)

  Config file: Section `general`, `read-every`. Defaults to 5.

`--time-offset N`
: The values read from the inverter are not current, "but represent a state
a few seconds in the past. Use this to offset the timestamps of the data sent
to MQTT. "This mainly important to sync the read with data from a different
device, like a smart energy meter, which may use internal time stamps. Using
this will affect the alignment of time stamps sent to MQTT (see --read-every).
Positive values will shift the time stamps into the past.

  Config file: Section `general`, `time-offset`. Defaults to 0.

`--mqtt-host`
: The MQTT host name to connect to. This is a required parameter.

  Config file: Section `general`, `mqtt-host`

`--mqtt-port`
: The MQTT port number to connect to. Defaults to 1883.

  Config file: Section `general`, `mqtt-port`

`--buffer-size`
: The size of the buffer (in number of measurements) that can be locally
  saved when the MQTT server is unavailable. The buffer is not persistent,
  and will be lost when the program exits. Defaults to 100000.

  Config file: Section `general`, `buffer-size`

`--mqtt-topic`
: The MQTT topic to publish the information to. This is a string that is put
  through python formatting, and can contain references to the variable `serial`.
  `serial` will contain the serial number of the inverter, which
  is part of the modbus data.
  The default is `solaredge-mqtt/tele/%(serial)s/SENSOR`.

  Config file: Section `general`, `mqtt-topic`

`--mqtt-client-id`
: The client identifier used when connecting to the MQTT gateway. This needs
  to be unique for all clients connecting to the same gateway, only one
  client can be connected with the same name at a time. The default is
  `se-mqtt-gateway`.

  Config file: Section `general`, `mqtt-client-id`

## Configuration file
The program supports a configuration file to define behaviour. The
configuration file is in .ini file syntax, and can contain multiple sections.
The `[general]` section contains settings that define overall program
behaviour.

### Example configuration file

```
[general]
mqtt-client-id = se-gateway-01
mqtt-host = mqtt.example.com
solaredge-host = 192.168.1.1

```
## Data pushed to MQTT

The script pushes the data received from the inverter to MQTT as a JSON
string. The information received from `solaredge-modbus` is presented as-is,
retaining the field names, but with scaling factors applied, so the numbers
are immediately useful. The scaling factors themselves are not sent.

In addition the following fields are added:

- a `solaredge_mqtt_timestamp` field is added, containing the time the measurement
  was taken. This is a UNIX timestamp in milliseconds. This value is taken
  from the system time, make sure this is correct (synced via NTP) before
  starting this program.
