import type { CSSProperties, SVGProps } from 'react';

export type IconName =
  | 'add'
  | 'arrow-left'
  | 'arrow-right'
  | 'arrow-up'
  | 'attachment'
  | 'bot'
  | 'checkmark'
  | 'checkmark-filled'
  | 'chevron-down'
  | 'chevron-left'
  | 'chevron-right'
  | 'chevron-up'
  | 'close'
  | 'copy'
  | 'document'
  | 'edit'
  | 'error-filled'
  | 'information'
  | 'logo'
  | 'menu'
  | 'overflow-menu-horizontal'
  | 'overflow-menu-vertical'
  | 'search'
  | 'send'
  | 'settings'
  | 'thumbs-down'
  | 'thumbs-up'
  | 'trash'
  | 'user'
  | 'warning-filled';

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'name'> {
  name: IconName;
  size?: number | string;
  title?: string;
}

const SPRITE_URL = '/icons/carbon-icons.svg';

export default function Icon({
  name,
  size = 16,
  title,
  style,
  ...rest
}: IconProps) {
  const dim: CSSProperties = {
    width: typeof size === 'number' ? `${size}px` : size,
    height: typeof size === 'number' ? `${size}px` : size,
    flexShrink: 0,
    ...style,
  };
  return (
    <svg
      aria-hidden={title ? undefined : true}
      role={title ? 'img' : undefined}
      focusable="false"
      style={dim}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      <use href={`${SPRITE_URL}#${name}`} />
    </svg>
  );
}
