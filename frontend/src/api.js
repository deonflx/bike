import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api',
});

let tokenGetter = null;

export const setAuthTokenGetter = (fn) => {
  tokenGetter = fn;
};

// Request interceptor to attach Clerk JWT Bearer token
api.interceptors.request.use(async (config) => {
  try {
    let token = null;
    if (tokenGetter) {
      token = await tokenGetter();
    } else if (window.Clerk?.session) {
      token = await window.Clerk.session.getToken();
    }
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  } catch (err) {
    console.error('Failed to attach Clerk token:', err);
  }
  return config;
});

export default api;