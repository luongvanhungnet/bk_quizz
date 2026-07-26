import { Outlet } from "react-router";
import { BrandLogo } from "./BrandLogo";

export function PageBrandLayout() {
  return (
    <>
      <div className="fixed left-3 top-2 z-[100] sm:left-5">
        <BrandLogo />
      </div>
      <Outlet />
    </>
  );
}

