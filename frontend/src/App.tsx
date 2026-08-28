import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./layout/AppLayout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import PlanList from "./pages/PlanList";
import PlanNew from "./pages/PlanNew";
import PlanDetail from "./pages/PlanDetail";
import ReviewBoard from "./pages/ReviewBoard";
import MemoryGraph from "./pages/MemoryGraph";
import About from "./pages/About";
import { useAuth } from "./store/auth";

// 路由：登录 / 布局(工作台 + 行程列表 + 新建 + 详情 + 审核台 + 系统说明)
export default function App() {
  const { token } = useAuth();

  if (!token) {
    return <Login />;
  }

  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/plans" element={<PlanList />} />
        <Route path="/plans/new" element={<PlanNew />} />
        <Route path="/plans/:id" element={<PlanDetail />} />
        <Route path="/reviews" element={<ReviewBoard />} />
        <Route path="/memory" element={<MemoryGraph />} />
        <Route path="/about" element={<About />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
