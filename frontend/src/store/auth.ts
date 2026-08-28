import { create } from "zustand";

// 鉴权状态：token + 用户信息持久化到 localStorage
interface AuthState {
  token: string | null;
  role: string | null;
  username: string | null;
  setAuth: (token: string, role: string, username: string) => void;
  logout: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  token: localStorage.getItem("token"),
  role: localStorage.getItem("role"),
  username: localStorage.getItem("username"),
  setAuth: (token, role, username) => {
    localStorage.setItem("token", token);
    localStorage.setItem("role", role);
    localStorage.setItem("username", username);
    set({ token, role, username });
  },
  logout: () => {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    localStorage.removeItem("username");
    set({ token: null, role: null, username: null });
  },
}));
