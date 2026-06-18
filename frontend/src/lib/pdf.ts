// react-pdf wiring. The PDF.js worker is bundled locally via Vite (import.meta.url
// resolves to a hashed asset under /assets) — NOT a CDN, matching the D14 spirit
// of demo robustness with no runtime network dependency.
import { Document, Page, pdfjs } from "react-pdf";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

export { Document, Page };
