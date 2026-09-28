/* Devices grouped by how the forecast models them (shiftable → fixed-time → always-on → heating), with what each
   device is drawing right now (simulated from the fake clock, see js/power.js). Used inside the Forecast tab. */
document.addEventListener('alpine:init', () => {
  Alpine.data('deviceList', () => ({
    devices: [],
    format: HW.power.format,

    async init() {
      this.devices = await HW.api.getDevices();
    },

    get minute() {
      return Alpine.store('clock').minutes;
    },
    get groups() {
      return HW.config.deviceGroups
        .map((g) => ({ ...g, devices: this.devices.filter((d) => d.model === g.model) }))
        .filter((g) => g.devices.length);
    },

    /** The confirmed shift for a device (washing machine / dishwasher), if it has been scheduled. */
    scheduled(device) {
      return Alpine.store('shifts').scheduledFor(device.name);
    },
    draw(device) {
      return HW.power.draw(device, this.minute);
    },
    groupTotal(group) {
      return group.devices.reduce((sum, d) => sum + this.draw(d), 0);
    },
    get total() {
      return this.devices.reduce((sum, d) => sum + this.draw(d), 0);
    },
    get activeCount() {
      return this.devices.filter((d) => this.draw(d) > 0).length;
    },
  }));
});
