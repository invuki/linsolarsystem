import * as THREE from 'three'
import { PLANETS, SUN, type PlanetData } from './data'
import { loadingManager, enhancePlanetMaterial, fadeEmissiveInDaylight, loadManifest, nasaRockMaterial, loadMeshes, type Manifest } from './models'

/** A planet in the scene: `pivot` moves along the orbit, `mesh` spins. */
export interface Body {
  name: string
  data: PlanetData | null // null for the Sun
  pivot: THREE.Object3D
  mesh: THREE.Mesh
  radius: number
  phase: number
}

const DEG = Math.PI / 180
/** Visual-only damping so fast spins don't strobe at high time speeds. */
const SPIN_DAMP = 0.1

export class SolarSystem {
  readonly group = new THREE.Group()
  readonly bodies: Body[] = []
  private orbitLines: THREE.Object3D[] = []
  private orbitsVisible = false

  constructor() {
    this.addLights()
    this.addStars()
    this.addSun()
    PLANETS.forEach((p, i) => this.addPlanet(p, i))
  }

  /**
   * Swap the placeholder spheres/rings/orbits for the Blender-made GLBs. Meshes keep the app's own
   * sizes and distances (scaled from the Blender values in the manifest); on failure the placeholders stay.
   */
  async loadModels() {
    // Hold the manager open across the manifest -> GLB handoff so onLoad can't fire between them.
    loadingManager.itemStart('models')
    try {
      await this.loadAll()
    } finally {
      loadingManager.itemEnd('models')
    }
  }

  private async loadAll() {
    const manifest = await loadManifest()
    const jobs = [
      this.applySun(manifest),
      this.applyOrbits(manifest),
      ...PLANETS.map((p) => this.applyPlanet(p, manifest)),
    ]
    const results = await Promise.allSettled(jobs)
    results.forEach((r) => r.status === 'rejected' && console.warn('model load failed:', r.reason))
  }

  private async applySun(m: Manifest) {
    const src = (await loadMeshes(m.sun.file)).get('Sun')!
    const body = this.bodyByName(SUN.name)!
    body.mesh.geometry.dispose()
    body.mesh.geometry = src.geometry
    body.mesh.scale.setScalar(SUN.radius / m.sun.radius)
    // Unlit: the baked emissive map is the Sun's whole look.
    // The real NASA Sun map is already coloured, so no tint.
    body.mesh.material = new THREE.MeshBasicMaterial({
      map: (src.material as THREE.MeshStandardMaterial).emissiveMap,
    })
  }

  private async applyPlanet(p: PlanetData, m: Manifest) {
    const info = m.planets[p.name]
    const meshes = await loadMeshes(info.file)
    const src = meshes.get(p.name)!
    const body = this.bodyByName(p.name)!
    const k = p.radius / info.radius
    body.mesh.geometry.dispose()
    ;(body.mesh.material as THREE.Material).dispose()
    body.mesh.geometry = src.geometry
    const nasa = nasaRockMaterial(p.name)
    body.mesh.material = nasa ?? src.material
    body.mesh.scale.setScalar(k)
    body.mesh.receiveShadow = true // planets never cast: no planet shadows on other planets
    if (p.name === 'Earth') fadeEmissiveInDaylight(src.material as THREE.MeshStandardMaterial)
    if (!nasa) enhancePlanetMaterial(p.name, src.material as THREE.MeshStandardMaterial)

    const clouds = meshes.get(`${p.name}_Clouds`)
    if (clouds) {
      clouds.position.set(0, 0, 0)
      clouds.rotation.set(0, 0, 0)
      clouds.scale.setScalar(1) // inherits k from the planet mesh
      ;(clouds.material as THREE.Material).depthWrite = false
      body.mesh.add(clouds)
    }

    const rings = meshes.get(`${p.name}_Rings`)
    if (rings) {
      const tilt = body.mesh.parent!
      const old = tilt.children.find((c) => c !== body.mesh)
      if (old) tilt.remove(old)
      rings.position.set(0, 0, 0)
      rings.rotation.set(0, 0, 0)
      rings.scale.setScalar(k)
      rings.castShadow = rings.receiveShadow = true // only Saturn's rings cast, and only onto Saturn
      ;(rings.material as THREE.Material).depthWrite = false
      tilt.add(rings) // tilt group, not the spinning mesh
    }
  }

  private async applyOrbits(m: Manifest) {
    const meshes = await loadMeshes(m.orbits)
    const mat = new THREE.MeshBasicMaterial({ color: 0x6f7f99, transparent: true, opacity: 0.6 })
    PLANETS.forEach((p, i) => {
      const tube = meshes.get(`${p.name}_Orbit`)
      if (!tube) return
      const k = p.distance / m.planets[p.name].orbitRadius
      tube.position.set(0, 0, 0)
      tube.rotation.set(0, 0, 0)
      tube.scale.set(k, 1, k)
      tube.material = mat
      tube.visible = this.orbitsVisible
      this.group.remove(this.orbitLines[i])
      this.group.add(tube)
      this.orbitLines[i] = tube
    })
  }

  /** Meshes eligible for click picking. */
  get pickables(): THREE.Object3D[] {
    return this.bodies.map((b) => b.mesh)
  }

  bodyByName(name: string): Body | undefined {
    return this.bodies.find((b) => b.name === name)
  }

  setOrbitsVisible(v: boolean) {
    this.orbitsVisible = v
    this.orbitLines.forEach((l) => (l.visible = v))
  }

  /** Advance to `days` simulated days since start. */
  update(days: number) {
    for (const b of this.bodies) {
      if (!b.data) {
        b.mesh.rotation.y = days * 0.05 // Sun: slow fixed spin
        continue
      }
      const angle = b.phase + (days / b.data.orbitDays) * Math.PI * 2
      b.pivot.position.set(Math.cos(angle) * b.data.distance, 0, -Math.sin(angle) * b.data.distance)
      b.mesh.rotation.y = (days * 24 * Math.PI * 2 * SPIN_DAMP) / b.data.rotationHours
    }
  }

  private addLights() {
    const sun = new THREE.PointLight(0xffffff, 3.5, 0, 0) // at origin = Sun; no decay
    sun.castShadow = true
    sun.shadow.mapSize.set(2048, 2048)
    sun.shadow.camera.near = 1 // outside the Sun sphere
    sun.shadow.camera.far = 200 // Neptune is at 83
    sun.shadow.bias = -0.0005
    sun.shadow.normalBias = 0.02 // world units; planets are ~1-4 across
    sun.shadow.radius = 2
    this.group.add(sun)
    this.group.add(new THREE.AmbientLight(0x404058, 0.7)) // lower fill so shadows and terminators read
  }

  private addStars() {
    const n = 4000
    const pos = new Float32Array(n * 3)
    for (let i = 0; i < n; i++) {
      // random point on a shell, radius 400-900
      const v = new THREE.Vector3().randomDirection().multiplyScalar(400 + Math.random() * 500)
      pos.set([v.x, v.y, v.z], i * 3)
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    this.group.add(
      new THREE.Points(geo, new THREE.PointsMaterial({ color: 0xffffff, size: 1.2, sizeAttenuation: false })),
    )
  }

  private addSun() {
    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(SUN.radius, 48, 48),
      new THREE.MeshBasicMaterial({ color: SUN.color }),
    )
    mesh.name = SUN.name
    this.group.add(mesh)

    // Soft glow: additive sprite with a radial-gradient texture.
    const c = document.createElement('canvas')
    c.width = c.height = 128
    const ctx = c.getContext('2d')!
    const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64)
    g.addColorStop(0, 'rgba(255,200,80,0.9)')
    g.addColorStop(0.35, 'rgba(255,140,40,0.35)')
    g.addColorStop(1, 'rgba(255,100,0,0)')
    ctx.fillStyle = g
    ctx.fillRect(0, 0, 128, 128)
    const glow = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: new THREE.CanvasTexture(c),
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    )
    glow.scale.setScalar(SUN.radius * 5)
    this.group.add(glow)

    this.bodies.push({ name: SUN.name, data: null, pivot: mesh, mesh, radius: SUN.radius, phase: 0 })
  }

  private addPlanet(p: PlanetData, i: number) {
    const pivot = new THREE.Object3D()
    // Axial tilt lives on a parent so the mesh spin stays about the tilted axis.
    const tilt = new THREE.Group()
    tilt.rotation.z = p.tilt * DEG
    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(p.radius, 48, 48),
      new THREE.MeshStandardMaterial({ color: p.color, roughness: 0.9, metalness: 0 }),
    )
    mesh.name = p.name
    mesh.receiveShadow = true
    tilt.add(mesh)
    pivot.add(tilt)

    if (p.rings) {
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(p.radius * 1.4, p.radius * 2.4, 96),
        new THREE.MeshBasicMaterial({ color: 0xcdb98a, side: THREE.DoubleSide, transparent: true, opacity: 0.75 }),
      )
      ring.rotation.x = -Math.PI / 2 // lie flat in the equatorial plane; tilt group tilts it
      tilt.add(ring)
    }
    this.group.add(pivot)

    // Orbit ring in the XZ plane.
    const pts = Array.from({ length: 257 }, (_, k) => {
      const a = (k / 256) * Math.PI * 2
      return new THREE.Vector3(Math.cos(a) * p.distance, 0, Math.sin(a) * p.distance)
    })
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: 0x556070, transparent: true, opacity: 0.6 }),
    )
    line.visible = this.orbitsVisible
    this.group.add(line)
    this.orbitLines.push(line)

    this.bodies.push({ name: p.name, data: p, pivot, mesh, radius: p.radius, phase: (i * 2.3) % (Math.PI * 2) })
  }
}
