import React from 'react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { X } from 'lucide-react';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger' | 'soft' | 'success';
type ButtonSize = 'sm' | 'md' | 'lg' | 'icon';

export const Button = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant, size?: ButtonSize }>(
  ({ className, variant = 'primary', size = 'md', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex shrink-0 items-center justify-center gap-2 rounded-md font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8102E] focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
          {
            "bg-[#C8102E] text-white shadow-sm hover:bg-[#A50F24] active:translate-y-px": variant === 'primary',
            "bg-[#111827] text-white hover:bg-black": variant === 'secondary',
            "border border-[#E5E7EB] bg-white text-[#111827] shadow-sm hover:border-[#C8102E]/40 hover:bg-[#FFF8E8]": variant === 'outline',
            "text-[#6B7280] hover:bg-[#F7F7F8] hover:text-[#111827]": variant === 'ghost',
            "bg-[#DC2626] text-white shadow-sm hover:bg-[#B91C1C]": variant === 'danger',
            "border border-[#F6C9D0] bg-[#FDE7EA] text-[#C8102E] hover:bg-[#F9D7DD]": variant === 'soft',
            "bg-[#16A34A] text-white hover:bg-[#15803D]": variant === 'success',
            "h-8 px-3 text-xs": size === 'sm',
            "h-10 px-4 text-sm": size === 'md',
            "h-12 px-6 text-base": size === 'lg',
            "h-10 w-10 p-0": size === 'icon',
          },
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={cn(
          "flex h-10 w-full rounded-md border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#111827] ring-offset-white file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-[#9CA3AF] focus-visible:border-transparent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8102E] disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("rounded-lg border border-[#E5E7EB] bg-white shadow-sm", className)}
      {...props}
    />
  )
);
Card.displayName = "Card";

export const Checkbox = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => {
    return (
      <input
        type="checkbox"
        ref={ref}
        className={cn(
          "h-4 w-4 rounded border-[#D1D5DB] text-[#C8102E] focus:ring-[#C8102E] accent-[#C8102E]",
          className
        )}
        {...props}
      />
    );
  }
);
Checkbox.displayName = "Checkbox";

export function Badge({ className, children }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span className={cn("inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold", className)}>
      {children}
    </span>
  );
}

export function Modal({
  title,
  children,
  onClose,
  className,
}: {
  title?: string;
  children: React.ReactNode;
  onClose: () => void;
  className?: string;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4">
      <Card className={cn("max-h-[90vh] w-full max-w-lg overflow-hidden bg-white shadow-2xl", className)}>
        {(title || onClose) && (
          <div className="flex items-center justify-between border-b border-[#E5E7EB] px-5 py-4">
            <h3 className="font-bold text-[#111827]">{title}</h3>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1.5 text-[#6B7280] hover:bg-[#F7F7F8] hover:text-[#111827]"
              aria-label="Đóng"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        )}
        {children}
      </Card>
    </div>
  );
}
