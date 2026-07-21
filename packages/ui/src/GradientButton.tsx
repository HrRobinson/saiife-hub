import { Slot } from "radix-ui";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "./cn";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  asChild?: boolean;
  variant?: "solid" | "outline";
};

export function GradientButton({
  asChild,
  variant = "solid",
  className,
  children,
  ...props
}: Props) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      className={cn(
        "group relative inline-flex items-center justify-center gap-2",
        "rounded-full px-6 py-2.5 text-sm font-medium",
        "transition-[transform,filter] duration-200",
        "hover:scale-[1.02] hover:brightness-110",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        "motion-reduce:transition-none motion-reduce:hover:scale-100",
        variant === "solid"
          ? "brand-gradient text-primary-foreground glow-ring"
          : "border border-[var(--border-glow)] text-foreground bg-card/40 hover:bg-card/60",
        "overflow-hidden",
        className,
      )}
      {...props}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 -translate-x-full bg-gradient-to-r from-transparent via-white/20 to-transparent transition-transform duration-700 group-hover:translate-x-full motion-reduce:hidden"
      />
      {asChild ? <Slot.Slottable>{children}</Slot.Slottable> : children}
    </Comp>
  );
}
