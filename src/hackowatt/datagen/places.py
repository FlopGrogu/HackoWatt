"""Place catalogue: remote cities for trips, local venues, and label -> coordinates for the geolocation stage."""
import hashlib
import math
from dataclasses import dataclass

from .geo import distance_m, shift_m

REF = (52.2297, 21.0122)      # Warsaw centre: local venues below are real Warsaw coordinates, stored relative to it


@dataclass(frozen=True)
class City:
    name: str
    country: str
    lat: float
    lon: float
    mode: str                  # "flight" or "train" from the home city
    partner: str = ""          # fictional partner organisation (work trips)
    tz_shift: int = 0          # local time minus home-city time, hours
    hotel: str = ""
    weight: float = 1.0        # relative frequency of work trips


CITIES = [
    City("Stockholm", "Sweden", 59.3293, 18.0686, "flight", "Nordvolt", 0, "Scandic Continental, Vasagatan 22", 1.3),
    City("Berlin", "Germany", 52.5200, 13.4050, "flight", "Spreewerk Energie", 0, "Hotel Amano, Auguststr. 43", 1.6),
    City("Brussels", "Belgium", 50.8503, 4.3517, "flight", "Flexa Brussels office", 0, "Thon Hotel EU, Rue de la Loi 75", 1.4),
    City("Vienna", "Austria", 48.2082, 16.3738, "flight", "DonauNetz", 0, "Motel One Wien-Staatsoper", 1.0),
    City("Copenhagen", "Denmark", 55.6761, 12.5683, "flight", "Kraftly", 0, "Absalon Hotel, Helgolandsgade 15", 1.0),
    City("London", "UK", 51.5074, -0.1278, "flight", "GridMint", -1, "The Hoxton, Shoreditch", 1.0),
    City("Munich", "Germany", 48.1351, 11.5820, "flight", "Isarwatt", 0, "Motel One München-Sendlinger Tor", 1.0),
    City("Amsterdam", "Netherlands", 52.3676, 4.9041, "flight", "Polderstroom", 0, "Hotel V Nesplein", 0.9),
    City("Paris", "France", 48.8566, 2.3522, "flight", "Lumière Réseau", 0, "Hôtel Le Pigalle", 0.7),
    City("Frankfurt", "Germany", 50.1109, 8.6821, "flight", "MainNetz", 0, "Roomers Frankfurt", 0.7),
    City("Zurich", "Switzerland", 47.3769, 8.5417, "flight", "Limmat Grid", 0, "Hotel Marta, Zähringerstr. 36", 0.5),
    City("Milan", "Italy", 45.4642, 9.1900, "flight", "Rete Verde", 0, "Hotel Berna, Via Napo Torriani 18", 0.5),
    City("Prague", "Czechia", 50.0755, 14.4378, "flight", "Vltava Energo", 0, "Hotel Josef, Rybná 20", 0.5),
    City("Budapest", "Hungary", 47.4979, 19.0402, "flight", "Duna Flex", 0, "Hotel Moments, Andrássy út 8", 0.4),
    City("Helsinki", "Finland", 60.1699, 24.9384, "flight", "Suomi Sähkö", 1, "Hotel Kämp, Pohjoisesplanadi 29", 0.4),
    City("Oslo", "Norway", 59.9139, 10.7522, "flight", "Fjordkraft Lab", 0, "Citybox Oslo, Prinsens gate 8", 0.4),
    City("Dublin", "Ireland", 53.3498, -6.2603, "flight", "Liffey Power", -1, "The Address Dublin, Connolly", 0.3),
    City("Madrid", "Spain", 40.4168, -3.7038, "flight", "Solaria Ibérica", 0, "Hotel Regina, Alcalá 19", 0.3),
    City("Hamburg", "Germany", 53.5511, 9.9937, "flight", "Elbstrom", 0, "Superbude Hamburg St. Pauli", 0.6),
    City("Essen", "Germany", 51.4556, 7.0116, "flight", "Ruhrwatt", 0, "Mintrops Stadt Hotel Margarethenhöhe", 0.4),
    City("Kraków", "Poland", 50.0647, 19.9450, "train", "KrakGrid", 0, "Puro Kraków Kazimierz", 1.4),
    City("Gdańsk", "Poland", 54.3520, 18.6466, "train", "Port of Gdańsk", 0, "PURO Gdańsk Stare Miasto", 1.1),
    City("Wrocław", "Poland", 51.1079, 17.0385, "train", "OdraGrid", 0, "Hotel Focus Wrocław", 0.9),
    City("Poznań", "Poland", 52.4064, 16.9252, "train", "Warta Energia", 0, "Hotel Brovaria, Stary Rynek", 0.8),
    City("Katowice", "Poland", 50.2649, 19.0238, "train", "Silesia Smart Grid", 0, "Hotel Diament Plaza", 0.8),
    City("Szczecin", "Poland", 53.4285, 14.5528, "train", "Baltic Wind Partners", 0, "Radisson Blu Szczecin", 0.3),
    City("Lublin", "Poland", 51.2465, 22.5684, "train", "Lubelski Prąd", 0, "Hotel Vanilla, Kalinowszczyzna", 0.3),
]
# private destinations (not part of the work rotation)
PRIVATE = {c.name: c for c in [
    City("Łódź", "Poland", 51.7592, 19.4560, "train"),
    City("Zakopane", "Poland", 49.2992, 19.9496, "train"),
    City("Sopot", "Poland", 54.4416, 18.5601, "train"),
    City("Mayrhofen", "Austria", 47.1533, 11.8617, "flight"),
    City("Split", "Croatia", 43.5081, 16.4402, "flight"),
    City("Lisbon", "Portugal", 38.7223, -9.1393, "flight", tz_shift=-1),
    City("Rome", "Italy", 41.9028, 12.4964, "flight"),
    City("Porto", "Portugal", 41.1579, -8.6291, "flight", tz_shift=-1),
    City("Giżycko", "Poland", 54.0378, 21.7654, "car"),
    City("Kazimierz Dolny", "Poland", 51.3220, 21.9500, "car"),
]}
BY_NAME = {c.name: c for c in CITIES}
BY_NAME.update(PRIVATE)
# Paul lives in Berlin
PAUL_CITY = BY_NAME["Berlin"]

# --- local venues: (label, real Warsaw latitude, longitude). {city} is replaced by the configured city. ---
LOCAL = {
    "office": ("Warsaw Spire, pl. Europejski 1, {city}", 52.2318, 20.9846),
    "airport": ("{city} Airport ({iata})", 52.1657, 20.9671),
    "station": ("{city} Central Station", 52.2287, 21.0033),
    "gym": ("Bouldering gym, ul. Puławska (Mokotów)", 52.2029, 21.0203),
    "run": ("Pole Mokotowskie", 52.2116, 20.9954),
    "park": ("Łazienki Park", 52.2153, 21.0350),
    "yoga": ("Joga Studio, ul. Mokotowska 51", 52.2226, 21.0177),
    "pool": ("Pływalnia Inflancka", 52.2570, 20.9930),
    "padel": ("Padel Club Wola", 52.2380, 20.9700),
    "physio": ("Physio clinic, ul. Mokotowska 49", 52.2232, 21.0182),
    "dentist": ("Dental clinic, ul. Hoża 42", 52.2224, 21.0153),
    "gp": ("LuxMed, ul. Chmielna 85", 52.2295, 21.0011),
    "hair": ("Salon Fryzjerski, ul. Nowogrodzka 18", 52.2277, 21.0100),
    "charlotte": ("Charlotte, pl. Zbawiciela", 52.2200, 21.0182),
    "koszyki": ("Hala Koszyki, ul. Koszykowa 63", 52.2266, 21.0192),
    "gwardii": ("Hala Gwardii", 52.2447, 21.0009),
    "relaks": ("Kawiarnia Relaks, ul. Puławska 48", 52.2103, 21.0202),
    "beirut": ("Beirut Hummus & Music Bar, ul. Poznańska 12", 52.2247, 21.0182),
    "nolita": ("Nolita, ul. Wilcza 46", 52.2235, 21.0194),
    "pardon": ("Pardon, To Tu, pl. Grzybowski", 52.2317, 21.0046),
    "browar": ("Browar Warszawski", 52.2317, 20.9916),
    "studio": ("Bar Studio, PKiN", 52.2318, 21.0060),
    "hydro": ("Klub Hydrozagadka, ul. 11 Listopada 22", 52.2510, 21.0500),
    "kino": ("Kino Muranów", 52.2496, 20.9989),
    "filharmonia": ("Filharmonia Narodowa, ul. Jasna 5", 52.2386, 21.0185),
    "teatr": ("Teatr Polski, ul. Karasia 2", 52.2385, 21.0195),
    "elektrownia": ("Elektrownia Powiśle, ul. Dobra 42", 52.2337, 21.0287),
    "museum": ("Muzeum Narodowe, Al. Jerozolimskie 3", 52.2318, 21.0247),
    "polin": ("POLIN Museum, ul. Mordechaja Anielewicza 6", 52.2497, 20.9932),
    "praga": ("Tomek's flat, Praga", 52.2500, 21.0450),
    "poniatowka": ("Plaża Poniatówka", 52.2340, 21.0400),
    "szczesliwicki": ("Park Szczęśliwicki", 52.2110, 20.9600),
    "rondo": ("Rondo Dmowskiego", 52.2300, 21.0181),
    "oldtown": ("Rynek Starego Miasta", 52.2497, 21.0122),
    "nowyswiat": ("Nowy Świat", 52.2320, 21.0190),
    "vistula": ("Vistula boulevards", 52.2400, 21.0320),
    "pkin": ("Palace of Culture and Science", 52.2318, 21.0060),
    "market": ("Hala Mirowska market", 52.2367, 21.0006),
    "mokotow_c": ("Mokotów cinema Kinoteka", 52.2318, 21.0060),
    "zoo": ("Warsaw Zoo", 52.2530, 21.0270),
    "bike": ("Vistula bike path", 52.2200, 21.0400),
    "lakeside": ("Jeziorko Czerniakowskie", 52.1960, 21.0600),
}


class Places:
    def __init__(self, cfg):
        self.cfg = cfg
        self.label = {}
        self._coord = {}
        for key, (tpl, lat, lon) in LOCAL.items():
            label = tpl.format(city=cfg.city, iata=cfg.iata)
            self.label[key] = label
            self._coord[label] = (cfg.lat + (lat - REF[0]), cfg.lon + (lon - REF[1]))
        self.home_label = f"Home – ul. Chmielna 71, {cfg.city}"
        self._coord[self.home_label] = cfg.home
        self._by_city = sorted(((c.name, c) for c in list(CITIES) + list(PRIVATE.values())), key=lambda x: -len(x[0]))

    def scatter(self, label, center, radius_m):
        """Stable pseudo-random position around `center` (the same label always lands on the same spot)."""
        h = int(hashlib.md5(label.encode()).hexdigest(), 16)
        r = radius_m * math.sqrt((h % 10007) / 10007)
        a = 2 * math.pi * ((h // 10007) % 10007) / 10007
        return shift_m(center, r * math.cos(a), r * math.sin(a))

    def coord(self, label):
        """Coordinates for a calendar location string."""
        if label in self._coord:
            return self._coord[label]
        low = label.lower()
        radius = 12000 if "airport" in low else 600 if "station" in low else 2500
        if self.cfg.city.lower() in low:
            return self.scatter(label, (self.cfg.lat, self.cfg.lon), max(radius, 4000 if radius == 2500 else radius))
        for name, c in self._by_city:
            if name.lower() in low:
                return self.scatter(label, (c.lat, c.lon), radius)
        return self.scatter(label, (self.cfg.lat, self.cfg.lon), 5000)

    def city_center(self, label):
        """Centre of the city named in a location string, or None."""
        low = label.lower()
        for name, c in self._by_city:
            if name.lower() in low:
                return (c.lat, c.lon)
        return None

    def is_local(self, label):
        return label in self._coord or self.cfg.city.lower() in label.lower() or not self.city_center(label)

    def distance(self, a, b):
        return distance_m(self.coord(a), self.coord(b))
