import { Link } from "react-router";

export function BrandLogo({ className = "" }: { className?: string }) {
  return (
    <Link
      aria-label="BKQuiz - về Dashboard"
      className={`relative block h-11 w-36 overflow-hidden rounded-lg border border-white/20 bg-[#31383d] shadow-lg sm:h-12 sm:w-44 ${className}`}
      to="/dashboard"
    >
      <img
        alt="BKQuiz"
        className="absolute left-1/2 top-1/2 w-[165%] max-w-none -translate-x-1/2 -translate-y-1/2"
        src="/brand/bkquiz-logo.png"
      />
    </Link>
  );
}

