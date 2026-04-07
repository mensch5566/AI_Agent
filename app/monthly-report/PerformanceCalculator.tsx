"use client";

import { useState } from "react";

interface StockPrice {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface Result {
  ticker: string;
  startDate: string;
  endDate: string;
  startPrice: number;
  endPrice: number;
  change: number;
  changePercent: number;
}

const AVAILABLE_TICKERS = ["SPY", "QQQ", "DIA"];

function getFirstDayOfMonth(date: Date): string {
  const d = new Date(date);
  d.setDate(1);
  return d.toISOString().split("T")[0];
}

function getTodayString(): string {
  return new Date().toISOString().split("T")[0];
}

function calculatePerformance(data: StockPrice[]): {
  startPrice: number;
  endPrice: number;
  change: number;
  changePercent: number;
} | null {
  if (data.length < 2) {
    return null;
  }

  const startPrice = data[0].close;
  const endPrice = data[data.length - 1].close;
  const change = endPrice - startPrice;
  const changePercent = (change / startPrice) * 100;

  return {
    startPrice,
    endPrice,
    change,
    changePercent,
  };
}

export function PerformanceCalculator() {
  const [startDate, setStartDate] = useState(getFirstDayOfMonth(new Date()));
  const [endDate, setEndDate] = useState(getTodayString());
  const [selectedTickers, setSelectedTickers] = useState<string[]>(["SPY"]);
  const [results, setResults] = useState<Result[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleTickerToggle = (ticker: string) => {
    setSelectedTickers(prev =>
      prev.includes(ticker)
        ? prev.filter(t => t !== ticker)
        : [...prev, ticker]
    );
  };

  const handleCalculate = async () => {
    if (!startDate || !endDate) {
      setError("Please select both start and end dates");
      return;
    }

    if (new Date(startDate) > new Date(endDate)) {
      setError("Start date must be before end date");
      return;
    }

    if (selectedTickers.length === 0) {
      setError("Please select at least one ticker");
      return;
    }

    setLoading(true);
    setError(null);
    setResults([]);

    try {
      const newResults: Result[] = [];

      for (const ticker of selectedTickers) {
        const response = await fetch(
          `/api/stock-prices/${ticker}?start=${startDate}&end=${endDate}`
        );

        if (!response.ok) {
          setError(`Failed to fetch data for ${ticker}`);
          continue;
        }

        const json = await response.json();
        const data = json.data as StockPrice[];

        if (data.length === 0) {
          setError(
            `No data available for ${ticker} in this date range`
          );
          continue;
        }

        const perf = calculatePerformance(data);
        if (!perf) {
          setError(`Insufficient data for ${ticker}`);
          continue;
        }

        newResults.push({
          ticker,
          startDate: data[0].date,
          endDate: data[data.length - 1].date,
          startPrice: perf.startPrice,
          endPrice: perf.endPrice,
          change: perf.change,
          changePercent: perf.changePercent,
        });
      }

      setResults(newResults);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* 日期選擇 */}
      <div className="bg-[var(--bg-card)] rounded-[var(--radius)] border border-[var(--border)] p-6 shadow-[0_1px_3px_rgba(44,21,23,0.06)]">
        <h2 className="text-lg font-semibold mb-4 text-[var(--text)]">選擇時間範圍</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-[var(--text)] mb-2">
              開始日期
            </label>
            <input
              type="date"
              value={startDate}
              onChange={e => setStartDate(e.target.value)}
              className="w-full px-3 py-2 border border-[var(--border)] rounded-md bg-[var(--bg-page)] text-[var(--text)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-[var(--text)] mb-2">
              結束日期
            </label>
            <input
              type="date"
              value={endDate}
              onChange={e => setEndDate(e.target.value)}
              className="w-full px-3 py-2 border border-[var(--border)] rounded-md bg-[var(--bg-page)] text-[var(--text)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
            />
          </div>
        </div>
      </div>

      {/* 標的選擇 */}
      <div className="bg-[var(--bg-card)] rounded-[var(--radius)] border border-[var(--border)] p-6 shadow-[0_1px_3px_rgba(44,21,23,0.06)]">
        <h2 className="text-lg font-semibold mb-4 text-[var(--text)]">選擇標的</h2>
        <div className="space-y-3">
          {AVAILABLE_TICKERS.map(ticker => (
            <label key={ticker} className="flex items-center space-x-3 cursor-pointer hover:opacity-80">
              <input
                type="checkbox"
                checked={selectedTickers.includes(ticker)}
                onChange={() => handleTickerToggle(ticker)}
                className="w-4 h-4 rounded border-[var(--border)] accent-[var(--primary)]"
              />
              <span className="text-[var(--text)] font-medium">{ticker}</span>
            </label>
          ))}
        </div>
      </div>

      {/* 錯誤訊息 */}
      {error && (
        <div className="bg-[var(--bg-highlight)] border border-[var(--primary-lt)] rounded-[var(--radius)] p-4">
          <p className="text-[var(--primary-dk)] text-sm">{error}</p>
        </div>
      )}

      {/* 計算按鈕 */}
      <button
        onClick={handleCalculate}
        disabled={loading}
        className="w-full bg-[var(--primary)] hover:bg-[var(--primary-dk)] disabled:bg-[var(--text-faint)] text-white font-semibold py-3 rounded-[var(--radius)] transition shadow-[0_2px_4px_rgba(44,21,23,0.1)]"
      >
        {loading ? "計算中..." : "計算漲跌幅"}
      </button>

      {/* 結果表格 */}
      {results.length > 0 && (
        <div className="bg-[var(--bg-card)] rounded-[var(--radius)] border border-[var(--border)] overflow-hidden shadow-[0_1px_3px_rgba(44,21,23,0.06)]">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-[var(--bg-subtle)] border-b border-[var(--border)]">
                <tr>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-[var(--text)]">
                    標的
                  </th>
                  <th className="px-6 py-3 text-right text-sm font-semibold text-[var(--text)]">
                    開始價
                  </th>
                  <th className="px-6 py-3 text-right text-sm font-semibold text-[var(--text)]">
                    結束價
                  </th>
                  <th className="px-6 py-3 text-right text-sm font-semibold text-[var(--text)]">
                    漲跌幅
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[var(--text-muted)]">
                    期間
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {results.map(result => (
                  <tr key={result.ticker} className="hover:bg-[var(--bg-subtle)] transition">
                    <td className="px-6 py-4 text-sm font-semibold text-[var(--text)]">
                      {result.ticker}
                    </td>
                    <td className="px-6 py-4 text-right text-sm text-[var(--text-muted)]">
                      ${result.startPrice.toFixed(2)}
                    </td>
                    <td className="px-6 py-4 text-right text-sm text-[var(--text-muted)]">
                      ${result.endPrice.toFixed(2)}
                    </td>
                    <td
                      className={`px-6 py-4 text-right text-sm font-semibold ${
                        result.changePercent >= 0
                          ? "text-[var(--primary-lt)]"
                          : "text-[var(--primary)]"
                      }`}
                    >
                      {result.changePercent >= 0 ? "+" : ""}
                      {result.changePercent.toFixed(2)}%
                    </td>
                    <td className="px-6 py-4 text-xs text-[var(--text-faint)]">
                      {result.startDate} ~ {result.endDate}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {results.length === 0 && !loading && (
        <div className="text-center py-12 text-[var(--text-muted)]">
          <p>選擇日期和標的，點擊「計算漲跌幅」查看結果</p>
        </div>
      )}
    </div>
  );
}
