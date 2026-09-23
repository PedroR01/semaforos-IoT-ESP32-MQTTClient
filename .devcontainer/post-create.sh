#!/usr/bin/env bash
set -euo pipefail

copy_example() {
    local example="$1"
    local target="${example%.example}"
    if [[ ! -f "$target" ]]; then
        cp "$example" "$target"
        echo "Created local configuration: $target"
    fi
}

copy_example firmware/camera-server/include/secrets.h.example
copy_example firmware/sensor-controller/include/secrets.h.example

python -m pip install --user --editable vision/detector
pio run -d firmware/sensor-controller -e esp32dev
pio run -d firmware/camera-server -e esp32cam
