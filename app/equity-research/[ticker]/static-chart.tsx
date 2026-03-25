"use client";

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from "chart.js";
import { Bar, Line } from "react-chartjs-2";

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
);

interface Dataset {
  label: string;
  data: (number | null)[];
  color?: string;
}

interface Props {
  type: "bar" | "area";
  labels: string[];
  datasets: Dataset[];
  yLabel?: string;
}

const COLORS = ["#C02734", "#2D8A4E", "#B07D10", "#5A3E42", "#3B82F6"];

export default function StaticChart({ type, labels, datasets, yLabel }: Props) {
  const chartData = {
    labels,
    datasets: datasets.map((ds, i) => ({
      label: ds.label,
      data: ds.data,
      backgroundColor:
        type === "bar"
          ? (ds.color || COLORS[i % COLORS.length]) + "CC"
          : (ds.color || COLORS[i % COLORS.length]) + "33",
      borderColor: ds.color || COLORS[i % COLORS.length],
      borderWidth: type === "bar" ? 0 : 2,
      fill: type === "area",
      tension: 0.3,
      pointRadius: type === "area" ? 4 : 0,
      pointBackgroundColor: ds.color || COLORS[i % COLORS.length],
    })),
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: datasets.length > 1,
        position: "top" as const,
        labels: { font: { size: 11 }, usePointStyle: true },
      },
      tooltip: {
        callbacks: {
          label: (ctx: { dataset: { label?: string }; parsed: { y: number | null } }) => {
            const v = ctx.parsed.y;
            if (v == null) return "";
            return `${ctx.dataset.label}: $${v}B`;
          },
        },
      },
    },
    scales: {
      y: {
        beginAtZero: false,
        title: {
          display: !!yLabel,
          text: yLabel || "",
          font: { size: 11 },
        },
        ticks: { font: { size: 11 } },
        grid: { color: "rgba(0,0,0,0.05)" },
      },
      x: {
        ticks: { font: { size: 11 } },
        grid: { display: false },
      },
    },
  };

  return (
    <div className="my-3" style={{ height: 280 }}>
      {type === "bar" ? (
        <Bar data={chartData} options={options} />
      ) : (
        <Line data={chartData} options={options} />
      )}
    </div>
  );
}
