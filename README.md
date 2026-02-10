# ASDB Scheduler

Project for tooling allowing for the generation and visualization of a TDMA schedule for an example
ASDB network.

The program is split into two functions:

- `scheduler.py`: Generates a TDMA schedule from input
- `visualizer.py`: Offers functions for visual representation of the schedule or network graph

The executable program parts can be found in the `src` folder.


Dependencies and build options are found in the `pyproject.toml`.

## Usage

```sh
pip install -e .[test,dev]
```

For the scheduler.py

```
usage: scheduler [-h] [-o OUTPUT_FOLDER] [-i INPUT_SCHEMA]
                 [-s SCHEDULE_SCHEMA] [-c CONFIG_SCHEMA]
                 [-l {debug,info,warning,warn,error,fatal,critical}]
                 [input-scheduler]

Scheduler for TDMA

positional arguments:
  input-scheduler       scheduler input file name (default:
                        example_network.json)

options:
  -h, --help            show this help message and exit
  -o OUTPUT_FOLDER, --output-folder OUTPUT_FOLDER
                        output folder name (default: output)
  -i INPUT_SCHEMA, --input-schema INPUT_SCHEMA
                        input file schema (default:
                        schema_input_scheduler.json)
  -s SCHEDULE_SCHEMA, --schedule-schema SCHEDULE_SCHEMA
                        output schedule file schema (default:
                        schema_output_scheduler.json)
  -c CONFIG_SCHEMA, --config-schema CONFIG_SCHEMA
                        output config file schema (default:
                        schema_output_config.json)
  -l {debug,info,warning,warn,error,fatal,critical}, --log-level {debug,info,warning,warn,error,fatal,critical}
                        log level (default: info)
```

## Example

```
python .\scheduler.py .\example_network.json -o Results
```

## License

Licensed under either of

- Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE) or http://www.apache.org/licenses/LICENSE-2.0)
- MIT License ([LICENSE-MIT](LICENSE-MIT) or http://opensource.org/licenses/MIT)

at your option.

## Contribution

Unless you explicitly state otherwise, any contribution intentionally submitted for inclusion in the work by you, as defined in the Apache-2.0 license, shall be dual licensed as above, without any additional terms or conditions.

## Copyright

Copyright © 2026 Deutsches Zentrum für Luft- und Raumfahrt e.V. (DLR)
