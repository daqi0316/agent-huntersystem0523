"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Candidate } from "@/types";

interface CandidateCardProps {
  candidate: Candidate;
  matchScore?: number;
  onClick?: () => void;
}

export function CandidateCard({ candidate, matchScore, onClick }: CandidateCardProps) {
  return (
    <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={onClick}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{candidate.name}</CardTitle>
          {matchScore !== undefined && (
            <Badge variant={matchScore >= 0.8 ? "success" : matchScore >= 0.6 ? "warning" : "secondary"}>
              {Math.round(matchScore * 100)}%
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground mb-2 line-clamp-2">{candidate.summary}</p>
        <div className="flex flex-wrap gap-1">
          {candidate.skills.slice(0, 4).map((skill) => (
            <Badge key={skill} variant="secondary" className="text-xs">
              {skill}
            </Badge>
          ))}
          {candidate.skills.length > 4 && (
            <Badge variant="outline" className="text-xs">
              +{candidate.skills.length - 4}
            </Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
