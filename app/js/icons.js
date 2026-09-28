/* Inline SVG icons (stroke = currentColor). Add a new icon by adding a key; use it with x-html="$icon('name')". */
(() => {
  const svg = (body, size = 24) =>
    `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" ` +
    `stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

  HW.icons = {
    home: svg('<path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1z"/>'),
    search: svg('<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>'),
    devices: svg('<rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/>' +
                 '<rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/>'),
    profile: svg('<circle cx="12" cy="8" r="3.5"/><path d="M5 20c1-3.5 3.8-5 7-5s6 1.5 7 5"/>'),
    back: svg('<path d="M15 5l-7 7 7 7"/>'),
    arrowLeft: svg('<path d="M19 12H5m6-6-6 6 6 6"/>'),
    settings: svg('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>'),
    thermometer: svg('<path d="M14 14.8V5a2 2 0 1 0-4 0v9.8a4 4 0 1 0 4 0z"/>'),
    droplet: svg('<path d="M12 3.5s6 6.3 6 10.5a6 6 0 0 1-12 0c0-4.2 6-10.5 6-10.5z"/>'),
    chip: svg('<rect x="7" y="7" width="10" height="10" rx="1.5"/><rect x="10" y="10" width="4" height="4"/>' +
              '<path d="M10 3v4m4-4v4m-4 10v4m4-4v4M3 10h4m-4 4h4m10-4h4m-4 4h4"/>'),
    fridge: svg('<rect x="6" y="3" width="12" height="18" rx="2"/><path d="M6 10h12M9 6v1.5M9 13v2"/>'),
    kettle: svg('<path d="M7 9h10l1.5 11h-13z"/><path d="M9 9V6.5A3 3 0 0 1 15 6.5V9M17.5 11l2-1.5v5L18 16"/>'),
    coffee: svg('<path d="M5 9h12v6a5 5 0 0 1-5 5h-2a5 5 0 0 1-5-5z"/><path d="M17 11h1.5a2 2 0 0 1 0 4H17M9 3v3m4-3v3"/>'),
    oven: svg('<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9h16"/><rect x="7" y="12" width="10" height="5" rx="1"/>'),
    dishwasher: svg('<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M5 8h14"/><circle cx="12" cy="14" r="3.5"/>'),
    tv: svg('<rect x="3.5" y="7" width="17" height="12" rx="2"/><path d="m9 3 3 4 3-4"/>'),
    wifi: svg('<path d="M4.5 10a11 11 0 0 1 15 0M7.5 13.2a6.5 6.5 0 0 1 9 0M10.5 16.3a2 2 0 0 1 3 0"/><circle cx="12" cy="19" r=".6"/>'),
    bulb: svg('<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z"/>'),
    charging: svg('<rect x="3" y="7" width="15" height="10" rx="2"/><path d="M21 11v2M11 8.5 8.5 12h3L9 15.5"/>'),
    washer: svg('<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 7h16M7 5h.01"/><circle cx="12" cy="14" r="4.5"/>'),
    heatpump: svg('<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="12" r="3.5"/><path d="M9 8.5v7M5.5 12h7M15 9h3M15 12h3M15 15h3"/>'),
    laptop: svg('<rect x="5" y="5" width="14" height="10" rx="1.5"/><path d="M3 18.5h18"/>'),
    status: '<svg viewBox="0 0 66 12" width="66" height="12" aria-hidden="true" fill="currentColor">' +
            '<rect x="0" y="8" width="3" height="4" rx="1"/><rect x="5" y="6" width="3" height="6" rx="1"/>' +
            '<rect x="10" y="3" width="3" height="9" rx="1"/><rect x="15" y="0" width="3" height="12" rx="1"/>' +
            '<path d="M24 4.5a9 9 0 0 1 12 0l-1.4 1.4a7 7 0 0 0-9.2 0zM26.8 7.3a5 5 0 0 1 6.4 0L30 10.5z"/>' +
            '<rect x="41.5" y="1" width="21" height="10" rx="3" fill="none" stroke="currentColor"/>' +
            '<rect x="43.5" y="3" width="17" height="6" rx="1.5"/><rect x="63.5" y="4" width="1.5" height="4" rx=".7"/></svg>',
  };
})();
