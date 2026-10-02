import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Kpi } from "@/components/ui/Kpi";
import { Panel } from "@/components/ui/Panel";
import { usePageHeader } from "@/hooks/usePageHeader";

type Direction = "east" | "west" | "north" | "south" | "walk";
type Actor = { id: number; label: string; direction: Direction; offset: number; kind: "car" | "bike" | "pedestrian" };
type Scenario = "rush" | "pedestrian" | "red-light";
type Point = { x: number; y: number };

const SCENARIOS: { id: Scenario; label: string; description: string; offset: number }[] = [
  { id: "rush", label: "Rush hour junction", description: "Cross traffic builds around a busy four-way junction.", offset: 0 },
  { id: "pedestrian", label: "Pedestrian crossing", description: "A pedestrian enters the crossing as vehicles approach.", offset: 190 },
  { id: "red-light", label: "Conflict replay", description: "Staggered arrivals create a short illustrative conflict window.", offset: 360 },
];

const ACTORS: Actor[] = [
  { id: 12, label: "Car", direction: "east", offset: 0, kind: "car" },
  { id: 18, label: "Car", direction: "west", offset: 225, kind: "car" },
  { id: 24, label: "Bus", direction: "north", offset: 360, kind: "car" },
  { id: 31, label: "Bike", direction: "south", offset: 510, kind: "bike" },
  { id: 42, label: "Pedestrian", direction: "walk", offset: 170, kind: "pedestrian" },
  { id: 47, label: "Car", direction: "east", offset: 620, kind: "car" },
  { id: 53, label: "Bike", direction: "west", offset: 790, kind: "bike" },
];

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
const wrap = (value: number, length: number) => ((value % length) + length) % length;

function actorPosition(actor: Actor, seconds: number, scenarioOffset: number): Point {
  const travel = wrap(seconds * 18 + actor.offset + scenarioOffset, 1060) - 150;
  switch (actor.direction) {
    case "east": return { x: travel, y: actor.id === 47 ? 265 : 325 };
    case "west": return { x: 1060 - travel, y: actor.id === 53 ? 295 : 355 };
    case "north": return { x: 465, y: 700 - travel };
    case "south": return { x: 535, y: travel - 80 };
    case "walk": return { x: 365 + wrap(seconds * 9 + actor.offset + scenarioOffset, 300), y: 405 };
  }
}

function proximityScore(positions: Point[]): number {
  let closest = Number.POSITIVE_INFINITY;
  for (let left = 0; left < positions.length; left += 1) {
    for (let right = left + 1; right < positions.length; right += 1) {
      const first = positions[left];
      const second = positions[right];
      if (!first || !second) continue;
      const dx = first.x - second.x;
      const dy = first.y - second.y;
      closest = Math.min(closest, Math.hypot(dx, dy));
    }
  }
  return Math.round(clamp(100 - closest / 2.8, 0, 100));
}

export function SimulationPage() {
  const [scenarioId, setScenarioId] = useState<Scenario>("rush");
  const [seconds, setSeconds] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(1);
  const scenario = SCENARIOS.find((item) => item.id === scenarioId) ?? SCENARIOS[0]!;
  const positions = useMemo(
    () => ACTORS.map((actor) => actorPosition(actor, seconds, scenario.offset)),
    [seconds, scenario.offset],
  );
  const score = proximityScore(positions);
  const nearMisses = score >= 72 ? 1 : 0;

  usePageHeader("Traffic Simulation", "Replay an illustrative junction scenario without a camera feed");

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setSeconds((current) => (current >= 60 ? 0 : Math.min(60, current + 0.1 * speed)));
    }, 100);
    return () => window.clearInterval(timer);
  }, [playing, speed]);

  const reset = () => {
    setSeconds(0);
    setPlaying(true);
  };

  return (
    <div className="space-y-3 overflow-y-auto p-4">
      <div className="border-accent-line bg-accent-dim flex flex-wrap items-center gap-2 rounded-sm border px-3 py-2">
        <Badge tone="accent">SIMULATION · DEMO</Badge>
        <p className="text-ink-muted text-xs">All tracks and scores on this screen are generated for demonstration. No live camera or stored event data is used.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Panel><Kpi label="Simulated road users" value={ACTORS.length} note="moving tracks" /></Panel>
        <Panel><Kpi label="Proximity score" value={score} unit="/100" note="illustrative scenario output" tone={score >= 72 ? "high" : score >= 45 ? "moderate" : "low"} /></Panel>
        <Panel><Kpi label="Near-miss windows" value={nearMisses} note="current replay moment" tone={nearMisses ? "high" : "neutral"} /></Panel>
        <Panel><Kpi label="Replay time" value={seconds.toFixed(1)} unit="s" note="60 second loop" /></Panel>
      </div>

      <div className="grid grid-cols-1 gap-3 2xl:grid-cols-[minmax(0,1fr)_290px]">
        <Panel
          title="Junction replay"
          meta="synthetic trajectories"
          flush
          actions={<Badge tone={score >= 72 ? "high" : "low"}>{score >= 72 ? "CONFLICT WINDOW" : "FLOWING"}</Badge>}
        >
          <Junction actors={ACTORS} positions={positions} score={score} />
          <div className="border-line flex flex-wrap items-center gap-2 border-t p-3">
            <Button
              variant="primary"
              icon={<Icon name={playing ? "pause" : "play"} size={13} />}
              onClick={() => setPlaying((value) => !value)}
              aria-label={playing ? "Pause simulation" : "Play simulation"}
            >{playing ? "Pause" : "Play"}</Button>
            <Button icon={<Icon name="refresh" size={13} />} onClick={reset}>Restart</Button>
            <Button onClick={() => setSpeed((value) => value === 1 ? 2 : 1)}>Speed {speed}×</Button>
            <span className="text-ink-subtle mono ml-auto text-2xs">00:{String(Math.floor(seconds)).padStart(2, "0")} / 01:00</span>
            <input
              aria-label="Simulation time"
              className="accent-accent min-w-36 flex-1"
              type="range"
              min={0}
              max={60}
              step={0.5}
              value={seconds}
              onChange={(event) => setSeconds(Number(event.target.value))}
            />
          </div>
        </Panel>

        <div className="space-y-3">
          <Panel title="Scenario">
            <label className="field-label" htmlFor="simulation-scenario">Choose replay</label>
            <select
              id="simulation-scenario"
              className="border-line-strong bg-surface-raised text-ink mt-1 w-full rounded-sm border px-2 py-1.5 text-xs"
              value={scenarioId}
              onChange={(event) => { setScenarioId(event.target.value as Scenario); setSeconds(0); }}
            >
              {SCENARIOS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
            <p className="text-ink-muted mt-2 text-xs leading-relaxed">{scenario.description}</p>
          </Panel>

          <Panel title="What this shows">
            <ul className="text-ink-muted space-y-2 text-xs leading-relaxed">
              <li>• Anonymous tracks move through a four-way junction.</li>
              <li>• Proximity score is derived from the closest pair of simulated tracks.</li>
              <li>• Conflict windows are a visual demo signal, not a calibrated safety assessment.</li>
            </ul>
          </Panel>

          <Panel title="Pipeline walkthrough">
            <ol className="text-ink-muted space-y-2 text-xs">
              {["Detect road users", "Track motion over time", "Compare nearby trajectories", "Raise a demo warning"].map((step, index) => (
                <li key={step} className="flex items-center gap-2">
                  <span className={`mono flex size-5 items-center justify-center rounded-full text-2xs ${index === (score >= 72 ? 3 : Math.min(2, Math.floor(seconds / 18))) ? "bg-accent-dim text-accent" : "bg-surface-raised text-ink-subtle"}`}>{index + 1}</span>
                  {step}
                </li>
              ))}
            </ol>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function Junction({ actors, positions, score }: { actors: Actor[]; positions: Point[]; score: number }) {
  return (
    <div className="bg-surface-sunken min-h-[340px] p-2 sm:p-4">
      <svg viewBox="0 0 920 620" role="img" aria-label="Animated synthetic traffic moving through a four-way junction" className="h-full max-h-[590px] min-h-[320px] w-full">
        <rect width="920" height="620" fill="var(--color-surface-sunken)" />
        <rect x="0" y="205" width="920" height="240" fill="#252e34" />
        <rect x="345" y="0" width="230" height="620" fill="#252e34" />
        <path d="M0 325H345M575 325H920M460 0V205M460 445V620" stroke="#7c898b" strokeWidth="2" strokeDasharray="18 15" opacity=".65" />
        <path d="M0 220H345M575 430H920M360 0V205M560 445V620" stroke="#536064" strokeWidth="2" />
        <rect x="345" y="205" width="230" height="240" fill="#29343a" stroke="#465459" strokeWidth="2" />
        <g opacity=".85" fill="#d4d9d5">
          {Array.from({ length: 7 }, (_, i) => <rect key={`cross-a-${i}`} x={352 + i * 31} y="190" width="17" height="9" rx="1" />)}
          {Array.from({ length: 7 }, (_, i) => <rect key={`cross-b-${i}`} x={352 + i * 31} y="451" width="17" height="9" rx="1" />)}
          {Array.from({ length: 6 }, (_, i) => <rect key={`cross-c-${i}`} x="329" y={220 + i * 34} width="9" height="18" rx="1" />)}
          {Array.from({ length: 6 }, (_, i) => <rect key={`cross-d-${i}`} x="582" y={220 + i * 34} width="9" height="18" rx="1" />)}
        </g>
        <circle cx="460" cy="325" r="42" fill="none" stroke={score >= 72 ? "#f29955" : "#57c7b0"} strokeWidth="2" strokeDasharray="5 5" opacity=".8" />
        <text x="460" y="375" textAnchor="middle" fill="#a9b6b8" fontSize="11" letterSpacing="1.5">CONFLICT ZONE</text>
        {actors.map((actor, index) => {
          const point = positions[index];
          return point ? <Vehicle key={actor.id} actor={actor} point={point} highlighted={score >= 72 && index < 2} /> : null;
        })}
        <g transform="translate(22 24)">
          <rect width="178" height="49" rx="4" fill="#171e22" stroke="#3a484c" />
          <circle cx="15" cy="16" r="4" fill="#57c7b0" />
          <text x="27" y="20" fill="#e4ebe8" fontSize="11">TRACK ID · CLASS</text>
          <circle cx="15" cy="34" r="4" fill="#f29955" />
          <text x="27" y="38" fill="#a9b6b8" fontSize="11">PROXIMITY ALERT</text>
        </g>
      </svg>
    </div>
  );
}

function Vehicle({ actor, point, highlighted }: { actor: Actor; point: Point; highlighted: boolean }) {
  const rotation = actor.direction === "north" ? -90 : actor.direction === "south" ? 90 : actor.direction === "west" ? 180 : 0;
  const color = actor.kind === "pedestrian" ? "#f2c66d" : actor.kind === "bike" ? "#7fbbf2" : "#57c7b0";
  return (
    <g transform={`translate(${point.x} ${point.y}) rotate(${rotation})`}>
      {highlighted ? <circle r="22" fill="none" stroke="#f29955" strokeWidth="2" className="animate-pulse" /> : null}
      {actor.kind === "pedestrian" ? (
        <><circle cy="-8" r="5" fill={color} /><path d="M0 -2V9M0 2 -7 7M0 2 7 6M0 9 -5 17M0 9 6 16" stroke={color} strokeWidth="3" strokeLinecap="round" /></>
      ) : (
        <><rect x="-18" y="-9" width="36" height="18" rx="6" fill={color} stroke="#172126" strokeWidth="2" /><path d="M-7 -7v14M4 -7v14" stroke="#172126" strokeWidth="2" opacity=".65" /><text y="3" textAnchor="middle" fill="#10201f" fontSize="8" fontWeight="700">{actor.id}</text></>
      )}
      <text y="29" textAnchor="middle" fill="#e4ebe8" fontSize="9" paintOrder="stroke" stroke="#171e22" strokeWidth="3">#{actor.id} {actor.label}</text>
    </g>
  );
}
