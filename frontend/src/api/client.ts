import axios from "axios";
import { message } from "antd";
import { useAuth } from "../store/auth";

// 统一 axios 实例：自动带 token，统一解包 {code, message, data}
export const api = axios.create({
  baseURL: "/api",
  timeout: 15000,
});

api.interceptors.request.use((config) => {
  const token = useAuth.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (resp) => {
    const body = resp.data;
    if (body && typeof body.code === "number" && body.code !== 0) {
      return Promise.reject(new Error(body.message || "请求失败"));
    }
    return resp;
  },
  (err) => {
    // 401 统一跳登录
    if (err.response?.status === 401) {
      useAuth.getState().logout();
      message.error("登录已过期，请重新登录");
    }
    return Promise.reject(err);
  }
);

// 解包 data 的便捷方法
export async function unwrap<T>(p: Promise<any>): Promise<T> {
  const resp = await p;
  return resp.data.data;
}
