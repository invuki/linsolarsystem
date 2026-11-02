/** Reference values from NASA planetary/sun fact sheets (nssdc.gsfc.nasa.gov, science.nasa.gov). */
export interface BodyInfo {
  radiusKm: string // mean radius
  mass: string
  distance: string // mean distance from the Sun
  orbitalPeriod: string
  rotation: string // sidereal rotation period
  atmosphere: string
  exploration: string
}

/** Static planet data. Sizes and distances are NOT to scale (compressed for visibility). */
export interface PlanetData {
  name: string
  color: number
  radius: number // scene units (exaggerated)
  distance: number // scene units from Sun
  orbitDays: number // real orbital period, Earth days
  rotationHours: number // real sidereal rotation; negative = retrograde
  tilt: number // axial tilt, degrees
  info: BodyInfo
  blurb: string
  rings?: boolean
}

export const SUN = { name: 'Sun', color: 0xffcc33, radius: 6 }

export const PLANETS: PlanetData[] = [
  {
    name: 'Mercury', color: 0xa8a39d, radius: 0.8, distance: 11, orbitDays: 88, rotationHours: 1407.6, tilt: 0.03,
    blurb: 'Smallest planet and closest to the Sun. Almost no atmosphere, so temperatures swing wildly.',
    info: {
      radiusKm: '2,439.7 km',
      mass: '3.30 × 10²³ kg',
      distance: '57.9 million km (0.39 AU)',
      orbitalPeriod: '87.97 Earth days',
      rotation: '58.6 Earth days (1,407.6 h)',
      atmosphere: 'Near-vacuum exosphere: oxygen, sodium, hydrogen, helium, potassium',
      exploration: 'Mariner 10 flew by in 1974–75. MESSENGER orbited 2011–2015 and mapped the whole surface. BepiColombo (ESA/JAXA) arrives in 2026. Surface is cratered like the Moon; permanently shadowed polar craters hold water ice.',
    },
  },
  {
    name: 'Venus', color: 0xe3bb76, radius: 1.4, distance: 16, orbitDays: 224.7, rotationHours: -5832.5, tilt: 177.4,
    blurb: 'Hottest planet thanks to a runaway greenhouse effect. Rotates backwards, very slowly.',
    info: {
      radiusKm: '6,051.8 km',
      mass: '4.87 × 10²⁴ kg',
      distance: '108.2 million km (0.72 AU)',
      orbitalPeriod: '224.7 Earth days',
      rotation: '243 Earth days, retrograde (−5,832.5 h)',
      atmosphere: 'About 96.5% carbon dioxide, 3.5% nitrogen, traces of sulfur dioxide. Surface pressure ~92 bar',
      exploration: "Venera 7 (USSR, 1970) made the first landing on another planet. NASA's Magellan radar-mapped 98% of the surface in 1990–94. Surface is about 464 °C, hot enough to melt lead.",
    },
  },
  {
    name: 'Earth', color: 0x2f6fdd, radius: 1.5, distance: 22, orbitDays: 365.25, rotationHours: 23.93, tilt: 23.4,
    blurb: 'The only known world with life. About 71% of its surface is water.',
    info: {
      radiusKm: '6,371.0 km',
      mass: '5.97 × 10²⁴ kg',
      distance: '149.6 million km (1 AU)',
      orbitalPeriod: '365.25 days',
      rotation: '23.93 hours',
      atmosphere: 'About 78% nitrogen, 21% oxygen, 0.9% argon, variable water vapor',
      exploration: 'Only known world with life and liquid surface water. Observed continuously by Earth-observing satellites such as Landsat (since 1972) and the ISS (since 2000).',
    },
  },
  {
    name: 'Mars', color: 0xc1440e, radius: 1.1, distance: 28, orbitDays: 687, rotationHours: 24.6, tilt: 25.2,
    blurb: 'The red planet. Home to Olympus Mons, the tallest volcano in the solar system.',
    info: {
      radiusKm: '3,389.5 km',
      mass: '6.42 × 10²³ kg',
      distance: '227.9 million km (1.52 AU)',
      orbitalPeriod: '687 Earth days',
      rotation: '24.6 hours',
      atmosphere: "About 95% carbon dioxide, 2.8% nitrogen, 2% argon. Surface pressure under 1% of Earth's",
      exploration: 'Visited by orbiters and rovers since Mariner 4 (1965). Perseverance and the Ingenuity helicopter reached Jezero crater in 2021. Olympus Mons, about 22 km high, is the tallest known volcano in the solar system.',
    },
  },
  {
    name: 'Jupiter', color: 0xd8a56b, radius: 3.8, distance: 41, orbitDays: 4333, rotationHours: 9.93, tilt: 3.1,
    blurb: 'Largest planet; a gas giant with a storm, the Great Red Spot, wider than Earth.',
    info: {
      radiusKm: '69,911 km',
      mass: '1.90 × 10²⁷ kg',
      distance: '778.5 million km (5.20 AU)',
      orbitalPeriod: '11.86 Earth years',
      rotation: '9.93 hours',
      atmosphere: 'About 90% hydrogen, 10% helium, traces of methane, ammonia and water',
      exploration: 'Galileo orbited 1995–2003; Juno has orbited since 2016. The Great Red Spot is a storm wider than Earth that has lasted centuries. Europa and Ganymede are likely to hold subsurface oceans.',
    },
  },
  {
    name: 'Saturn', color: 0xe8d29a, radius: 3.2, distance: 56, orbitDays: 10759, rotationHours: 10.7, tilt: 26.7, rings: true,
    blurb: 'Famous for its bright ring system, made mostly of ice particles. Less dense than water.',
    info: {
      radiusKm: '58,232 km',
      mass: '5.68 × 10²⁶ kg',
      distance: '1.43 billion km (9.58 AU)',
      orbitalPeriod: '29.4 Earth years',
      rotation: '10.7 hours',
      atmosphere: 'About 96% hydrogen, 3% helium, traces of methane and ammonia',
      exploration: 'Cassini orbited 2004–2017 and its Huygens probe landed on Titan in 2005. Rings are mostly water ice. Average density is lower than water. Enceladus vents water from a subsurface ocean.',
    },
  },
  {
    name: 'Uranus', color: 0x8fd8e0, radius: 2.2, distance: 70, orbitDays: 30687, rotationHours: -17.2, tilt: 97.8,
    blurb: 'An ice giant that rolls around the Sun on its side.',
    info: {
      radiusKm: '25,362 km',
      mass: '8.68 × 10²⁵ kg',
      distance: '2.87 billion km (19.2 AU)',
      orbitalPeriod: '84 Earth years',
      rotation: '17.2 hours, retrograde',
      atmosphere: 'About 83% hydrogen, 15% helium, 2% methane (gives the cyan colour)',
      exploration: 'Only visited by Voyager 2, in January 1986. Axial tilt of 97.8° means it orbits nearly on its side. Has 13 known rings and 28 known moons.',
    },
  },
  {
    name: 'Neptune', color: 0x3d5fe0, radius: 2.1, distance: 83, orbitDays: 60190, rotationHours: 16.1, tilt: 28.3,
    blurb: 'Farthest planet, with the fastest winds in the solar system (over 2,000 km/h).',
    info: {
      radiusKm: '24,622 km',
      mass: '1.02 × 10²⁶ kg',
      distance: '4.50 billion km (30.1 AU)',
      orbitalPeriod: '164.8 Earth years',
      rotation: '16.1 hours',
      atmosphere: 'About 80% hydrogen, 19% helium, 1.5% methane',
      exploration: 'Only visited by Voyager 2, in August 1989. Winds exceed 2,000 km/h, the fastest measured on any planet. Triton, its largest moon, orbits retrograde and is likely a captured Kuiper belt object.',
    },
  },
]

export const SUN_INFO: { blurb: string; info: BodyInfo } = {
  blurb: 'The star at the centre of our solar system, holding 99.86% of its mass.',
  info: {
    radiusKm: '695,700 km',
    mass: '1.99 × 10³⁰ kg',
    distance: '0 (centre); Earth orbits at 149.6 million km',
    orbitalPeriod: 'About 230 million years around the galactic centre',
    rotation: 'About 25 days at the equator, 35 days at the poles',
    atmosphere: 'Plasma of about 73% hydrogen and 25% helium by mass; photosphere ~5,500 °C, core ~15 million °C',
    exploration: 'Studied by SOHO (1995), SDO (2010) and Parker Solar Probe, which in 2021 became the first spacecraft to fly through the corona. About 4.6 billion years old.',
  },
}
