import { ReactNode } from "react";
import { DashboardProvider } from "@/components/dashboard/DashboardProvider";

export const metadata = {
  title: "SAATHI Dashboard",
};

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <DashboardProvider>
      {children}
    </DashboardProvider>
  );
}
