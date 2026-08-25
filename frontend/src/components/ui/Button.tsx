import type { ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" };

export function Button({ variant = "primary", className = "", ...props }: Props) {
  return <button className={`ui-button ui-button-${variant} ${className}`} {...props} />;
}
