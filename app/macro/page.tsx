import type { Metadata } from "next";
import { Suspense } from "react";
import Dashboard from "./Dashboard";

export const metadata: Metadata = { title: "AI 資金流儀表板" };

export default function Page() {
  return (
    <Suspense>
      <Dashboard />
    </Suspense>
  );
}
