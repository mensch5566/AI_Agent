import type { Metadata } from "next";
import { Suspense } from "react";
import Viewer from "./Viewer";

export const metadata: Metadata = {
  title: "Financials Viewer (SEC v2)",
};

export default async function Page({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;
  return (
    <Suspense>
      <Viewer ticker={ticker.toUpperCase()} />
    </Suspense>
  );
}
