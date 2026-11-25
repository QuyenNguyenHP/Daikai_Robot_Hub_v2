"""Build a compact, indexed GLB for the HUD; the original STL is preserved.

Build-only dependencies: pip install trimesh==5.2.2 fast-simplification==0.2.0
Run from the repository root: python3 tools/optimize_robot_model.py
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--faces', type=int, default=80000)
    args = parser.parse_args()
    source = ROOT / 'R1_full_robot.stl'
    target = ROOT / 'frontend/src/assets/r1-monitor.glb'
    mesh = trimesh.load_mesh(source, process=True)
    reduced = mesh.simplify_quadric_decimation(face_count=args.faces, aggression=5)
    reduced.remove_unreferenced_vertices()
    if not np.isfinite(reduced.vertices).all() or len(reduced.faces) == 0:
        raise RuntimeError('Invalid simplified geometry')
    if not np.allclose(mesh.bounds, reduced.bounds, atol=0.003):
        raise RuntimeError('Model bounds changed by more than 3 mm')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(trimesh.exchange.gltf.export_glb(trimesh.Scene(reduced), include_normals=True))
    report = {
        'source': source.name, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'source_bytes': source.stat().st_size, 'source_triangles': len(mesh.faces),
        'asset': target.name, 'asset_bytes': target.stat().st_size,
        'triangles': len(reduced.faces), 'vertices': len(reduced.vertices),
        'bounds_metres': reduced.bounds.tolist(),
        'trimesh': trimesh.__version__,
    }
    target.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
