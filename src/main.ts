import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import 'bootstrap/dist/css/bootstrap.min.css'
import './index.css'
import { loadingManager } from './models'
import { SolarSystem } from './solarSystem'
import { createUI } from './ui'

const canvas = document.querySelector<HTMLCanvasElement>('#scene')
const uiRoot = document.getElementById('ui')
if (!canvas || !uiRoot) throw new Error('#scene or #ui missing from index.html')
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
renderer.shadowMap.enabled = true
// PCFSoftShadowMap was removed in three r18x; PCFShadowMap is soft there and honours light.shadow.radius.
renderer.shadowMap.type = THREE.PCFShadowMap

const scene = new THREE.Scene()
const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 2000)
camera.position.set(0, 70, 130)

const controls = new OrbitControls(camera, canvas)
controls.enableDamping = true
controls.maxDistance = 600

const system = new SolarSystem()
scene.add(system.group)
system.loadModels() // placeholders show until the Blender GLBs arrive

// --- loading screen ---
const loader = document.getElementById('loader')
const loaderBar = document.getElementById('loader-bar')
const loaderPct = document.getElementById('loader-pct')
loadingManager.onProgress = (_url, loaded, total) => {
  const pct = Math.round((loaded / total) * 100)
  if (loaderBar) loaderBar.style.width = `${pct}%`
  loaderBar?.parentElement?.setAttribute('aria-valuenow', String(pct))
  if (loaderPct) loaderPct.textContent = `${pct}%`
}
loadingManager.onLoad = () => {
  loader?.classList.add('done')
  loader?.addEventListener('transitionend', () => loader.remove(), { once: true })
}

// --- state ---
let paused = false
let daysPerSecond = 1 / 86400 // real time; the speed selector overrides this on load
let days = 0
let focusName: string | null = null
let panelW = 0 // open sidebar width; the view is shifted so the focused planet stays visible
let focusUntil = 0 // ms timestamp; camera distance is eased until then

const ui = createUI(uiRoot, {
  onPause: (p) => (paused = p),
  onSpeed: (s) => (daysPerSecond = s),
  onOrbits: (v) => system.setOrbitsVisible(v),
  onPanel: (w) => {
    panelW = w
    resize()
  },
  onFocus: (name) => {
    focusName = name
    focusUntil = performance.now() + 1500
  },
})

// --- resize ---
function resize() {
  renderer.setSize(innerWidth, innerHeight, false)
  camera.aspect = innerWidth / innerHeight
  // Shift the projection left by half the sidebar so the scene centre sits in the free area.
  if (panelW) camera.setViewOffset(innerWidth, innerHeight, panelW / 2, 0, innerWidth, innerHeight)
  else camera.clearViewOffset()
  camera.updateProjectionMatrix()
}
addEventListener('resize', resize)
resize()

// --- click picking (ignore drags so orbiting doesn't open the modal) ---
const raycaster = new THREE.Raycaster()
let downAt = { x: 0, y: 0 }
canvas.addEventListener('pointerdown', (e) => (downAt = { x: e.clientX, y: e.clientY }))
canvas.addEventListener('pointerup', (e) => {
  if (Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > 4) return
  raycaster.setFromCamera(new THREE.Vector2((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1), camera)
  const hit = raycaster.intersectObjects(system.pickables, false)[0]
  if (!hit) return
  const body = system.bodyByName(hit.object.name)
  if (!body) return
  focusName = body.name
  focusUntil = performance.now() + 1500
  ui.showInfo(body.name, body.data?.blurb, body.data?.info)
})

// --- loop ---
const clock = new THREE.Clock()
const tmp = new THREE.Vector3()
const prevTarget = new THREE.Vector3()

function tick() {
  requestAnimationFrame(tick)
  const dt = Math.min(clock.getDelta(), 0.1)
  if (!paused) days += dt * daysPerSecond
  system.update(days)

  const body = focusName ? system.bodyByName(focusName) : null
  if (body) {
    // Follow the body: ease the target toward it and carry the camera along by the same delta.
    prevTarget.copy(controls.target)
    body.pivot.getWorldPosition(tmp)
    controls.target.lerp(tmp, 0.1)
    camera.position.add(tmp.copy(controls.target).sub(prevTarget))
    // During the transition, also ease the camera to a close viewing distance.
    if (performance.now() < focusUntil) {
      const dist = body.radius * 4 + 4
      const dir = camera.position.clone().sub(controls.target).normalize()
      camera.position.lerp(tmp.copy(controls.target).addScaledVector(dir, dist), 0.06)
    }
  }

  controls.update()
  renderer.render(scene, camera)
}
tick()
