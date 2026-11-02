import { Offcanvas } from 'bootstrap'
import { PLANETS, SUN_INFO, type BodyInfo } from './data'

export interface UIHandlers {
  onPause(paused: boolean): void
  onSpeed(daysPerSecond: number): void
  onOrbits(visible: boolean): void
  onFocus(name: string): void
  /** Sidebar width in px while open, 0 when closed, so the scene can re-centre in the free area. */
  onPanel(widthPx: number): void
}

/** Speed options as multiples of real time (1x = 1 simulated second per second). */
const SPEEDS: [multiplier: number, label: string][] = [
  [1, 'Real-time'],
  [60, '60x (1 min/s)'],
  [3600, '3,600x (1 hr/s)'],
  [86400, '86,400x (1 day/s)'],
  [864000, '864,000x (10 days/s)'],
  [8640000, '8,640,000x (100 days/s)'],
  [86400000, '86,400,000x (1,000 days/s)'],
]
const DEFAULT_SPEED = 1
const SECONDS_PER_DAY = 86400

/** Builds the Bootstrap control bar + planet modal and wires them to handlers. */
export function createUI(root: HTMLElement, h: UIHandlers) {
  const focusItems = ['Sun', ...PLANETS.map((p) => p.name)]
    .map((n) => `<li><button class="dropdown-item" data-focus="${n}">${n}</button></li>`)
    .join('')

  root.innerHTML = `
    <nav class="navbar navbar-expand-lg navbar-dark bg-transparent fixed-top glass-nav">
      <div class="container-fluid">
        <span class="navbar-brand">Solar System</span>
        <button class="navbar-toggler" data-bs-toggle="collapse" data-bs-target="#controls" aria-label="Toggle controls">
          <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="controls">
          <div class="d-flex flex-wrap align-items-center gap-3 ms-lg-auto py-2 py-lg-0">
            <button id="pause" class="btn btn-sm btn-outline-light rounded-pill px-3" style="min-width: 5.5rem">Pause</button>
            <label class="d-flex align-items-center gap-2 mb-0 small text-nowrap">
              Speed
              <select id="speed" class="form-select form-select-sm w-auto glass-input">
                ${SPEEDS.map(([m, label]) => `<option value="${m}"${m === DEFAULT_SPEED ? ' selected' : ''}>${label}</option>`).join('')}
              </select>
            </label>
            <div class="form-check form-switch mb-0">
              <input id="orbits" class="form-check-input" type="checkbox" role="switch">
              <label class="form-check-label small" for="orbits">Orbits</label>
            </div>
            <div class="dropdown">
              <button class="btn btn-sm btn-light rounded-pill px-3 dropdown-toggle" data-bs-toggle="dropdown">Focus</button>
              <ul class="dropdown-menu dropdown-menu-end dropdown-menu-dark">${focusItems}</ul>
            </div>
          </div>
        </div>
      </div>
    </nav>

    <div class="offcanvas offcanvas-end glass-panel" id="planet-panel" tabindex="-1" aria-labelledby="planet-title" data-bs-backdrop="false" data-bs-scroll="true" style="top: 56px">
      <div class="offcanvas-header">
        <h2 class="offcanvas-title h4" id="planet-title"></h2>
        <button class="btn-close" data-bs-dismiss="offcanvas" aria-label="Close"></button>
      </div>
      <div class="offcanvas-body">
        <p id="planet-blurb"></p>
        <dl class="mb-0" id="planet-facts"></dl>
      </div>
    </div>`

  const $ = <T extends HTMLElement>(sel: string): T => {
    const el = root.querySelector<T>(sel)
    if (!el) throw new Error(`UI element missing: ${sel}`)
    return el
  }
  const pauseBtn = $<HTMLButtonElement>('#pause')
  const speed = $<HTMLSelectElement>('#speed')
  const panelEl = $('#planet-panel')
  const panel = new Offcanvas(panelEl)
  panelEl.addEventListener('shown.bs.offcanvas', () => h.onPanel(panelEl.offsetWidth))
  panelEl.addEventListener('hidden.bs.offcanvas', () => h.onPanel(0))

  let paused = false
  pauseBtn.onclick = () => {
    paused = !paused
    pauseBtn.textContent = paused ? 'Resume' : 'Pause'
    h.onPause(paused)
  }

  speed.onchange = () => h.onSpeed(Number(speed.value) / SECONDS_PER_DAY)
  speed.onchange(new Event('change'))

  $<HTMLInputElement>('#orbits').onchange = (e) => h.onOrbits((e.target as HTMLInputElement).checked)

  root.querySelectorAll<HTMLElement>('[data-focus]').forEach((el) => {
    el.onclick = () => h.onFocus(el.dataset.focus!)
  })

  /** Fill and show the info sidebar. Sun has no PlanetData, so pass undefined. */
  function showInfo(name: string, blurb?: string, info: BodyInfo = SUN_INFO.info) {
    $('#planet-title').textContent = name
    $('#planet-blurb').textContent = blurb ?? SUN_INFO.blurb
    const rows: [string, string][] = [
      ['Mean radius', info.radiusKm],
      ['Mass', info.mass],
      ['Distance from Sun', info.distance],
      ['Orbital period', info.orbitalPeriod],
      ['Rotation period', info.rotation],
      ['Atmosphere', info.atmosphere],
      ['Exploration', info.exploration],
    ]
    $('#planet-facts').innerHTML = rows
      .map(([k, v]) => `<dt class="text-body-secondary small text-uppercase">${k}</dt><dd>${v}</dd>`)
      .join('')
    panel.show()
  }

  return { showInfo }
}
