import { Navigate, Route, Routes } from "react-router-dom";
import NavRail from "./components/NavRail";
import Header from "./components/Header";
import NewAnalysis from "./pages/NewAnalysis";
import ViewAnalysis from "./pages/ViewAnalysis";
import Admin from "./pages/Admin";

export default function App() {
  return (
    <div className="flex h-full">
      <NavRail />
      <div className="flex flex-1 flex-col min-w-0">
        <Header />
        <main className="flex-1 overflow-auto px-8 py-8">
          <Routes>
            <Route path="/" element={<Navigate to="/new" replace />} />
            <Route path="/new" element={<NewAnalysis />} />
            <Route path="/analysis/:jobId?" element={<ViewAnalysis />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="*" element={<Navigate to="/new" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
