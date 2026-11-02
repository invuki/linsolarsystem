import * as THREE from 'three'
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

/** Shape of public/assets/planets/manifest.json (written by scripts/build_solar_system.py). */
export interface Manifest {
  sun: { radius: number; file: string }
  orbits: string
  planets: Record<string, { file: string; radius: number; orbitRadius: number }>
}

const DIR = '/assets/planets/'
/** Tracks every GLB, texture and the manifest so the loading screen can show real progress. */
export const loadingManager = new THREE.LoadingManager()
const loader = new GLTFLoader(loadingManager).setDRACOLoader(new DRACOLoader().setDecoderPath('/draco/'))

export async function loadManifest(): Promise<Manifest> {
  const url = `${DIR}manifest.json`
  loadingManager.itemStart(url)
  try {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`manifest.json: ${res.status}`)
    return await res.json()
  } finally {
    loadingManager.itemEnd(url)
  }
}

/** Load a GLB and return its meshes by node name. Node transforms are ignored by callers. */
export async function loadMeshes(file: string): Promise<Map<string, THREE.Mesh>> {
  const gltf = await loader.loadAsync(DIR + file)
  const meshes = new Map<string, THREE.Mesh>()
  gltf.scene.traverse((o) => {
    if ((o as THREE.Mesh).isMesh) meshes.set(o.name, o as THREE.Mesh)
  })
  return meshes
}

/** Baked city lights are one static map; fade them out on the sunlit side (Sun is at the origin). */
export function fadeEmissiveInDaylight(mat: THREE.MeshStandardMaterial) {
  mat.onBeforeCompile = (s) => {
    const varyings = '#include <common>\nvarying vec3 vWPos;\nvarying vec3 vWNrm;'
    s.vertexShader = s.vertexShader
      .replace('#include <common>', varyings)
      .replace(
        '#include <begin_vertex>',
        '#include <begin_vertex>\nvWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;\nvWNrm = mat3(modelMatrix) * objectNormal;',
      )
    s.fragmentShader = s.fragmentShader
      .replace('#include <common>', varyings)
      .replace(
        '#include <emissivemap_fragment>',
        '#include <emissivemap_fragment>\ntotalEmissiveRadiance *= 1.0 - smoothstep(-0.12, 0.12, dot(normalize(vWNrm), normalize(-vWPos)));',
      )
  }
}

/** Atmosphere rim colour and strength per planet (matches the Blender rim glow). */
const ATMOSPHERE: Record<string, [number, number]> = {
  Earth: [0x4080ff, 1.2],
  Venus: [0xffcc73, 0.9],
  Jupiter: [0xffd9b3, 0.25],
  Saturn: [0xffe699, 0.25],
  Uranus: [0x80e6ff, 1.0],
  Neptune: [0x4d73ff, 1.2],
}

/** Sharper 4K maps at grazing angles, plus a sun-facing atmosphere rim added to the emissive term. */
export function enhancePlanetMaterial(name: string, mat: THREE.MeshStandardMaterial) {
  for (const t of [mat.map, mat.normalMap, mat.emissiveMap]) if (t) t.anisotropy = 16
  const atmo = ATMOSPHERE[name]
  if (!atmo) return
  const color = new THREE.Color(atmo[0])
  const prev = mat.onBeforeCompile
  mat.onBeforeCompile = (s, r) => {
    prev?.call(mat, s, r)
    s.uniforms.rimColor = { value: color.clone().multiplyScalar(atmo[1]) }
    s.vertexShader = s.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vRimPos;\nvarying vec3 vRimNrm;')
      .replace(
        '#include <begin_vertex>',
        '#include <begin_vertex>\nvRimPos = (modelMatrix * vec4(transformed, 1.0)).xyz;\nvRimNrm = mat3(modelMatrix) * objectNormal;',
      )
    s.fragmentShader = s.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform vec3 rimColor;\nvarying vec3 vRimPos;\nvarying vec3 vRimNrm;')
      .replace(
        '#include <emissivemap_fragment>',
        `#include <emissivemap_fragment>
        vec3 rimN = normalize(vRimNrm);
        float rim = pow(1.0 - saturate(dot(normalize(vViewPosition), normal)), 3.0);
        totalEmissiveRadiance += rimColor * rim * smoothstep(-0.1, 0.4, dot(rimN, normalize(-vRimPos)));`,
      )
  }
  mat.customProgramCacheKey = () => `rim-${name}`
}

/**
 * Mercury/Mars: discard the baked GLB material and rebuild from a NASA map. Fully rough, non-metal,
 * diffuse-only: no normal/bump/emissive/rim, so the Sun's point light gives clean Lambert shading.
 * Maps: Mercury = MESSENGER MDIS global mosaic (PIA15063); Mars = NASA 3D Resources Mars image texture.
 */
const NASA_MAPS: Record<string, string> = {
  Mercury: 'textures/mercury.jpg',
  Mars: 'textures/mars.jpg',
}
const texLoader = new THREE.TextureLoader(loadingManager)

export function nasaRockMaterial(name: string): THREE.MeshStandardMaterial | null {
  const file = NASA_MAPS[name]
  if (!file) return null
  const map = texLoader.load(DIR + file)
  map.colorSpace = THREE.SRGBColorSpace
  map.flipY = false // GLB UVs use the glTF (top-left) convention
  map.anisotropy = 16
  return new THREE.MeshStandardMaterial({ map, roughness: 1, metalness: 0 })
}
