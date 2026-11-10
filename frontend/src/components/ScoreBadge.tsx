import { scoreBand } from "../lib/format";

export function ScoreBadge({ score }: { score: number | null }) {
  return (
    <span className={`score score-${scoreBand(score)}`} title={score === null ? "Not scored yet" : `Match ${score}/100`}>
      {score ?? "…"}
    </span>
  );
}
