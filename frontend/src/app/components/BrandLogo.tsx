import { Link } from "react-router";

export function BrandLogo({ className = "" }: { className?: string }) {
  return (
    <Link
      aria-label="BKQuiz - về Dashboard"
      className={`block h-10 w-36 shrink-0 ${className}`}
      to="/dashboard"
    >
      <img
        alt="BKQuiz"
        className="h-full w-full object-contain object-left"
        src="/brand/bkquiz-logo-transparent.png"
      />
    </Link>
  );
}
