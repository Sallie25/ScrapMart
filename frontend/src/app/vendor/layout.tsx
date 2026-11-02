import type { ReactNode } from "react";
import { VendorShell } from "@/components/vendor/vendor-shell";
export default function VendorLayout({ children }: { children: ReactNode }) {
  return <VendorShell>{children}</VendorShell>;
}
