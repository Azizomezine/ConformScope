// Illustrative demo apartment, built in code. Not a real audited home.
// Coordinates are metres on a 10 x 7 m plan. Same shape the real checker
// returns: polygon, area, turning circle and PMR verdict per room.

export type DemoRoom = {
  name: string;
  nameFr: string;
  verdictFr: string;
  roomType: string;
  color: string;
  polygon: [number, number][];
  areaM2: number;
  circle: { center: [number, number]; diameterM: number; conforme: boolean };
  verdict: string;
};

export const PLAN_W = 10;
export const PLAN_H = 7;
export const WALL_H = 1.4;
export const TURNING_DIAMETER_M = 1.5;

export const DEMO_ROOMS: DemoRoom[] = [
  {
    name: "Living room", nameFr: "Séjour", verdictFr: "Conforme PMR", roomType: "living", color: "#f4a261",
    polygon: [[0, 0], [5.6, 0], [5.6, 4.2], [0, 4.2]],
    areaM2: 23.5,
    circle: { center: [2.8, 2.1], diameterM: 1.5, conforme: true },
    verdict: "Conforme PMR",
  },
  {
    name: "Kitchen", nameFr: "Cuisine", verdictFr: "Conforme PMR", roomType: "kitchen", color: "#e9c46a",
    polygon: [[5.6, 0], [10, 0], [10, 2.6], [5.6, 2.6]],
    areaM2: 11.4,
    circle: { center: [7.8, 1.3], diameterM: 1.5, conforme: true },
    verdict: "Conforme PMR",
  },
  {
    name: "Bedroom", nameFr: "Chambre", verdictFr: "Conforme PMR", roomType: "bedroom", color: "#8ab17d",
    polygon: [[0, 4.2], [4.2, 4.2], [4.2, 7], [0, 7]],
    areaM2: 11.8,
    circle: { center: [2.1, 5.6], diameterM: 1.5, conforme: true },
    verdict: "Conforme PMR",
  },
  {
    name: "Bathroom", nameFr: "Salle de bain", verdictFr: "Conforme PMR", roomType: "bathroom", color: "#4ea8de",
    polygon: [[4.2, 4.2], [7.2, 4.2], [7.2, 7], [4.2, 7]],
    areaM2: 8.4,
    circle: { center: [5.7, 5.6], diameterM: 1.5, conforme: true },
    verdict: "Conforme PMR",
  },
  {
    name: "WC", nameFr: "WC", verdictFr: "Non conforme PMR (max Ø1,40 m)", roomType: "wc", color: "#2a6f97",
    polygon: [[7.2, 4.2], [8.6, 4.2], [8.6, 7], [7.2, 7]],
    areaM2: 3.9,
    circle: { center: [7.9, 5.6], diameterM: 1.4, conforme: false },
    verdict: "Non conforme PMR (max Ø1.40 m)",
  },
  {
    name: "Corridor", nameFr: "Couloir", verdictFr: "Conforme PMR", roomType: "corridor", color: "#b5a1d9",
    polygon: [[5.6, 2.6], [10, 2.6], [10, 7], [8.6, 7], [8.6, 4.2], [5.6, 4.2]],
    areaM2: 11.0,
    circle: { center: [7.8, 3.4], diameterM: 1.5, conforme: true },
    verdict: "Conforme PMR",
  },
];

// Door centres on shared walls, in plan metres. The 3D scene leaves a gap
// in the wall at each one so the wheelchair can pass through.
export const DEMO_DOORS: [number, number][] = [[5.6, 3.4], [7.9, 4.2]];

// The wheelchair's route: living room -> corridor -> WC door, where it stops.
export const DEMO_PATH: [number, number][] = [[2.8, 2.1], [5.6, 3.4], [7.8, 3.4], [7.9, 4.2]];
// After the fix it rolls the last stretch, into the WC.
export const DEMO_PATH_END: [number, number] = [7.9, 5.6];

export const DEMO_STEPS_EN = [
  {
    eyebrow: "Reading", title: "Reading the plan",
    text: "Muse Spark reads the plan's labels. Dimensions become metres, the plan stays flat.",
    tags: ["2D plan", "Labels", "Metres"],
  },
  {
    eyebrow: "Rooms", title: "Each room is cut out",
    text: "SAM 3.1 cuts out the rooms on the image. Each one gets its type and its area.",
    tags: ["Segmentation", "Room type", "Area m²"],
  },
  {
    eyebrow: "Volume", title: "The walls go up",
    text: "Each room becomes a volume. You see the home, not just the drawing.",
    tags: ["Real-time 3D", "Walls"],
  },
  {
    eyebrow: "Circle", title: "A Ø1.50 m circle has to turn",
    text: "Geometry looks for the largest free circle in each room. No verdict comes from the model.",
    tags: ["Ø1.50 m", "Geometry"],
  },
  {
    eyebrow: "Verdict", title: "The WC does not fit",
    text: "Green: a wheelchair can turn around. Red: the WC tops out at Ø1.40 m. You see it before signing.",
    tags: ["Compliant", "Not compliant"],
  },
  {
    eyebrow: "The fix", title: "Move a wall 10 cm, keep the home",
    text: "Shift the WC partition by 10 cm and the Ø1.50 m circle fits. The wheelchair rolls in — fixed on paper, before anyone signs.",
    tags: ["+10 cm", "Ø1.50 m fits", "On paper"],
  },
] as const;

export const DEMO_STEPS = [
  {
    eyebrow: "Lecture", title: "On lit le plan",
    text: "Muse Spark lit les étiquettes du plan. Les cotes passent en mètres, le plan reste à plat.",
    tags: ["Plan 2D", "Étiquettes", "Mètres"],
  },
  {
    eyebrow: "Pièces", title: "Chaque pièce est découpée",
    text: "SAM 3.1 découpe les pièces sur l'image. Chacune reçoit son type et sa surface.",
    tags: ["Segmentation", "Type de pièce", "Surface m²"],
  },
  {
    eyebrow: "Volume", title: "Les murs montent",
    text: "Chaque pièce devient un volume. On voit la maison, pas seulement le dessin.",
    tags: ["3D temps réel", "Murs"],
  },
  {
    eyebrow: "Cercle", title: "Un cercle de Ø1,50 m doit tourner",
    text: "La géométrie cherche le plus grand cercle libre de chaque pièce. Aucun verdict ne vient du modèle.",
    tags: ["Ø1,50 m", "Géométrie"],
  },
  {
    eyebrow: "Verdict", title: "Le WC ne passe pas",
    text: "Vert : un fauteuil peut y faire demi-tour. Rouge : le WC plafonne à Ø1,40 m. On le voit avant de signer.",
    tags: ["Conforme", "Non conforme"],
  },
  {
    eyebrow: "La correction", title: "On pousse un mur de 10 cm, la maison reste",
    text: "Décalez la cloison des WC de 10 cm et le cercle de Ø1,50 m passe. Le fauteuil entre — corrigé sur le papier, avant de signer.",
    tags: ["+10 cm", "Ø1,50 m passe", "Sur le papier"],
  },
] as const;

// Share of the scroll track the hero holds before the first chapter starts.
export const STORY_INTRO = 0.1;

/** Scroll progress [start, end) of chapter i on the hero track. */
export function chapterRange(i: number): [number, number] {
  const span = (1 - STORY_INTRO) / DEMO_STEPS.length;
  return [STORY_INTRO + i * span, STORY_INTRO + (i + 1) * span];
}

/** Chapter shown at scroll progress p, or -1 while the hero is on screen. */
export function chapterAt(p: number) {
  if (p < STORY_INTRO) return -1;
  const span = (1 - STORY_INTRO) / DEMO_STEPS.length;
  return Math.min(DEMO_STEPS.length - 1, Math.floor((p - STORY_INTRO) / span));
}
