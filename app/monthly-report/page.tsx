import { PerformanceCalculator } from "./PerformanceCalculator";

export const metadata = {
  title: "月報 - 漲跌幅計算器",
  description: "對比多個市場標的的漲跌幅表現",
};

export default function MonthlyReportPage() {
  return (
    <div className="min-h-screen bg-background p-8">
      <div className="max-w-4xl mx-auto">
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-2">月報 - 漲跌幅計算器</h1>
          <p className="text-muted-foreground">
            選擇日期範圍，快速對比多個市場標的的表現
          </p>
        </div>

        <PerformanceCalculator />
      </div>
    </div>
  );
}
