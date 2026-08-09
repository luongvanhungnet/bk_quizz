import { Outlet } from "react-router";
import { BrandLogo } from "./BrandLogo";

export function PageBrandLayout() {
  return (
    <div className="min-h-dvh">
      <header className="relative z-50 flex h-16 items-center border-b border-black/5 bg-white px-4 sm:px-6">
        <BrandLogo />
      </header>
      <Outlet />
    </div>
  );
}
