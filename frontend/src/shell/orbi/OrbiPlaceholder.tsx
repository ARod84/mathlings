/*
 * ============================================================================
 * PLACEHOLDER ART: replace this file's SVG with the final ORBI character.
 * ============================================================================
 * ORBI is the tutor character who gives hints. This is a simple stand-in so
 * the layout, sizing and motion can be built now.
 *
 * To swap in the real art, keep the component name and props and replace the
 * <svg> below. Nothing else in the app draws ORBI.
 */

interface OrbiPlaceholderProps {
  /** Rendered width in px. Height follows the 86:94 aspect ratio. */
  size?: number;
  /**
   * Which background ORBI sits on. 'dark' draws a white body for dark
   * backgrounds; 'light' draws a dark body with house-colored eyes.
   */
  surface?: 'dark' | 'light';
  className?: string;
}

export function OrbiPlaceholder({ size = 64, surface = 'dark', className }: OrbiPlaceholderProps) {
  const onLight = surface === 'light';
  const body = onLight ? '#221739' : '#FFFFFF';
  const screen = onLight ? '#FFFFFF' : '#221739';
  const eyes = onLight ? 'var(--house, #7C4DEF)' : '#7FE0FF';

  return (
    <svg
      className={className}
      data-placeholder="orbi"
      width={size}
      height={(size * 94) / 86}
      viewBox="0 0 86 94"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      {/* antenna */}
      <line x1="43" y1="5" x2="43" y2="17" stroke="#F6B53C" strokeWidth="4" strokeLinecap="round" />
      <circle cx="43" cy="5" r="5" fill="#F6B53C" />
      {/* head and ears */}
      <rect x="12" y="15" width="62" height="54" rx="19" fill={body} />
      <rect x="6" y="33" width="8" height="19" rx="4" fill="#F0936B" />
      <rect x="72" y="33" width="8" height="19" rx="4" fill="#F0936B" />
      {/* face screen */}
      <rect x="20" y="25" width="46" height="34" rx="13" fill={screen} />
      <circle cx="35" cy="40" r="4.6" fill={eyes} />
      <circle cx="51" cy="40" r="4.6" fill={eyes} />
      <path d="M34 49 q9 7 18 0" stroke={eyes} strokeWidth="3" strokeLinecap="round" />
      {/* body */}
      <rect x="24" y="69" width="38" height="20" rx="11" fill={body} />
    </svg>
  );
}
