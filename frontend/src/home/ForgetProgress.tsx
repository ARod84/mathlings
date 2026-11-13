import { useState } from 'react';
import { forgetPlayer } from '../api/player';
import styles from './ForgetProgress.module.css';

type Stage = 'idle' | 'confirming' | 'working' | 'done' | 'failed';

/**
 * A quiet text button that deletes this device's practice history. It asks
 * once, inside the page, before doing anything.
 */
export function ForgetProgress() {
  const [stage, setStage] = useState<Stage>('idle');

  const forget = async () => {
    setStage('working');
    setStage((await forgetPlayer()) === 'forgotten' ? 'done' : 'failed');
  };

  if (stage === 'confirming' || stage === 'working') {
    return (
      <div className={styles.forget} role="group" aria-label="Forget my progress">
        <p className={styles.text}>
          This deletes your practice history from this device and from our server. It cannot be
          undone.
        </p>
        <div className={styles.choices}>
          <button
            type="button"
            className={styles.link}
            disabled={stage === 'working'}
            onClick={() => void forget()}
          >
            Yes, forget it
          </button>
          <button
            type="button"
            className={styles.link}
            disabled={stage === 'working'}
            onClick={() => setStage('idle')}
          >
            Keep it
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.forget}>
      <button type="button" className={styles.link} onClick={() => setStage('confirming')}>
        Forget my progress on this device
      </button>
      <p className={styles.text} role="status">
        {stage === 'done' && 'Done. Your progress is forgotten.'}
        {stage === 'failed' && 'That did not work. Please try again.'}
      </p>
    </div>
  );
}
