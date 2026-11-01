import Link from "next/link";
import styles from "../page.module.css";
import { PlanIntake } from "../plan-intake";

export default function CheckPage() {
  return (
    <main className={styles.landing}>
      <header className={styles.topbar}>
        <div className={styles.topbarInner}>
          <span className={styles.brand}><span className={styles.brandMark} aria-hidden />ConformScope</span>
          <Link href="/" className={styles.navLink}>← Accueil</Link>
        </div>
      </header>
      <div className={styles.wrap}>
        <section className={styles.checkIntro}>
          <span className={styles.eyebrow}>Vérifier un plan</span>
          <h1>Can a wheelchair live in this home?</h1>
          <p>Déposez un plan (PDF ou image). ConformScope lit les pièces, les mesure en mètres, et vérifie le cercle de retournement de Ø1,50 m dans chacune. Vous pourrez ensuite corriger la découpe à la souris.</p>
        </section>
        <div className={styles.checkCard}>
          <PlanIntake />
        </div>
      </div>
      <footer className={styles.footer}>
        <div className={styles.wrap}>
          <span className={styles.brand}><span className={styles.brandMark} aria-hidden />ConformScope</span>
          <p>Lecture par Muse Spark, segmentation par SAM 3.1, verdict par la géométrie.</p>
        </div>
      </footer>
    </main>
  );
}
