import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Compose Tailwind class names safely (shadcn/ui convention). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
