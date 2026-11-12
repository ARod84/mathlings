import { useCallback, useEffect, useRef, useState } from 'react';

export type FeedbackSound = 'correct' | 'incorrect' | 'solved';

interface Tone {
  /** Frequency in Hz. */
  frequency: number;
  /** Start offset in seconds. */
  at: number;
  /** Length in seconds. */
  length: number;
}

interface SoundRecipe {
  wave: OscillatorType;
  /** Peak gain. Kept low: these are cues, not alarms. */
  peak: number;
  tones: Tone[];
}

const RECIPES: Record<FeedbackSound, SoundRecipe> = {
  // Two quick rising notes.
  correct: {
    wave: 'triangle',
    peak: 0.12,
    tones: [
      { frequency: 659.25, at: 0, length: 0.12 },
      { frequency: 880, at: 0.1, length: 0.2 },
    ],
  },
  // A soft, low "hmm": quieter than the others and never a buzzer.
  incorrect: {
    wave: 'sine',
    peak: 0.07,
    tones: [
      { frequency: 392, at: 0, length: 0.14 },
      { frequency: 329.63, at: 0.12, length: 0.22 },
    ],
  },
  // A rising arpeggio.
  solved: {
    wave: 'triangle',
    peak: 0.12,
    tones: [
      { frequency: 523.25, at: 0, length: 0.14 },
      { frequency: 659.25, at: 0.11, length: 0.14 },
      { frequency: 783.99, at: 0.22, length: 0.14 },
      { frequency: 1046.5, at: 0.33, length: 0.34 },
    ],
  },
};

/** Marks the mute button, so pressing it is not counted as the "first interaction". */
export const SOUND_TOGGLE_ATTRIBUTE = 'data-sound-toggle';

function getAudioContextConstructor(): typeof AudioContext | undefined {
  if (typeof window === 'undefined') return undefined;
  const legacy = window as unknown as { webkitAudioContext?: typeof AudioContext };
  return window.AudioContext ?? legacy.webkitAudioContext;
}

export interface FeedbackSoundControls {
  muted: boolean;
  toggleMuted: () => void;
  play: (sound: FeedbackSound) => void;
}

/**
 * Short synthesized feedback tones (Web Audio API, no audio files).
 *
 * Sound starts muted. The first tap or key press anywhere on the page unmutes
 * it, unless the user has already chosen a setting with the mute toggle.
 */
export function useFeedbackSound(): FeedbackSoundControls {
  // null until the user picks a setting with the toggle.
  const [preference, setPreference] = useState<boolean | null>(null);
  const [hasInteracted, setHasInteracted] = useState(false);
  const contextRef = useRef<AudioContext | null>(null);

  const muted = preference ?? !hasInteracted;

  useEffect(() => {
    if (hasInteracted) return;
    const onFirstInteraction = (event: Event) => {
      const target = event.target;
      if (target instanceof Element && target.closest(`[${SOUND_TOGGLE_ATTRIBUTE}]`)) return;
      setHasInteracted(true);
    };
    window.addEventListener('pointerdown', onFirstInteraction);
    window.addEventListener('keydown', onFirstInteraction);
    return () => {
      window.removeEventListener('pointerdown', onFirstInteraction);
      window.removeEventListener('keydown', onFirstInteraction);
    };
  }, [hasInteracted]);

  useEffect(
    () => () => {
      void contextRef.current?.close();
      contextRef.current = null;
    },
    [],
  );

  const toggleMuted = useCallback(() => {
    setPreference(!muted);
  }, [muted]);

  const play = useCallback(
    (sound: FeedbackSound) => {
      if (muted) return;
      const AudioContextConstructor = getAudioContextConstructor();
      if (!AudioContextConstructor) return;

      try {
        contextRef.current ??= new AudioContextConstructor();
        const context = contextRef.current;
        if (context.state === 'suspended') void context.resume();

        const recipe = RECIPES[sound];
        const start = context.currentTime + 0.02;
        for (const tone of recipe.tones) {
          const oscillator = context.createOscillator();
          const gain = context.createGain();
          const begin = start + tone.at;
          const end = begin + tone.length;

          oscillator.type = recipe.wave;
          oscillator.frequency.setValueAtTime(tone.frequency, begin);
          // Quick fade in and a smooth fade out, so there are no clicks.
          gain.gain.setValueAtTime(0.0001, begin);
          gain.gain.linearRampToValueAtTime(recipe.peak, begin + 0.015);
          gain.gain.exponentialRampToValueAtTime(0.0001, end);

          oscillator.connect(gain);
          gain.connect(context.destination);
          oscillator.start(begin);
          oscillator.stop(end + 0.02);
        }
      } catch {
        // Audio is an extra. If the browser refuses, the visual feedback still works.
      }
    },
    [muted],
  );

  return { muted, toggleMuted, play };
}
