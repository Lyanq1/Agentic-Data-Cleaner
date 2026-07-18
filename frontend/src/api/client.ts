import axios from 'axios';

const isProd = import.meta.env.PROD;
const prodApiUrl = import.meta.env.VITE_API_URL || '';
const prodWsUrl = import.meta.env.VITE_WS_URL || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;

export const apiClient = axios.create({
  baseURL: isProd ? (prodApiUrl ? `${prodApiUrl}/api/v1` : '/api/v1') : 'http://localhost:8000/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const wsBaseURL = isProd
  ? prodWsUrl
  : 'ws://localhost:8000/ws';


