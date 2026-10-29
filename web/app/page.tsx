import styles from "./page.module.css";
import { PlanIntake } from "./plan-intake";

export default function Home() {
  return (
    <main className={styles.main}>
      <header>
        <h1>ConformScope</h1>
        <p className={styles.muted}>Can a wheelchair live in this home?</p>
      </header>
      <PlanIntake />
    </main>
  );
}
