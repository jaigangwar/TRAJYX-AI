/** Calibrated ground-plane replay; paths rise over time so conflicts are visible. */

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import type { VideoAnalysis } from "@/features/analysis/api";
import { riskLevelFromScore, riskPresentation } from "@/lib/risk";

const TIME_SCALE = 2.5;

function resolveColour(token: string, fallback: string): string {
  const variable = token.match(/^var\((--[^)]+)\)$/)?.[1];
  if (!variable) return token;
  return getComputedStyle(document.documentElement).getPropertyValue(variable).trim() || fallback;
}

export function ConflictView3D({
  analysis,
  onUnavailable,
}: {
  analysis: VideoAnalysis;
  onUnavailable: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = host.current;
    const calibration = analysis.camera_calibration;
    if (!element || !calibration || analysis.frame_width <= 0 || analysis.frame_height <= 0) {
      onUnavailable();
      return;
    }

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch {
      onUnavailable();
      return;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#11171b");
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 10000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.autoRotate = false;
    controls.target.set(0, Math.max(1, analysis.duration_s * TIME_SCALE / 2), 0);
    scene.add(new THREE.HemisphereLight("#d7e5e1", "#263238", 2.2));
    const keyLight = new THREE.DirectionalLight("#ffffff", 1.8);
    keyLight.position.set(20, 40, 25);
    scene.add(keyLight);
    element.appendChild(renderer.domElement);

    const toWorld = (x: number, y: number, seconds: number) => {
      const depthScale = 1 - calibration.depth_factor * ((y - calibration.reference_y) / calibration.frame_height);
      const scale = calibration.metres_per_pixel_at_reference * Math.max(0.25, Math.min(4, depthScale));
      return new THREE.Vector3(
        (x - analysis.frame_width / 2) * scale,
        Math.max(0, seconds) * TIME_SCALE,
        (analysis.frame_height - y) * scale,
      );
    };

    const trackPoints = new Map<number, THREE.Vector3[]>();
    const palette = ["#57c7b0", "#86b9ed", "#c8a7f0", "#e7c66d", "#74d3c1", "#e7a978"];
    const highlightedIds = new Set(
      analysis.timeline
        .filter((entry) => entry.event_type === "NEAR_MISS")
        .flatMap((entry) => entry.track_ids),
    );
    const highRiskColour = resolveColour(riskPresentation("HIGH").color, "#f29955");
    const allGround: THREE.Vector3[] = [];

    analysis.tracks.forEach((track, index) => {
      if (track.path.length < 2) return;
      const span = Math.max(1, track.last_frame - track.first_frame);
      const points = track.path.flatMap((point, pointIndex) => {
        const x = point[0];
        const y = point[1];
        if (x === undefined || y === undefined || !Number.isFinite(x) || !Number.isFinite(y)) return [];
        const frame = track.first_frame + (pointIndex / (track.path.length - 1)) * span;
        const result = toWorld(x, y, frame / analysis.frame_rate);
        allGround.push(new THREE.Vector3(result.x, 0, result.z));
        return [result];
      });
      if (points.length < 2) return;
      trackPoints.set(track.track_id, points);
      const curve = new THREE.CatmullRomCurve3(points);
      const geometry = new THREE.TubeGeometry(curve, Math.min(160, points.length * 5), 0.16, 5, false);
      const color = highlightedIds.has(track.track_id) ? highRiskColour : palette[index % palette.length]!;
      const material = new THREE.MeshStandardMaterial({ color, roughness: 0.75, metalness: 0 });
      scene.add(new THREE.Mesh(geometry, material));
    });

    if (allGround.length === 0) {
      renderer.dispose();
      element.removeChild(renderer.domElement);
      onUnavailable();
      return;
    }

    const bounds = new THREE.Box3().setFromPoints(allGround);
    const size = bounds.getSize(new THREE.Vector3());
    const groundSize = Math.max(10, size.x, size.z) * 1.35;
    const grid = new THREE.GridHelper(groundSize, 24, "#49615e", "#293638");
    grid.position.y = 0;
    scene.add(grid);
    const centre = bounds.getCenter(new THREE.Vector3());
    controls.target.set(centre.x, Math.max(0.5, analysis.duration_s * TIME_SCALE / 2), centre.z);
    const viewDistance = Math.max(15, groundSize * 1.25, analysis.duration_s * TIME_SCALE * 0.9);
    camera.position.set(centre.x + viewDistance * 0.75, viewDistance * 0.78, centre.z + viewDistance);
    controls.update();

    const markerGeometry = new THREE.SphereGeometry(0.55, 14, 10);
    for (const entry of analysis.timeline.filter((item) => item.event_type === "NEAR_MISS")) {
      const paths = entry.track_ids
        .map((trackId) => {
          const track = analysis.tracks.find((candidate) => candidate.track_id === trackId);
          const points = trackPoints.get(trackId);
          if (!track || !points?.length) return null;
          const denominator = Math.max(1, track.last_frame - track.first_frame);
          const ratio = THREE.MathUtils.clamp((entry.frame_index - track.first_frame) / denominator, 0, 1);
          return points[Math.round(ratio * (points.length - 1))] ?? null;
        })
        .filter((point): point is THREE.Vector3 => point !== null);
      if (!paths.length) continue;
      const centrePoint = paths.reduce((sum, point) => sum.add(point), new THREE.Vector3()).multiplyScalar(1 / paths.length);
      const markerColour = entry.risk_score === null || entry.risk_score === undefined
        ? highRiskColour
        : resolveColour(riskPresentation(riskLevelFromScore(entry.risk_score)).color, highRiskColour);
      const marker = new THREE.Mesh(markerGeometry, new THREE.MeshBasicMaterial({ color: markerColour }));
      marker.position.copy(centrePoint);
      marker.userData.event = entry.label;
      scene.add(marker);
    }

    const resize = () => {
      const width = Math.max(1, element.clientWidth);
      const height = Math.max(1, element.clientHeight);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(width, height);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();

    let frame = 0;
    const draw = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = window.requestAnimationFrame(draw);
    };
    draw();

    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          const material = object.material;
          if (Array.isArray(material)) material.forEach((part) => part.dispose());
          else material.dispose();
        } else if (object instanceof THREE.GridHelper) {
          object.geometry.dispose();
          const material = object.material;
          if (Array.isArray(material)) material.forEach((part) => part.dispose());
          else material.dispose();
        }
      });
      markerGeometry.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    };
  }, [analysis, onUnavailable]);

  return (
    <div className="bg-surface-sunken relative h-[360px] min-h-[280px] w-full overflow-hidden sm:h-[480px]" aria-label="3D calibrated track conflict replay">
      <div ref={host} className="absolute inset-0" />
      <div className="pointer-events-none absolute top-2 left-2 rounded-sm border border-line bg-ground/90 px-2 py-1 text-2xs text-ink-muted">
        Z axis: estimated ground plane · vertical axis: time
      </div>
      <div className="pointer-events-none absolute right-2 bottom-2 rounded-sm border border-line bg-ground/90 px-2 py-1 text-2xs text-ink-muted">
        Drag to rotate · scroll to zoom
      </div>
    </div>
  );
}
