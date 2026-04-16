import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";

interface SparklineProps {
  data: { v: number }[];
  color?: string;
  height?: number;
  width?: number | string;
}

export function Sparkline({
  data,
  color = "hsl(var(--primary))",
  height = 36,
  width = "100%",
}: SparklineProps) {
  if (!data || data.length === 0) {
    return <div className="h-9 w-full rounded-sm bg-muted/30" aria-label="no data" />;
  }
  return (
    <div style={{ width, height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Line
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
