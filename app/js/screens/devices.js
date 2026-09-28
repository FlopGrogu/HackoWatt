/* Active devices grouped by room: forecast model and what each device is drawing right now
   (simulated from the fake clock, see js/power.js). */
document.addEventListener('alpine:init', () => {
  Alpine.data('devicesScreen', () => ({
    rooms: [],
    models: HW.config.models,
    format: HW.power.format,

    async init() {
      this.rooms = await HW.api.getRooms();
    },

    get minute() {
      return Alpine.store('clock').minutes;
    },
    get devices() {
      return this.rooms.flatMap((room) => room.devices);
    },

    draw(device) {
      return HW.power.draw(device, this.minute);
    },
    roomTotal(room) {
      return room.devices.reduce((sum, d) => sum + this.draw(d), 0);
    },
    get total() {
      return this.rooms.reduce((sum, room) => sum + this.roomTotal(room), 0);
    },
    get activeCount() {
      return this.devices.filter((d) => this.draw(d) > 0).length;
    },
  }));
});
