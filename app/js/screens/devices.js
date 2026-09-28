/* Active devices grouped by room, with the forecast model used for each device. */
document.addEventListener('alpine:init', () => {
  Alpine.data('devicesScreen', () => ({
    rooms: [],
    models: HW.config.models,

    async init() {
      this.rooms = await HW.api.getRooms();
    },

    get deviceCount() {
      return this.rooms.reduce((n, room) => n + room.devices.length, 0);
    },

    roomTotal(room) {
      return room.devices.reduce((sum, d) => sum + d.watts, 0);
    },
  }));
});
