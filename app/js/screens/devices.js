/* Devices grouped by how the forecast models them (shiftable → fixed-time → always-on → heating), with what each
   running device draws at the moment last hovered on the forecast chart (the current time until then), simulated
   by js/power.js. Devices that are off are hidden; scheduled shiftable devices move to their new time.
   Used inside the Forecast tab. */
document.addEventListener('alpine:init', () => {
  Alpine.data('deviceList', () => ({
    devices: [],
    format: HW.power.format,

    async init() {
      this.devices = await HW.api.getDevices();
    },

    // --- the moment shown: last hovered forecast time, else the (fake) clock ---
    get date() {
      const focus = Alpine.store('focus').time;
      return focus ? new Date(focus) : Alpine.store('clock').date;
    },
    get minute() {
      return this.date.getHours() * 60 + this.date.getMinutes();
    },
    get dateLabel() {
      return this.date.toLocaleString('en-US', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false });
    },

    /** The confirmed shift for a device (washing machine / dishwasher), if it has been scheduled. */
    scheduled(device) {
      return Alpine.store('shifts').scheduledFor(device.name);
    },
    draw(device) {
      const shift = this.scheduled(device);
      if (!shift || device.runs === 'always') return HW.power.draw(device, this.minute);
      const ideal = new Date(shift.ideal);                    // runs at the scheduled time instead of the usual one
      const runs = [[ideal.getHours() * 60 + ideal.getMinutes(), device.runs[0][1]]];
      return HW.power.draw({ ...device, runs }, this.minute);
    },
    visible(device) {
      return this.draw(device) > 0 || !!this.scheduled(device);
    },

    get groups() {
      return HW.config.deviceGroups
        .map((g) => ({ ...g, devices: this.devices.filter((d) => d.model === g.model && this.visible(d)) }))
        .filter((g) => g.devices.length);
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
