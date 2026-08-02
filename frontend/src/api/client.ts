import axios from 'axios';

const isProd = import.meta.env.PROD;
const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const wsBase = apiUrl.replace(/^http/, 'ws');
const prodWsUrl = import.meta.env.VITE_WS_URL || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;

export const apiClient = axios.create({
  baseURL: isProd ? (import.meta.env.VITE_API_URL ? `${import.meta.env.VITE_API_URL}/api/v1` : '/api/v1') : `${apiUrl}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const wsBaseURL = isProd
  ? prodWsUrl
  : `${wsBase}/ws`;


