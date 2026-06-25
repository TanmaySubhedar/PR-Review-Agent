import { Route, Routes } from "react-router-dom";
import { ReviewDetailPage } from "./pages/ReviewDetailPage";
import { ReviewListPage } from "./pages/ReviewListPage";

export function App() {
  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: 24, fontFamily: "sans-serif" }}>
      <Routes>
        <Route path="/" element={<ReviewListPage />} />
        <Route path="/reviews/:reviewRunId" element={<ReviewDetailPage />} />
      </Routes>
    </div>
  );
}
