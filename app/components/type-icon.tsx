import type { ContentType } from "../lib/db";

type IconProps = { className?: string; size?: number };

function Envelope({ className, size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className={className} aria-hidden="true">
      <rect x="1.5" y="3.5" width="13" height="9" rx="1" />
      <path d="M1.5 4.5l6.5 4.5 6.5-4.5" />
    </svg>
  );
}

function Quote({ className, size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M3.5 4.5h3.5v4H5l-.5 3H3l1-3H3.5v-4zm6 0H13v4h-2l-.5 3H8.5l1-3H9.5v-4z" />
    </svg>
  );
}

function Microphone({ className, size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className={className} aria-hidden="true">
      <rect x="6" y="2" width="4" height="8" rx="2" />
      <path d="M3.5 8a4.5 4.5 0 0 0 9 0" />
      <path d="M8 12.5v2M6 14.5h4" />
    </svg>
  );
}

function Scroll({ className, size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className={className} aria-hidden="true">
      <path d="M3.5 2.5h7l2 2v9h-7l-2-2v-9z" />
      <path d="M5 5h5M5 7.5h5M5 10h3" />
    </svg>
  );
}

function Camera({ className, size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className={className} aria-hidden="true">
      <path d="M2 5h2.5l1-1.5h5l1 1.5H14v8H2z" />
      <circle cx="8" cy="9" r="2.5" />
    </svg>
  );
}

function Notebook({ className, size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className={className} aria-hidden="true">
      <rect x="3" y="2.5" width="10" height="11" rx="1" />
      <path d="M5.5 2.5v11M7 5.5h4M7 8h4M7 10.5h2.5" />
    </svg>
  );
}

function Star({ className, size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M8 2l1.7 3.9 4.3.4-3.2 2.9 1 4.2L8 11.3 4.2 13.4l1-4.2L2 6.3l4.3-.4z" />
    </svg>
  );
}

function Dot({ className, size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <circle cx="8" cy="8" r="3" />
    </svg>
  );
}

const ICONS: Record<ContentType, React.ComponentType<IconProps>> = {
  press_release: Envelope,
  statement: Quote,
  op_ed: Notebook,
  blog: Notebook,
  letter: Scroll,
  photo_release: Camera,
  floor_statement: Microphone,
  presidential_action: Star,
  other: Dot,
};

export function TypeIcon({
  type,
  size = 14,
  className,
}: {
  type: ContentType;
  size?: number;
  className?: string;
}) {
  const Cmp = ICONS[type] ?? Dot;
  return <Cmp size={size} className={className} />;
}
