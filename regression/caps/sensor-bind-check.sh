#!/bin/sh
# regression/caps/sensor-bind-check.sh — SPIKE-0 (tsp-9sx.1) sensor-bind evidence.
#
# READ-ONLY. Runs on a device (BusyBox-safe) and prints whether DT-listed sensors
# (a523: qmi8658 imu / mmc5603 mag / GNSS) actually BIND — the R3 rule is that a
# DT-but-unbound sensor is OMITTED from the descriptor's [[sensors]], never claimed.
# Capture the output verbatim as the bead transcript.

echo "== uname =="
uname -a

echo "== /sys/bus/iio/devices =="
ls -l /sys/bus/iio/devices/ 2>&1
for d in /sys/bus/iio/devices/iio:device*; do
    [ -e "$d" ] || continue
    echo "$d name=$(cat "$d/name" 2>/dev/null)"
done

echo "== i2c devices (name + bound driver) =="
for d in /sys/bus/i2c/devices/*; do
    [ -e "$d/name" ] || continue
    drv=""
    [ -e "$d/driver" ] && drv=$(basename "$(readlink "$d/driver")")
    echo "$d name=$(cat "$d/name" 2>/dev/null) driver=${drv:-UNBOUND}"
done

echo "== spi devices (name + bound driver) =="
for d in /sys/bus/spi/devices/*; do
    [ -e "$d" ] || continue
    drv=""
    [ -e "$d/driver" ] && drv=$(basename "$(readlink "$d/driver")")
    echo "$d modalias=$(cat "$d/modalias" 2>/dev/null) driver=${drv:-UNBOUND}"
done

echo "== DT nodes mentioning qmi8658 / mmc5603 / gnss / gps =="
if [ -d /proc/device-tree ]; then
    find /proc/device-tree -name compatible 2>/dev/null | while read -r f; do
        case "$(tr '\0' ' ' < "$f")" in
        *qmi8658*|*mmc5603*|*gnss*|*gps*) echo "$f: $(tr '\0' ' ' < "$f")" ;;
        esac
    done
else
    echo "no /proc/device-tree"
fi

echo "== loaded modules matching sensor stacks =="
lsmod 2>/dev/null | grep -i 'qmi\|mmc5\|gnss\|gps\|iio\|inv_\|icm\|bmi' || echo "(none)"

echo "== uevent drivers for platform sensor nodes =="
grep -l 'qmi8658\|mmc5603\|gnss' /sys/bus/platform/devices/*/uevent 2>/dev/null || echo "(none)"

echo "== /proc/bus/input/devices =="
cat /proc/bus/input/devices 2>/dev/null

echo "== done =="
