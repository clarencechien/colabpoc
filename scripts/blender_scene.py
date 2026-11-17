"""在 Blender 裡執行（blender -b -P scripts/blender_scene.py -- --device OPTIX|CUDA|CPU --out DIR [--glb 1]）。
程序化場景：地面 + 5 顆 PBR 球 + 日光與天空，1920x1080、128 samples。印出 RENDER_JSON。"""
import json
import os
import sys
import time

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opt = dict(zip(argv[::2], argv[1::2]))
device, out = opt.get("--device", "OPTIX"), opt.get("--out", "/content/out/phase4")
os.makedirs(out, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"


def material(name, color, metallic, roughness):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = roughness
    return m


bpy.ops.mesh.primitive_plane_add(size=40)
bpy.context.object.data.materials.append(material("ground", (0.5, 0.5, 0.5), 0.0, 0.6))
specs = [((0.8, 0.1, 0.1), 0.0, 0.5), ((0.9, 0.7, 0.2), 1.0, 0.15), ((0.1, 0.3, 0.8), 0.0, 0.05), ((0.8, 0.8, 0.8), 1.0, 0.4), ((0.1, 0.6, 0.2), 0.0, 0.9)]
for i, (c, met, rough) in enumerate(specs):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=64, ring_count=32, location=((i - 2) * 2.4, 0, 1))
    bpy.ops.object.shade_smooth()
    bpy.context.object.data.materials.append(material(f"pbr{i}", c, met, rough))
bpy.ops.object.light_add(type="SUN", rotation=(0.9, 0.1, 0.6))
bpy.context.object.data.energy = 4
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.7, 1.0, 1)
scene.world = world
bpy.ops.object.camera_add(location=(0, -13, 4.5), rotation=(1.3, 0, 0))
scene.camera = bpy.context.object

rep = {"requested_device": device, "blender": bpy.app.version_string, "devices": []}
if device == "CPU":
    scene.cycles.device = "CPU"
else:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = device
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == device  # 只開 GPU，不混 CPU
        rep["devices"].append({"name": d.name, "type": d.type, "use": d.use})
    scene.cycles.device = "GPU"
    if not any(d["use"] for d in rep["devices"]):
        rep["error"] = f"沒有 {device} 裝置"
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1920, 1080, 100
scene.cycles.samples = 128
scene.cycles.use_adaptive_sampling = False
scene.cycles.use_denoising = False
scene.render.filepath = os.path.join(out, f"render_{opt.get('--tag', 'gpu')}_{device}.png")
if "error" not in rep:
    t = time.time()
    bpy.ops.render.render(write_still=True)
    rep.update({"render_s": round(time.time() - t, 2), "png": os.path.basename(scene.render.filepath), "note": "含 kernel 載入／BVH 建置；單張冷跑"})
if opt.get("--glb") == "1":
    glb = os.path.join(out, "scene.glb")
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB")
    rep["glb_bytes"] = os.path.getsize(glb)
print("RENDER_JSON " + json.dumps(rep, ensure_ascii=False))
