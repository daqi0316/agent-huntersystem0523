"use client";

import { useState, useCallback } from "react";

interface Candidate {
  id: string;
  name: string;
  email: string;
  skills: string[];
  status: string;
}

export function useCandidates() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchCandidates = useCallback(async (jobId?: string) => {
    setLoading(true);
    try {
      // TODO: Replace with actual API call
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  }, []);

  return { candidates, loading, fetchCandidates };
}
