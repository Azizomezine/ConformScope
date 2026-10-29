"use client";

import { useState } from "react";
import styles from "./page.module.css";

type Room = {
  name: string;
  room_type: string;
  x: number;
  y: number;
  area_m2: number | null;
};

type PlanReading = {
  id: string;
  width: number;
  height: number;
  scale: string | null;
  rooms: Room[];
};

export function PlanIntake() {
  const [reading, setReading] = useState<PlanReading | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    setReading(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/plans", { method: "POST", body: form });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        setError(body?.detail ?? `Upload failed (${response.status})`);
        return;
      }
      setReading(body);
    } catch {
      setError("Could not reach the ConformScope server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.intake}>
      <label className={styles.drop}>
        <input
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) upload(file);
          }}
        />
        {busy ? "Reading the plan with Muse Spark…" : "Drop a plan (PDF or image)"}
      </label>

      {error && <p role="alert" className={styles.error}>{error}</p>}

      {reading && (
        <section className={styles.result}>
          <div className={styles.plan}>
            {/* eslint-disable-next-line @next/next/no-img-element -- served by our API, sized by the plan */}
            <img src={`/api/plans/${reading.id}/image`} alt="Uploaded plan" />
            {reading.rooms.map((room, i) => (
              <span
                key={i}
                className={styles.dot}
                title={room.name}
                style={{
                  left: `${(room.x / reading.width) * 100}%`,
                  top: `${(room.y / reading.height) * 100}%`,
                }}
              >
                {i + 1}
              </span>
            ))}
          </div>

          <aside>
            <h2>{reading.rooms.length} rooms found</h2>
            <p className={styles.muted}>Scale: {reading.scale ?? "not written on the plan"}</p>
            <ol className={styles.rooms}>
              {reading.rooms.map((room, i) => (
                <li key={i}>
                  <strong>{room.name}</strong>
                  <span>
                    {room.room_type}
                    {room.area_m2 !== null && ` · ${room.area_m2} m²`}
                  </span>
                </li>
              ))}
            </ol>
          </aside>
        </section>
      )}
    </div>
  );
}
