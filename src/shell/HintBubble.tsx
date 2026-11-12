import styles from './HintBubble.module.css';
import { OrbiPlaceholder } from './orbi/OrbiPlaceholder';

interface HintBubbleProps {
  text: string;
}

/** A speech bubble from ORBI, the tutor character. */
export function HintBubble({ text }: HintBubbleProps) {
  return (
    <div className={styles.hint}>
      <OrbiPlaceholder className={styles.orbi} size={56} surface="light" />
      <div className={styles.bubble}>
        <p className={styles.label}>ORBI&rsquo;s hint</p>
        <p className={styles.text}>{text}</p>
      </div>
    </div>
  );
}
