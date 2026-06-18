import { createContext, useContext } from "react";
import type { Citation } from "../lib/types";

// The currently-targeted source location for the split-pane PDF viewer.
export interface CiteTarget {
  docId: string;
  docName: string;
  page: number;
  bbox: [number, number, number, number] | null;
  text: string;
  chunkId: string;
}

interface CitationApi {
  cite: (c: Citation) => void;
  activeChunkId: string | null;
  loading: boolean;
}

const CitationContext = createContext<CitationApi | null>(null);

export const CitationProvider = CitationContext.Provider;

export function useCitation(): CitationApi {
  const ctx = useContext(CitationContext);
  if (!ctx) throw new Error("useCitation must be used within a CitationProvider");
  return ctx;
}
