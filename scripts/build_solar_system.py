"""Build the solar system in Blender and export one optimized GLB per body.

Run through Blender MCP in stages:
    ns = runpy.run_path(".../build_solar_system.py")
    ns["stage_scene"](); ns["stage_planets"](); ns["stage_validate"]()
    ns["bake_and_export"]("Earth")  # per body, plus "Orbits"
    ns["write_manifest"]()

Procedural shaders do not survive glTF, so each body is baked (Cycles EMIT/NORMAL)
to textures and exported with a simple Principled material built from them.
"""
import json
import math
import os

import bmesh
import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "public", "assets", "planets")

SUN_RADIUS = 4.0
# name: (radius, orbit radius, axial tilt deg, start angle deg)
PLANETS = {
    "Mercury": (0.38, 9.0, 0.03, 15),
    "Venus": (0.95, 13.0, 177.4, 75),
    "Earth": (1.0, 18.0, 23.4, 140),
    "Mars": (0.53, 24.0, 25.2, 200),
    "Jupiter": (2.8, 38.0, 3.1, 255),
    "Saturn": (2.4, 54.0, 26.7, 305),
    "Uranus": (1.6, 68.0, 97.8, 345),
    "Neptune": (1.55, 80.0, 28.3, 50),
}
RING_INNER, RING_OUTER = 1.25, 2.3  # x Saturn radius
CLOUD_SCALE = 1.015
TEX_SIZE = {n: (4096, 2048) for n in ("Sun", "Mercury", "Venus", "Earth", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune")}


# ---------------------------------------------------------------- node helpers
def make(nt, idname, inputs=None, **attrs):
    n = nt.nodes.new(idname)
    for k, v in attrs.items():
        setattr(n, k, v)
    for k, v in (inputs or {}).items():
        put(nt, n.inputs[k], v)
    return n


def put(nt, sock, v):
    if isinstance(v, bpy.types.NodeSocket):
        nt.links.new(v, sock)
    else:
        sock.default_value = v


def rgba(c):
    if isinstance(c, (int, float)):
        return (c, c, c, 1.0)
    return tuple(c) + (1.0,) if len(c) == 3 else tuple(c)


def math_(nt, op, a, b=None, c=None, clamp=False):
    ins = {0: a}
    if b is not None:
        ins[1] = b
    if c is not None:
        ins[2] = c
    return make(nt, "ShaderNodeMath", ins, operation=op, use_clamp=clamp).outputs[0]


def vmath(nt, op, a, b=None):
    ins = {0: a}
    if b is not None:
        ins[1] = b
    n = make(nt, "ShaderNodeVectorMath", ins, operation=op)
    return n.outputs["Value"] if op in ("LENGTH", "DOT_PRODUCT", "DISTANCE") else n.outputs["Vector"]


def noise(nt, vec, scale, detail=5.0, rough=0.5, distortion=0.0, dims="3D", w=None):
    ins = {"Scale": scale, "Detail": detail, "Roughness": rough, "Distortion": distortion}
    if vec is not None:
        ins["Vector"] = vec
    if w is not None:
        ins["W"] = w
    return make(nt, "ShaderNodeTexNoise", ins, noise_dimensions=dims).outputs["Fac"]


def voronoi_node(nt, vec, scale, rand=1.0):
    return make(nt, "ShaderNodeTexVoronoi", {"Vector": vec, "Scale": scale, "Randomness": rand},
                voronoi_dimensions="3D", feature="F1")


def mapr(nt, v, a, b, c=0.0, d=1.0, interp="LINEAR"):
    return make(nt, "ShaderNodeMapRange",
                {"Value": v, "From Min": a, "From Max": b, "To Min": c, "To Max": d},
                interpolation_type=interp, clamp=True).outputs["Result"]


def ramp(nt, fac, stops):
    n = make(nt, "ShaderNodeValToRGB", {"Fac": fac})
    el = n.color_ramp.elements
    el[0].position, el[0].color = stops[0][0], rgba(stops[0][1])
    el[1].position, el[1].color = stops[-1][0], rgba(stops[-1][1])
    for pos, col in stops[1:-1]:
        el.new(pos).color = rgba(col)
    return n.outputs["Color"]


def wsum(nt, terms):
    acc = None
    for sock, w in terms:
        t = math_(nt, "MULTIPLY", sock, w)
        acc = t if acc is None else math_(nt, "ADD", acc, t)
    return acc


def mix_rgb(nt, fac, a, b):
    n = make(nt, "ShaderNodeMix", data_type="RGBA")
    put(nt, n.inputs[0], fac)
    ca, cb = [s for s in n.inputs if s.type == "RGBA"][:2]
    put(nt, ca, rgba(a) if not isinstance(a, bpy.types.NodeSocket) else a)
    put(nt, cb, rgba(b) if not isinstance(b, bpy.types.NodeSocket) else b)
    return [s for s in n.outputs if s.type == "RGBA"][0]


def sep_z(nt, vec):
    return make(nt, "ShaderNodeSeparateXYZ", {"Vector": vec}).outputs["Z"]


def unit_coords(nt):
    """Generated coords remapped to [-1, 1]: radius-independent sphere coordinates."""
    tc = make(nt, "ShaderNodeTexCoord")
    sub = vmath(nt, "SUBTRACT", tc.outputs["Generated"], (0.5, 0.5, 0.5))
    return vmath(nt, "MULTIPLY", sub, (2.0, 2.0, 2.0))


def tag(nt, name, sock):
    """Named reroute the baker looks up."""
    r = nt.nodes.new("NodeReroute")
    r.name = name
    nt.links.new(sock, r.inputs[0])


def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes.clear()
    return m, m.node_tree


def finish(nt, bsdf):
    out = make(nt, "ShaderNodeOutputMaterial")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])


def bsdf_(nt, **ins):
    return make(nt, "ShaderNodeBsdfPrincipled", {k.replace("_", " "): v for k, v in ins.items()})


def blended(m):
    try:
        m.surface_render_method = "BLENDED"
    except Exception:
        pass


# ------------------------------------------------------------------- materials
def mat_sun():
    m, nt = new_mat("Sun_proc")
    U = unit_coords(nt)
    gran = wsum(nt, [(noise(nt, U, 12, 8, 0.6), 0.7), (noise(nt, U, 40, 4, 0.5), 0.3)])
    tone = ramp(nt, gran, [(0.2, 0.55), (0.55, 0.9), (0.8, 1.0)])
    bb = make(nt, "ShaderNodeBlackbody", {"Temperature": 5700.0})
    col = vmath(nt, "MULTIPLY", bb.outputs["Color"], tone)
    tag(nt, "BAKE_emission", col)
    finish(nt, bsdf_(nt, Base_Color=(0, 0, 0, 1), Roughness=1.0, Emission_Color=col, Emission_Strength=6.0))
    return m


def mat_rocky(name, stops, crater_scale, bump_strength, caps=False):
    m, nt = new_mat(name)
    U = unit_coords(nt)
    big = noise(nt, U, 2.2, 8, 0.55)
    fine = noise(nt, U, 22, 6, 0.6)
    prof = [(0.0, 0.12), (0.12, 0.18), (0.2, 0.85), (0.3, 0.45), (1.0, 0.5)]
    c1 = ramp(nt, voronoi_node(nt, U, crater_scale).outputs["Distance"], prof)
    shifted = vmath(nt, "ADD", U, (3.1, 1.7, 5.3))
    c2 = ramp(nt, voronoi_node(nt, shifted, crater_scale * 3.1).outputs["Distance"], prof)
    height = wsum(nt, [(c1, 0.45), (c2, 0.2), (big, 0.25), (fine, 0.1)])
    col = ramp(nt, wsum(nt, [(big, 0.55), (height, 0.45)]), stops)
    if caps:
        z = math_(nt, "ABSOLUTE", sep_z(nt, U))
        wob = math_(nt, "MULTIPLY", math_(nt, "SUBTRACT", fine, 0.5), 0.1)
        cap = mapr(nt, math_(nt, "ADD", z, wob), 0.88, 0.94)
        col = mix_rgb(nt, cap, col, (0.9, 0.92, 0.95, 1))
    bump = make(nt, "ShaderNodeBump", {"Strength": bump_strength, "Distance": 0.1, "Height": height})
    tag(nt, "BAKE_color", col)
    finish(nt, bsdf_(nt, Base_Color=col, Roughness=0.95, Normal=bump.outputs["Normal"]))
    return m


def mat_venus():
    m, nt = new_mat("Venus_proc")
    U = unit_coords(nt)
    st = vmath(nt, "MULTIPLY", U, (1.0, 1.0, 2.2))
    swirl = noise(nt, st, 3.0, 10, 0.55, 2.0)
    z = sep_z(nt, U)
    band = mapr(nt, math_(nt, "SINE", math_(nt, "ADD", math_(nt, "MULTIPLY", z, 7.0),
                                           math_(nt, "MULTIPLY", math_(nt, "SUBTRACT", swirl, 0.5), 3.0))),
                -1, 1)
    v = wsum(nt, [(swirl, 0.6), (band, 0.4)])
    col = ramp(nt, v, [(0.25, (0.5, 0.28, 0.08)), (0.55, (0.82, 0.55, 0.22)), (0.8, (0.95, 0.8, 0.48))])
    tag(nt, "BAKE_color", col)
    finish(nt, bsdf_(nt, Base_Color=col, Roughness=0.5))
    return m


def mat_earth():
    m, nt = new_mat("Earth_proc")
    U = unit_coords(nt)
    land_n = noise(nt, U, 1.9, 10, 0.55, 0.25)
    mask = ramp(nt, land_n, [(0.0, 0.0), (0.505, 0.0), (0.525, 1.0), (1.0, 1.0)])
    var = noise(nt, U, 5.5, 7, 0.6)
    land = ramp(nt, var, [(0.0, (0.06, 0.14, 0.03)), (0.45, (0.16, 0.26, 0.07)),
                          (0.7, (0.36, 0.28, 0.12)), (1.0, (0.5, 0.45, 0.33))])
    sea = ramp(nt, land_n, [(0.0, (0.004, 0.02, 0.1)), (0.4, (0.01, 0.06, 0.25)),
                            (0.5, (0.04, 0.22, 0.5)), (0.52, (0.08, 0.3, 0.55))])
    surf = mix_rgb(nt, mask, sea, land)
    lat = math_(nt, "ABSOLUTE", sep_z(nt, U))
    ice = mapr(nt, math_(nt, "ADD", lat, math_(nt, "MULTIPLY", math_(nt, "SUBTRACT", var, 0.5), 0.15)),
               0.9, 0.96)
    col = mix_rgb(nt, ice, surf, (0.92, 0.95, 1.0, 1))
    solid = math_(nt, "MAXIMUM", mask, ice)
    rough = mapr(nt, solid, 0, 1, 0.08, 0.85)  # oceans glossy, land matte
    relief = math_(nt, "MULTIPLY", wsum(nt, [(var, 0.5), (noise(nt, U, 30, 6, 0.6), 0.5)]), solid)
    bump = make(nt, "ShaderNodeBump", {"Strength": 0.35, "Distance": 0.05, "Height": relief})

    # city lights: land, no ice, clustered; faded in only on the side facing away from the Sun
    pts = ramp(nt, noise(nt, U, 38, 3, 0.5), [(0.55, 0.0), (0.68, 1.0)])
    clump = ramp(nt, noise(nt, U, 5, 4, 0.5), [(0.5, 0.0), (0.62, 1.0)])
    lights = math_(nt, "MULTIPLY", math_(nt, "MULTIPLY", mask, math_(nt, "SUBTRACT", 1.0, ice)),
                   math_(nt, "MULTIPLY", pts, clump))
    lights_rgb = mix_rgb(nt, lights, (0, 0, 0, 1), (1.0, 0.72, 0.35, 1))
    geo = make(nt, "ShaderNodeNewGeometry")
    to_sun = vmath(nt, "NORMALIZE", vmath(nt, "MULTIPLY", geo.outputs["Position"], (-1.0, -1.0, -1.0)))
    facing = vmath(nt, "DOT_PRODUCT", geo.outputs["Normal"], to_sun)
    night = mapr(nt, facing, 0.12, -0.12)
    tag(nt, "BAKE_color", col)
    tag(nt, "BAKE_emission", lights_rgb)
    finish(nt, bsdf_(nt, Base_Color=col, Roughness=rough, Normal=bump.outputs["Normal"],
                     Emission_Color=lights_rgb, Emission_Strength=math_(nt, "MULTIPLY", night, 3.0)))
    return m


def mat_clouds():
    m, nt = new_mat("Earth_Clouds_proc")
    U = unit_coords(nt)
    st = vmath(nt, "MULTIPLY", U, (1.0, 1.0, 2.2))
    v = wsum(nt, [(noise(nt, st, 3.4, 12, 0.55, 0.9), 0.75), (noise(nt, U, 9, 6, 0.5), 0.25)])
    alpha = mapr(nt, v, 0.56, 0.8, 0.0, 0.95, "SMOOTHSTEP")
    tag(nt, "BAKE_alpha", alpha)
    finish(nt, bsdf_(nt, Base_Color=(1, 1, 1, 1), Roughness=1.0, Alpha=alpha))
    blended(m)
    return m


def spot_mask(nt, U, lat_deg, lon_deg, scales):
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    c = (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))
    nn = make(nt, "ShaderNodeTexNoise", {"Vector": U, "Scale": 7.0, "Detail": 3.0, "Distortion": 0.5})
    wob = vmath(nt, "MULTIPLY", vmath(nt, "SUBTRACT", nn.outputs["Color"], (0.5, 0.5, 0.5)),
                (0.25, 0.25, 0.25))
    v = vmath(nt, "MULTIPLY", vmath(nt, "ADD", vmath(nt, "SUBTRACT", U, c), wob), scales)
    return mapr(nt, vmath(nt, "LENGTH", v), 1.0, 0.55)


def mat_gas(name, stops, freq, warp, nscale, spots=(), fine=0.1, rough=0.65):
    """Latitude bands: sin(z * freq + turbulence), turbulence stretched along X/Y."""
    m, nt = new_mat(name)
    U = unit_coords(nt)
    turb = noise(nt, vmath(nt, "MULTIPLY", U, (0.55, 0.55, 3.5)), nscale, 6, 0.55)
    fin = noise(nt, vmath(nt, "MULTIPLY", U, (0.4, 0.4, 5.0)), nscale * 4, 5, 0.5)
    wz = math_(nt, "ADD", math_(nt, "MULTIPLY", sep_z(nt, U), freq),
               math_(nt, "MULTIPLY", math_(nt, "SUBTRACT", turb, 0.5), warp))
    s = mapr(nt, math_(nt, "SINE", wz), -1, 1)
    col = ramp(nt, wsum(nt, [(s, 1.0 - fine), (fin, fine)]), stops)
    for lat, lon, scales, spot_stops in spots:
        col = mix_rgb(nt, spot_mask(nt, U, lat, lon, scales), col, ramp(nt, turb, spot_stops))
    tag(nt, "BAKE_color", col)
    finish(nt, bsdf_(nt, Base_Color=col, Roughness=rough))
    return m


def mat_rings():
    m, nt = new_mat("Saturn_Rings_proc")
    t = make(nt, "ShaderNodeSeparateXYZ",
             {"Vector": make(nt, "ShaderNodeTexCoord").outputs["UV"]}).outputs["X"]  # radial 0..1
    fine = noise(nt, None, 1.0, 3, 0.5, dims="1D", w=math_(nt, "MULTIPLY", t, 80.0))
    coarse = noise(nt, None, 1.0, 2, 0.5, dims="1D", w=math_(nt, "MULTIPLY", t, 14.0))
    bands = wsum(nt, [(fine, 0.5), (coarse, 0.5)])
    col = ramp(nt, bands, [(0.2, (0.35, 0.3, 0.22)), (0.8, (0.85, 0.78, 0.62))])
    layout = ramp(nt, t, [(0.0, 0.0), (0.04, 0.2), (0.14, 0.35), (0.15, 0.8), (0.44, 0.95), (0.47, 0.08),
                          (0.52, 0.08), (0.53, 0.85), (0.78, 0.85), (0.79, 0.3), (0.8, 0.85),
                          (0.97, 0.7), (1.0, 0.0)])
    alpha = math_(nt, "MULTIPLY", layout, math_(nt, "ADD", 0.6, math_(nt, "MULTIPLY", bands, 0.4)),
                  clamp=True)
    tag(nt, "BAKE_color", col)
    tag(nt, "BAKE_alpha", alpha)
    finish(nt, bsdf_(nt, Base_Color=col, Roughness=0.9, Alpha=alpha))
    blended(m)
    return m


def mat_orbit():
    m, nt = new_mat("Orbit_Line")
    finish(nt, bsdf_(nt, Base_Color=(0, 0, 0, 1), Roughness=1.0, Emission_Color=(0.55, 0.65, 0.9, 1),
                     Emission_Strength=1.5))
    return m


def planet_material(name):
    return {
        "Mercury": lambda: mat_rocky("Mercury_proc", [(0.25, (0.14, 0.13, 0.12)), (0.75, (0.5, 0.47, 0.43))],
                                     7, 0.9),
        "Venus": mat_venus,
        "Earth": mat_earth,
        "Mars": lambda: mat_rocky("Mars_proc", [(0.2, (0.16, 0.06, 0.03)), (0.5, (0.45, 0.2, 0.09)),
                                                (0.8, (0.7, 0.4, 0.22))], 6, 0.7, caps=True),
        "Jupiter": lambda: mat_gas(
            "Jupiter_proc",
            [(0.0, (0.35, 0.2, 0.1)), (0.3, (0.62, 0.4, 0.22)), (0.55, (0.85, 0.72, 0.55)),
             (0.8, (0.92, 0.85, 0.72)), (1.0, (0.6, 0.35, 0.2))], 14.0, 1.3, 4.0,
            spots=[(-22, 0, (3.0, 3.8, 6.5), [(0.3, (0.55, 0.15, 0.08)), (0.7, (0.8, 0.35, 0.2))]),
                   (33, 180, (3.0, 7.0, 10.0), [(0.3, (0.9, 0.88, 0.82)), (0.7, (1.0, 0.97, 0.92))])]),
        "Saturn": lambda: mat_gas(
            "Saturn_proc", [(0.0, (0.55, 0.45, 0.3)), (0.5, (0.8, 0.7, 0.5)), (1.0, (0.9, 0.82, 0.62))],
            10.0, 0.6, 3.0, fine=0.06, rough=0.7),
        "Uranus": lambda: mat_gas(
            "Uranus_proc", [(0.0, (0.4, 0.72, 0.78)), (1.0, (0.58, 0.86, 0.9))], 8.0, 0.3, 2.5,
            fine=0.04, rough=0.6),
        "Neptune": lambda: mat_gas(
            "Neptune_proc", [(0.0, (0.05, 0.12, 0.45)), (0.5, (0.1, 0.25, 0.75)), (1.0, (0.25, 0.45, 0.9))],
            11.0, 0.9, 3.5, spots=[(-20, 0, (3.0, 4.5, 8.0), [(0.3, (0.02, 0.05, 0.22)), (0.7, (0.05, 0.1, 0.35))])],
            rough=0.55),
    }[name]()


# --------------------------------------------------------------------- meshes
def make_sphere(name, r, seg=64, rings=32):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bm.loops.layers.uv.new("UVMap")  # calc_uvs only fills an existing layer
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=r, calc_uvs=True)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    return bpy.data.objects.new(name, me)


def make_ring(name, r_in, r_out, seg=128):
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    inner, outer = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        inner.append(bm.verts.new((r_in * math.cos(a), r_in * math.sin(a), 0)))
        outer.append(bm.verts.new((r_out * math.cos(a), r_out * math.sin(a), 0)))
    for i in range(seg):
        j = (i + 1) % seg
        f = bm.faces.new((inner[i], outer[i], outer[j], inner[j]))
        for loop, uvc in zip(f.loops, ((0, i / seg), (1, i / seg), (1, (i + 1) / seg), (0, (i + 1) / seg))):
            loop[uv].uv = uvc  # u = radial, v = angle
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    return bpy.data.objects.new(name, me)


def make_orbit(name, radius, n=160):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.05
    cu.bevel_resolution = 0
    sp = cu.splines.new("POLY")
    sp.points.add(n - 1)
    for i, p in enumerate(sp.points):
        a = 2 * math.pi * i / n
        p.co = (radius * math.cos(a), radius * math.sin(a), 0, 1)
    sp.use_cyclic_u = True
    obj = bpy.data.objects.new(name, cu)
    obj.visible_shadow = False  # ecliptic-plane lines would otherwise shadow every planet's equator
    return obj


def new_collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


# --------------------------------------------------------------------- stages
def stage_scene():
    """Clear everything, then build the Sun, point light, world and a preview camera."""
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras, bpy.data.curves,
                 bpy.data.images, bpy.data.collections, bpy.data.worlds):
        for d in list(coll):
            coll.remove(d)

    sc = bpy.context.scene
    sc.unit_settings.system = "NONE"
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.view_settings.view_transform = "AgX"

    sun_coll = new_collection("Sun")
    sun = make_sphere("Sun", SUN_RADIUS)
    sun.data.materials.append(mat_sun())
    sun.visible_shadow = False  # else the sphere would block its own point light
    sun_coll.objects.link(sun)

    ld = bpy.data.lights.new("SunLight", "POINT")
    ld.energy = 60000.0
    ld.shadow_soft_size = 0.5
    light = bpy.data.objects.new("SunLight", ld)
    sun_coll.objects.link(light)

    world = bpy.data.worlds.new("Space")
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    sc.world = world
    dirv = make(nt, "ShaderNodeTexCoord").outputs["Generated"]
    cell = voronoi_node(nt, dirv, 140.0)
    star_pt = ramp(nt, cell.outputs["Distance"], [(0.0, 1.0), (0.05, 0.0)])
    star_keep = ramp(nt, cell.outputs["Color"], [(0.55, 0.0), (0.8, 1.0)])
    stars = math_(nt, "MULTIPLY", math_(nt, "MULTIPLY", star_pt, star_keep), 5.0)
    haze = ramp(nt, noise(nt, dirv, 2.0, 6, 0.55), [(0.4, (0, 0, 0)), (1.0, (0.012, 0.015, 0.03))])
    col = vmath(nt, "ADD", vmath(nt, "MULTIPLY", (1.0, 1.0, 1.0), stars), haze)
    bg = make(nt, "ShaderNodeBackground", {"Color": col, "Strength": 1.0})
    out = make(nt, "ShaderNodeOutputWorld")
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

    cam_d = bpy.data.cameras.new("PreviewCamera")
    cam_d.clip_end = 2000
    cam = bpy.data.objects.new("PreviewCamera", cam_d)
    cam.location = (0, -150, 95)
    cam.rotation_euler = (-cam.location).to_track_quat("-Z", "Y").to_euler()
    sun_coll.objects.link(cam)
    sc.camera = cam
    return {"objects": [o.name for o in bpy.data.objects]}


def stage_planets():
    rings_obj = None
    orbit_coll = new_collection("Orbits")
    orbit_mat = mat_orbit()
    for name, (r, dist, tilt, ang) in PLANETS.items():
        coll = new_collection(f"{name}_System")
        body = make_sphere(name, r)
        body.data.materials.append(planet_material(name))
        a = math.radians(ang)
        body.location = (dist * math.cos(a), dist * math.sin(a), 0)
        body.rotation_euler = (math.radians(tilt), 0, 0)
        coll.objects.link(body)
        if name == "Earth":
            clouds = make_sphere("Earth_Clouds", r * CLOUD_SCALE, 48, 24)
            clouds.data.materials.append(mat_clouds())
            clouds.visible_shadow = False
            clouds.parent = body
            coll.objects.link(clouds)
        if name == "Saturn":
            rings_obj = make_ring("Saturn_Rings", r * RING_INNER, r * RING_OUTER)
            rings_obj.data.materials.append(mat_rings())
            rings_obj.parent = body  # inherits the 26.7 deg tilt
            coll.objects.link(rings_obj)
        orbit = make_orbit(f"{name}_Orbit", dist)
        orbit.data.materials.append(orbit_mat)
        orbit_coll.objects.link(orbit)
    return {c.name: [o.name for o in c.objects] for c in bpy.data.collections}


def validate_material(m):
    nt, issues = m.node_tree, []
    outs = [n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial"]
    if len(outs) != 1 or not outs[0].inputs["Surface"].is_linked:
        return ["Material Output missing or Surface unlinked"]
    seen, stack = set(), [outs[0]]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack += [l.from_node for i in n.inputs for l in i.links]
    issues += [f"orphan node {n.name}" for n in nt.nodes if n not in seen and not n.name.startswith("BAKE_")]
    issues += [f"invalid link {l.from_node.name}->{l.to_node.name}" for l in nt.links if not l.is_valid]
    return issues


def stage_validate():
    report = {m.name: validate_material(m) for m in bpy.data.materials}
    tris = {o.name: sum(len(p.vertices) - 2 for p in o.data.polygons) for o in bpy.data.objects if o.type == "MESH"}
    return {"issues": {k: v for k, v in report.items() if v}, "materials_checked": len(report), "tris": tris}


# ------------------------------------------------------------- bake + export
def use_cycles():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 4
    sc.cycles.use_denoising = False
    sc.render.bake.margin = 8
    sc.render.bake.use_clear = True


def deselect_all():
    bpy.context.view_layer.update()
    for o in bpy.data.objects:
        if o.name in bpy.context.view_layer.objects:
            o.select_set(False)


def focus(obj):
    deselect_all()
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _target(nt, img):
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.nodes.active = tex
    tex.select = True
    return tex


def bake_socket(obj, mat, tag_name, img_name, size, srgb=True):
    """Bake the tagged socket's value to an image through a temporary Emission shader."""
    nt = mat.node_tree
    out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    prev = out.inputs["Surface"].links[0].from_socket
    emit = make(nt, "ShaderNodeEmission", {"Color": nt.nodes[tag_name].outputs[0]})
    nt.links.new(emit.outputs[0], out.inputs["Surface"])
    img = bpy.data.images.new(img_name, *size, alpha=False)
    img.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    tex = _target(nt, img)
    focus(obj)
    bpy.ops.object.bake(type="EMIT")
    nt.links.new(prev, out.inputs["Surface"])
    nt.nodes.remove(emit)
    nt.nodes.remove(tex)
    img.pack()
    return img


def bake_normal(obj, mat, img_name, size):
    nt = mat.node_tree
    img = bpy.data.images.new(img_name, *size, alpha=False)
    img.colorspace_settings.name = "Non-Color"
    tex = _target(nt, img)
    focus(obj)
    bpy.ops.object.bake(type="NORMAL")
    nt.nodes.remove(tex)
    img.pack()
    return img


def combine_rgba(rgb_img, alpha_img, name):
    """glTF reads alpha from the base color texture, so merge colour + alpha into one RGBA image."""
    w, h = alpha_img.size
    px = np.ones(w * h * 4, np.float32)
    if rgb_img is not None:
        rgb_img.pixels.foreach_get(px)
    a = np.empty(w * h * 4, np.float32)
    alpha_img.pixels.foreach_get(a)
    px[3::4] = a[0::4]
    out = bpy.data.images.new(name, w, h, alpha=True)
    out.alpha_mode = "STRAIGHT"
    out.pixels.foreach_set(px)
    out.pack()
    return out


def export_material(name, color=None, rough=0.85, normal=None, emit=None, emit_strength=1.0,
                    alpha=False, double_sided=False, rough_img=None):
    m, nt = new_mat(name)
    b = bsdf_(nt, Roughness=rough)

    def image(img, non_color=False):
        t = make(nt, "ShaderNodeTexImage")
        t.image = img
        return t

    if color is not None:
        t = image(color)
        nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
        if alpha:
            nt.links.new(t.outputs["Alpha"], b.inputs["Alpha"])
    if normal is not None:
        nm = make(nt, "ShaderNodeNormalMap", {"Color": image(normal).outputs["Color"]})
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    if rough_img is not None:  # glTF reads roughness from the G channel
        sep = make(nt, "ShaderNodeSeparateColor", {"Color": image(rough_img).outputs["Color"]})
        nt.links.new(sep.outputs["Green"], b.inputs["Roughness"])
    if emit is not None:
        nt.links.new(image(emit).outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = emit_strength
    finish(nt, b)
    if alpha:
        blended(m)
    m.use_backface_culling = not double_sided
    return m


def _export_glb(objs, root, filename):
    os.makedirs(OUT_DIR, exist_ok=True)
    saved = root.location.copy()
    root.location = (0, 0, 0)  # each file is centred on its body
    deselect_all()
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = root
    path = os.path.join(OUT_DIR, filename)
    try:
        bpy.ops.export_scene.gltf(
            filepath=path, export_format="GLB", use_selection=True, export_apply=True,
            export_materials="EXPORT", export_image_format="WEBP", export_cameras=False, export_lights=False,
            export_yup=True, export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6)
    finally:
        root.location = saved
    return {"file": filename, "bytes": os.path.getsize(path)}


def bake_and_export(name):
    """Bake one body's procedural maps, swap in the texture material, export its GLB, restore."""
    if name == "Orbits":
        objs = [o for o in bpy.data.collections["Orbits"].objects]
        return _export_glb(objs, objs[0], "Orbits.glb")

    use_cycles()
    size = TEX_SIZE[name]
    body = bpy.data.objects[name]
    proc = body.material_slots[0].material
    objs, extra = [body], []

    if name == "Sun":
        emit = bake_socket(body, proc, "BAKE_emission", "Sun_emissive", size)
        exp = export_material("Sun_export", emit=emit, emit_strength=5.0)
        exp.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0, 0, 0, 1)
    else:
        color = bake_socket(body, proc, "BAKE_color", f"{name}_color", size)
        normal = bake_normal(body, proc, f"{name}_normal", size) if name in ("Mercury", "Mars", "Earth") else None
        emit = bake_socket(body, proc, "BAKE_emission", "Earth_lights", (1024, 512)) if name == "Earth" else None
        exp = export_material(f"{name}_export", color=color, normal=normal, emit=emit, emit_strength=1.0,
                              rough=0.15 if name == "Earth" else 0.85)

    swaps = [(body, proc, exp)]
    if name == "Earth":
        cl = bpy.data.objects["Earth_Clouds"]
        cproc = cl.material_slots[0].material
        a = bake_socket(cl, cproc, "BAKE_alpha", "Earth_clouds_alpha", (1024, 512), srgb=False)
        swaps.append((cl, cproc, export_material("Earth_Clouds_export",
                                                 color=combine_rgba(None, a, "Earth_clouds_rgba"),
                                                 rough=1.0, alpha=True, double_sided=True)))
        objs.append(cl)
    if name == "Saturn":
        rg = bpy.data.objects["Saturn_Rings"]
        rproc = rg.material_slots[0].material
        rc = bake_socket(rg, rproc, "BAKE_color", "Saturn_rings_color", (1024, 64))
        ra = bake_socket(rg, rproc, "BAKE_alpha", "Saturn_rings_alpha", (1024, 64), srgb=False)
        swaps.append((rg, rproc, export_material("Saturn_Rings_export",
                                                 color=combine_rgba(rc, ra, "Saturn_rings_rgba"),
                                                 rough=0.9, alpha=True, double_sided=True)))
        objs.append(rg)

    for o, _, new in swaps:
        o.material_slots[0].material = new
    try:
        res = _export_glb(objs, body, f"{name}.glb")
    finally:
        for o, old, _ in swaps:
            o.material_slots[0].material = old
    return res


# ---------------------------------------------------------------- real NASA-derived textures
# Solar System Scope maps (CC BY 4.0, from NASA imagery) live in TEX_DIR; run export_real(name) per body.
TEX_DIR = os.environ.get("PLANET_TEX_DIR", os.path.join(ROOT, "textures"))
REAL_SIZE = (4096, 2048)


def load_tex(fname, size=REAL_SIZE, non_color=False):
    img = bpy.data.images.load(os.path.join(TEX_DIR, fname), check_existing=False)
    if size and tuple(img.size) != tuple(size):
        img.scale(*size)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    img.pack()
    return img


def new_img(name, w, h, pixels, non_color=True):
    img = bpy.data.images.new(name, w, h, alpha=False)
    img.pixels.foreach_set(pixels.ravel().astype(np.float32))
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    img.pack()
    return img


def pixels_of(img):
    a = np.empty(len(img.pixels), np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], 4)


def relief_normal(color_img, name, strength=2.0):
    """Tangent-space normal map from albedo luminance (stand-in for crater/canyon relief; no height map is bundled)."""
    c = pixels_of(color_img)
    h = c[..., :3] @ np.array([0.3, 0.59, 0.11], np.float32)
    h = (h + np.roll(h, 1, 0) + np.roll(h, -1, 0) + np.roll(h, 1, 1) + np.roll(h, -1, 1)) / 5  # denoise
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * strength * 8
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * strength * 8
    n = np.dstack([-dx, -dy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    out = np.dstack([n * 0.5 + 0.5, np.ones_like(h)])
    return new_img(name, c.shape[1], c.shape[0], out)


def export_real(name):
    """Swap in an image-based PBR material, export the GLB, restore."""
    body = bpy.data.objects[name]
    objs = [body]
    old = body.material_slots[0].material
    swaps = []
    if name == "Sun":
        em = load_tex("8k_sun.jpg")
        exp = export_material("Sun_export", emit=em, emit_strength=5.0)
        exp.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0, 0, 0, 1)
    elif name == "Earth":
        col = load_tex("8k_earth_daymap.jpg")
        spec = pixels_of(load_tex("8k_earth_specular_map.tif", None, True))
        r = 0.9 - 0.8 * spec[..., 0]  # ocean (bright spec) glossy, land matte
        rough = new_img("Earth_roughness", spec.shape[1], spec.shape[0], np.dstack([r, r, r, np.ones_like(r)]))
        rough.scale(2048, 1024)
        exp = export_material("Earth_export", color=col, normal=load_tex("8k_earth_normal_map.tif", non_color=True),
                              rough_img=rough, emit=load_tex("8k_earth_nightmap.jpg", (2048, 1024)))
    elif name in ("Mercury", "Mars"):
        col = load_tex(f"8k_{name.lower()}.jpg")
        exp = export_material(f"{name}_export", color=col, normal=relief_normal(col, f"{name}_relief"), rough=0.9)
    else:
        f = {"Venus": ("2k_venus_surface.jpg", (2048, 1024)), "Uranus": ("2k_uranus.jpg", (2048, 1024)),
             "Neptune": ("2k_neptune.jpg", (2048, 1024))}.get(name, (f"8k_{name.lower()}.jpg", REAL_SIZE))
        exp = export_material(f"{name}_export", color=load_tex(f[0], f[1]), rough=0.9)
    swaps.append((body, old, exp))
    if name == "Earth":
        cl = bpy.data.objects["Earth_Clouds"]
        a = pixels_of(load_tex("8k_earth_clouds.jpg"))[..., 0]
        white = np.dstack([np.ones_like(a)] * 3 + [a])
        img = bpy.data.images.new("Earth_clouds_rgba", a.shape[1], a.shape[0], alpha=True)
        img.pixels.foreach_set(white.ravel().astype(np.float32))
        img.pack()
        swaps.append((cl, cl.material_slots[0].material,
                      export_material("Earth_Clouds_export", color=img, rough=1.0, alpha=True, double_sided=True)))
        objs.append(cl)
    if name == "Saturn":
        rg = bpy.data.objects["Saturn_Rings"]
        swaps.append((rg, rg.material_slots[0].material,
                      export_material("Saturn_Rings_export", color=load_tex("8k_saturn_ring_alpha.png", None),
                                      rough=0.9, alpha=True, double_sided=True)))
        objs.append(rg)
    for o, _, new in swaps:
        o.material_slots[0].material = new
    try:
        return _export_glb(objs, body, f"{name}.glb")
    finally:
        for o, o_old, _ in swaps:
            o.material_slots[0].material = o_old


def write_manifest():
    data = {"sun": {"radius": SUN_RADIUS, "file": "Sun.glb"}, "orbits": "Orbits.glb", "planets": {}}
    for name, (r, dist, tilt, ang) in PLANETS.items():
        d = {"file": f"{name}.glb", "radius": r, "orbitRadius": dist, "axialTiltDeg": tilt, "startAngleDeg": ang}
        if name == "Earth":
            d["clouds"] = {"radiusScale": CLOUD_SCALE}
        if name == "Saturn":
            d["rings"] = {"inner": r * RING_INNER, "outer": r * RING_OUTER}
        data["planets"][name] = d
    with open(os.path.join(OUT_DIR, "manifest.json"), "w") as f:
        json.dump(data, f, indent=2)
    return data
