/* Data service: the ONLY place screens get data from. Every method returns a Promise, so switching from
   the static demo data to the real forecast (e.g. fetch('/api/forecast?hours=24') or a JSON file exported
   by src/run_forecast.py) only changes this file – the screens stay as they are. */
(() => {
  const copy = (value) => Promise.resolve(structuredClone(value));
  const demo = () => HW.demo;

  HW.api = {
    getUser: () => copy(demo().user),
    getNow: () => copy(demo().now),
    getTariff: () => copy(HW.config.tariff),
    getOverview: () => copy(demo().overview),
    getPeakHours: () => copy(demo().peak),
    getUsage: (range) => copy(demo().usage[range]),
    getRooms: () => copy(demo().rooms),

    async getHomeTiles() {
      const rooms = await this.getRooms();
      const deviceCount = rooms.reduce((n, room) => n + room.devices.length, 0);
      const { temperature, humidity } = demo().home;
      return [
        { id: 'temperature', icon: 'thermometer', state: temperature.state, value: temperature.value,
          label: 'Temperature', highlight: true },
        { id: 'humidity', icon: 'droplet', state: humidity.state, value: humidity.value, label: 'Humidity' },
        { id: 'devices', icon: 'chip', state: 'Active', value: String(deviceCount), label: 'Devices',
          target: 'devices' },
      ];
    },
  };
})();
