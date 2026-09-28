/* Simulated instantaneous power draw of a device at a given minute of the day.
   A device draws power while inside one of its `runs` windows ([startMinute, durationMinutes], wrapping past
   midnight) or all day when runs === 'always'; the value is picked inside its typical `watts` range and
   changes every 5 minutes, deterministically (same clock time → same reading). */
HW.power = (() => {
  const DAY = 24 * 60;

  const noise = (seed) => {                      // stable pseudo-random number in [0, 1)
    let h = 2166136261;
    for (const ch of seed) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
    return ((h >>> 0) % 10000) / 10000;
  };

  const running = (device, minute) =>
    device.runs === 'always' ||
    device.runs.some(([start, length]) => (minute - start + DAY) % DAY < length);

  /** Current draw in watts (0 when the device is off). */
  const draw = (device, minute) => {
    if (!running(device, minute)) return 0;
    const [lo, hi] = device.watts;
    return Math.round(lo + (hi - lo) * noise(`${device.name}@${Math.floor(minute / 5)}`));
  };

  /** "150 W" below a kilowatt, "1.85 kW" above. */
  const format = (watts) => (watts >= 1000 ? `${(watts / 1000).toFixed(2)} kW` : `${watts} W`);

  return { draw, format };
})();
