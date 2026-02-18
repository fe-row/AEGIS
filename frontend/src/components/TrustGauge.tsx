"use client";

interface Props {
  score: number;
  size?: number;
}

export default function TrustGauge({ score, size = 80 }: Props) {
  const radius = (size - 10) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;

  const color =
    score >= 80 ? "#22c55e" :
    score >= 60 ? "#3b82f6" :
    score >= 40 ? "#eab308" :
    score >= 20 ? "#f97316" : "#ef4444";

  const label =
    score >= 80 ? "HIGH" :
    score >= 60 ? "MED" :
    score >= 40 ? "STD" :
    score >= 20 ? "LOW" : "CRIT";

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#1f2937" strokeWidth={4} />
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke={color} strokeWidth={4}
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          strokeLinecap="round"
          className="transition-all duration-700"
        />
      </svg>
      <div className="absolute text-center">
        <div className="text-xs font-bold" style={{ color }}>{Math.round(score)}</div>
        <div className="text-[8px] text-gray-500 uppercase">{label}</div>
      </div>
    </div>
  );
}